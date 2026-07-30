"""Orchestrator & CLI runner for the Ethiopian Financial Intelligence Bureau."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from ethio_fin_bureau.config import (
    MIN_RELEVANCE_SCORE,
    OUTPUT_PATH,
    STRONG_SIGNAL_KEYWORDS,
    TARGET_SOURCES,
    OPENROUTER_API_KEY_ENV,
    USE_SQLITE,
    TELEGRAM_MIN_IMPACT,
)
from ethio_fin_bureau.llm.analyzer import (
    analyze_articles,
    analyze_articles_new,
)
from ethio_fin_bureau.llm.schemas import (
    PipelineOutput,
    ScrapedArticle,
    MarketIntelligenceReport,
)
from ethio_fin_bureau.middleware.date_converter import extract_and_convert_dates
from ethio_fin_bureau.middleware.prefilter import is_noise, score_relevance
from ethio_fin_bureau.scrapers.ingestion import FinancialBureauIngestionEngine
# Database and delivery imports are conditional to avoid import errors
# when optional dependencies are not installed
try:
    from ethio_fin_bureau.db.database import init_db, save_record, get_stats
except ImportError:
    init_db = None
    save_record = None
    get_stats = None

try:
    from ethio_fin_bureau.delivery.telegram import broadcast_alerts
except ImportError:
    broadcast_alerts = None

# Configure production-ready logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ethio_fin_bureau/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Reduce noise from external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _source_config_map() -> Dict[str, Dict]:
    return {s["source_name"]: s for s in TARGET_SOURCES}


def enrich_and_filter(raw_items: List[Dict]) -> List[ScrapedArticle]:
    source_map = _source_config_map()
    cleaned: List[ScrapedArticle] = []
    for item in raw_items:
        headline = item["headline"]
        url = item["url"]
        tier = item["tier"]
        source_name = item["source_name"]
        cfg = source_map.get(source_name, {})
        require_match = cfg.get("require_keyword_match", False)
        if is_noise(headline, url):
            continue
        relevance, keywords = score_relevance(headline, tier, require_match)
        if require_match:
            if relevance < MIN_RELEVANCE_SCORE:
                continue
            if not any(kw in keywords for kw in STRONG_SIGNAL_KEYWORDS):
                continue
        published = extract_and_convert_dates(headline, url)
        cleaned.append(ScrapedArticle(
            source_name=source_name, tier=tier, headline=headline, url=url,
            published_date=published, relevance_score=round(relevance, 3),
            keywords_matched=sorted(set(keywords)),
        ))
    cleaned.sort(key=lambda a: (a.tier, -a.relevance_score))
    return cleaned


def _generate_content_hash(headline: str, url: str) -> str:
    return hashlib.sha256(f"{headline}|{url}".encode("utf-8")).hexdigest()


def _intel_to_db_record(intel: MarketIntelligenceReport, article: ScrapedArticle) -> dict:
    return {
        "content_hash": _generate_content_hash(article.headline, str(article.url)),
        "source_name": article.source_name,
        "tier": article.tier,
        "headline": article.headline,
        "url": str(article.url),
        "normalized_date": article.published_date,
        "executive_summary": intel.executive_summary,
        "sentiment": intel.sentiment.value.upper(),
        "impact_level": intel.impact_level.value.upper(),
        "primary_asset_class": intel.primary_asset_class.value,
        "affected_entities": list(intel.affected_entities),
        "trading_implication": intel.trading_implication,
    }


async def run_pipeline(run_llm: bool = False, llm_max: int = 10, use_new_schema: bool = False) -> PipelineOutput:
    engine = FinancialBureauIngestionEngine()
    raw = await engine.run()
    articles = enrich_and_filter(raw)
    intelligence: List = []
    if run_llm and articles:
        if use_new_schema:
            intelligence = analyze_articles_new(articles, max_items=llm_max)
        else:
            intelligence = analyze_articles(articles, max_items=llm_max)
    output = PipelineOutput(
        scraped_at=datetime.now(timezone.utc).isoformat(),
        total_items=len(articles), articles=articles, intelligence=intelligence,
    )
    return output


def save_output(output: PipelineOutput) -> None:
    payload = output.model_dump(mode="json")
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    OUTPUT_PATH.write_text(json_text, encoding="utf-8")
    root_output = OUTPUT_PATH.parent.parent / "output.json"
    root_output.write_text(json_text, encoding="utf-8")
    logger.info("Saved %d articles to %s", output.total_items, OUTPUT_PATH)


def persist_intelligence(output: PipelineOutput) -> int:
    if not USE_SQLITE:
        return 0
    init_db()
    saved_count = 0
    for article, intel in zip(output.articles, output.intelligence):
        if isinstance(intel, MarketIntelligenceReport):
            record_dict = _intel_to_db_record(intel, article)
            if save_record(record_dict):
                saved_count += 1
    logger.info("Persisted %d intelligence reports to database.", saved_count)
    return saved_count


async def broadcast_intelligence(output: PipelineOutput) -> int:
    reports = []
    for article, intel in zip(output.articles, output.intelligence):
        if isinstance(intel, MarketIntelligenceReport):
            reports.append({
                "source_name": article.source_name,
                "headline": article.headline,
                "normalized_date": article.published_date or "Unknown",
                "sentiment": intel.sentiment.value,
                "impact_level": intel.impact_level.value,
                "primary_asset_class": intel.primary_asset_class.value,
                "affected_entities": list(intel.affected_entities),
                "executive_summary": intel.executive_summary,
                "trading_implication": intel.trading_implication,
            })
    if not reports:
        return 0
    return await broadcast_alerts(reports, min_impact=TELEGRAM_MIN_IMPACT)


def check_llm_config() -> bool:
    api_key = os.environ.get(OPENROUTER_API_KEY_ENV) or os.environ.get("OPENAI_API_KEY")
    if api_key:
        logger.info("LLM API key found in environment")
        return True
    logger.warning("No LLM API key found.")
    return False


def main() -> None:
    """Main entry point with production-ready error handling."""
    parser = argparse.ArgumentParser(
        description="Ethiopian Financial Intelligence Bureau",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ethio_fin_bureau.main                    # Run pipeline
  python -m ethio_fin_bureau.main --llm              # With LLM analysis
  python -m ethio_fin_bureau.main --llm --new-schema # New intelligence schema
  python -m ethio_fin_bureau.main --llm --db         # Persist to database
  python -m ethio_fin_bureau.main --llm --telegram   # Broadcast via Telegram
  python -m ethio_fin_bureau.main --stats            # Show DB statistics
        """
    )
    parser.add_argument("--llm", action="store_true", help="Run LLM analysis")
    parser.add_argument("--llm-max", type=int, default=10, help="Max articles for LLM")
    parser.add_argument("--new-schema", action="store_true", help="Use new MarketIntelligenceReport schema")
    parser.add_argument("--db", action="store_true", help="Persist to database (SQLite or PostgreSQL)")
    parser.add_argument("--telegram", action="store_true", help="Broadcast alerts via Telegram")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    args = parser.parse_args()

    try:
        if args.stats:
            stats = get_stats()
            print(f"\n{'=' * 60}")
            print("  DATABASE STATISTICS")
            print(f"{'=' * 60}")
            if stats.get("enabled"):
                print(f"  Total records: {stats.get('total_records', 0)}")
                print(f"  By sentiment: {stats.get('by_sentiment', {})}")
                print(f"  By impact: {stats.get('by_impact', {})}")
            else:
                print("  Database persistence is disabled.")
                print("  Set USE_SQLITE=True in config.py or DATABASE_URL environment variable.")
            print(f"{'=' * 60}\n")
            return

        if args.llm:
            check_llm_config()

        logger.info("=" * 60)
        logger.info("Starting Financial Intelligence Pipeline")
        logger.info("=" * 60)
        
        output = asyncio.run(run_pipeline(run_llm=args.llm, llm_max=args.llm_max, use_new_schema=args.new_schema))
        save_output(output)

        db_saved = 0
        telegram_sent = 0

        if args.db and output.intelligence:
            db_saved = persist_intelligence(output)
            if db_saved:
                print(f"  DB records saved: {db_saved}")

        if args.telegram and output.intelligence:
            # Only broadcast if we have new intelligence (either new to DB or just generated)
            # If --db is enabled, only broadcast newly saved records
            # If --db is not enabled, broadcast all intelligence
            if args.db:
                # Only broadcast if we actually saved new records
                if db_saved > 0:
                    logger.info("Broadcasting %d new intelligence reports via Telegram", db_saved)
                    telegram_sent = asyncio.run(broadcast_intelligence(output))
                    if telegram_sent:
                        print(f"  Telegram alerts sent: {telegram_sent}")
                else:
                    logger.info("Skipping Telegram broadcast - all %d reports are duplicates", len(output.intelligence))
            else:
                # No DB mode, broadcast all intelligence
                logger.info("Broadcasting all %d intelligence reports via Telegram (no DB mode)", len(output.intelligence))
                telegram_sent = asyncio.run(broadcast_intelligence(output))
                if telegram_sent:
                    print(f"  Telegram alerts sent: {telegram_sent}")

        print(f"\n{'=' * 60}")
        print(f"  PIPELINE COMPLETE — {output.total_items} relevant articles")
        print(f"  Output: {OUTPUT_PATH}")
        if output.intelligence:
            print(f"  LLM intelligence items: {len(output.intelligence)}")
        if db_saved:
            print(f"  DB records saved: {db_saved}")
        if telegram_sent:
            print(f"  Telegram alerts sent: {telegram_sent}")
        print(f"{'=' * 60}\n")

        by_source: Dict[str, int] = {}
        for a in output.articles:
            by_source[a.source_name] = by_source.get(a.source_name, 0) + 1
        for source, count in sorted(by_source.items()):
            print(f"  {source}: {count}")

        logger.info("Pipeline completed successfully")
        
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Pipeline failed with error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()