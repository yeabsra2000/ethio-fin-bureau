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
    MarketIntelligence,
)
from ethio_fin_bureau.middleware.date_converter import extract_and_convert_dates
from ethio_fin_bureau.middleware.prefilter import is_noise, score_relevance
from ethio_fin_bureau.scrapers.ingestion import FinancialBureauIngestionEngine
# Database and delivery imports are conditional to avoid import errors
# when optional dependencies are not installed
try:
    from ethio_fin_bureau.db.database import init_db, save_record, get_stats, save_intelligence_report
except ImportError:
    init_db = None
    save_record = None
    get_stats = None
    save_intelligence_report = None

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
    """Convert a MarketIntelligenceReport and its source article to a database record dict."""
    record = {
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
        "event_type": intel.event_type.value,
        "time_horizon": intel.time_horizon.value,
        "confidence_score": intel.confidence_score,
    }
    
    # Add key_metrics as JSON if present
    if intel.key_metrics:
        record["key_metrics"] = json.dumps(
            [m.model_dump() if hasattr(m, 'model_dump') else m for m in intel.key_metrics],
            ensure_ascii=False
        )
    
    # Add actionable_signals as JSON if present
    if intel.actionable_signals:
        record["actionable_signals"] = json.dumps(
            [s.model_dump() if hasattr(s, 'model_dump') else s for s in intel.actionable_signals],
            ensure_ascii=False
        )
    
    # Add synthesized_market_impact if present
    if intel.synthesized_market_impact:
        record["synthesized_market_impact"] = intel.synthesized_market_impact
    
    # Add historical_connections as JSON if present
    if intel.historical_connections:
        record["historical_connections"] = json.dumps(
            [h.model_dump() if hasattr(h, 'model_dump') else h for h in intel.historical_connections],
            ensure_ascii=False
        )
    
    return record


async def run_pipeline(run_llm: bool = False, llm_max: int = 10, use_new_schema: bool = False) -> PipelineOutput:
    engine = FinancialBureauIngestionEngine()
    raw = await engine.run()
    articles = enrich_and_filter(raw)
    intelligence: List = []
    
    # OPTIMIZATION: Only run LLM on NEW articles to conserve tokens
    # Check which articles are new (not in database) before spawning AI
    if run_llm and articles:
        from ethio_fin_bureau.db.database import is_hash_exists
        
        new_articles = []
        for article in articles:
            content_hash = _generate_content_hash(article.headline, str(article.url))
            if not is_hash_exists(content_hash):
                new_articles.append(article)
        
        if new_articles:
            logger.info("Running LLM analysis on %d new articles (skipping %d duplicates)", 
                       len(new_articles), len(articles) - len(new_articles))
            
            # Sort by relevance and limit
            new_articles_sorted = sorted(new_articles, key=lambda a: a.relevance_score, reverse=True)[:llm_max]
            
            if use_new_schema:
                # Returns list of tuples: (MarketIntelligenceReport, ScrapedArticle)
                intel_with_articles = analyze_articles_new(new_articles_sorted, max_items=len(new_articles_sorted))
                # Extract just the intelligence reports for the output
                intelligence = [intel for intel, _ in intel_with_articles]
                # Store the mapping for persistence
                intelligence_article_map = {id(intel): article for intel, article in intel_with_articles}
            else:
                # Use the new analyze_articles which now returns MarketIntelligenceReport
                intelligence = analyze_articles(new_articles_sorted, max_items=len(new_articles_sorted))
                # Build mapping from intelligence reports to articles
                intelligence_article_map = {}
                for intel in intelligence:
                    # Find matching article by headline similarity
                    for article in new_articles_sorted:
                        if article.headline in intel.executive_summary or intel.executive_summary[:50] in article.headline:
                            intelligence_article_map[id(intel)] = article
                            break
        else:
            logger.info("All %d articles already in database - skipping LLM analysis", len(articles))
            intelligence_article_map = {}
    else:
        intelligence_article_map = {}
    
    output = PipelineOutput(
        scraped_at=datetime.now(timezone.utc).isoformat(),
        total_items=len(articles), articles=articles, intelligence=intelligence,
    )
    # Attach the mapping to the output for use in persistence
    output.intelligence_article_map = intelligence_article_map
    return output


def save_output(output: PipelineOutput) -> None:
    payload = output.model_dump(mode="json")
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    OUTPUT_PATH.write_text(json_text, encoding="utf-8")
    root_output = OUTPUT_PATH.parent.parent / "output.json"
    root_output.write_text(json_text, encoding="utf-8")
    logger.info("Saved %d articles to %s", output.total_items, OUTPUT_PATH)
    
    # Also generate a human-readable summary report
    _save_human_readable_report(output)


def _save_human_readable_report(output: PipelineOutput) -> None:
    """Generate a human-readable markdown summary alongside the JSON output."""
    report_path = OUTPUT_PATH.parent / "report.md"
    root_report = OUTPUT_PATH.parent.parent / "report.md"
    
    # Build a map from intelligence id to article for headline lookup
    intelligence_article_map = getattr(output, 'intelligence_article_map', {})
    
    def _get_headline_for_intel(intel) -> str:
        """Get the original headline for an intelligence report."""
        # Try the map first
        article = intelligence_article_map.get(id(intel))
        if article:
            return article.headline
        # Fallback: try to find by matching in articles list
        for article in output.articles:
            if article.headline in intel.executive_summary[:100]:
                return article.headline
        return "N/A"
    
    lines = [
        "# Financial Intelligence Report",
        f"**Generated:** {output.scraped_at}",
        f"**Total Articles:** {output.total_items}",
        f"**Intelligence Reports:** {len(output.intelligence)}",
        "",
        "---",
        "",
    ]
    
    if output.intelligence:
        lines.append("## 📊 Intelligence Summary")
        lines.append("")
        
        for i, intel in enumerate(output.intelligence, 1):
            if isinstance(intel, MarketIntelligenceReport):
                # Impact emoji
                impact_emoji = {"critical": "🚨", "high": "🔥", "medium": "📌", "low": "💡"}.get(
                    intel.impact_level.value, "📊"
                )
                sentiment_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(
                    intel.sentiment.value, "⚪"
                )
                
                headline = _get_headline_for_intel(intel)
                lines.append(f"### {i}. {impact_emoji} {intel.event_type.value.replace('_', ' ').title()}")
                lines.append(f"")
                lines.append(f"**{headline}**")
                lines.append(f"")
                lines.append(f"| Field | Value |")
                lines.append(f"|-------|-------|")
                lines.append(f"| Sentiment | {sentiment_emoji} {intel.sentiment.value.upper()} |")
                lines.append(f"| Impact | {intel.impact_level.value.upper()} |")
                lines.append(f"| Asset Class | {intel.primary_asset_class.value} |")
                lines.append(f"| Time Horizon | {intel.time_horizon.value} |")
                lines.append(f"| Confidence | {intel.confidence_score:.0%} |")
                lines.append(f"")
                lines.append(f"**Executive Summary:**")
                lines.append(f"> {intel.executive_summary}")
                lines.append(f"")
                lines.append(f"**Trading Implication:**")
                lines.append(f"> {intel.trading_implication}")
                lines.append(f"")
                
                if intel.key_metrics:
                    lines.append(f"**Key Metrics:**")
                    for metric in intel.key_metrics:
                        if hasattr(metric, 'name'):
                            lines.append(f"- **{metric.name}:** {metric.value} ({metric.context})")
                        else:
                            lines.append(f"- {metric}")
                    lines.append(f"")
                
                if intel.actionable_signals:
                    lines.append(f"**Actionable Signals:**")
                    for signal in intel.actionable_signals:
                        if hasattr(signal, 'signal_type'):
                            lines.append(f"- **{signal.signal_type.upper()}** {signal.asset}: {signal.rationale} (Urgency: {signal.urgency})")
                        else:
                            lines.append(f"- {signal}")
                    lines.append(f"")
                
                if intel.synthesized_market_impact:
                    lines.append(f"**Historical Context Impact:**")
                    lines.append(f"> {intel.synthesized_market_impact}")
                    lines.append(f"")
                
                lines.append(f"---")
                lines.append(f"")
        
        # Summary statistics
        lines.append("## 📈 Summary Statistics")
        lines.append("")
        
        sentiments = {}
        impacts = {}
        asset_classes = {}
        for intel in output.intelligence:
            if isinstance(intel, MarketIntelligenceReport):
                sentiments[intel.sentiment.value] = sentiments.get(intel.sentiment.value, 0) + 1
                impacts[intel.impact_level.value] = impacts.get(intel.impact_level.value, 0) + 1
                asset_classes[intel.primary_asset_class.value] = asset_classes.get(intel.primary_asset_class.value, 0) + 1
        
        lines.append("**By Sentiment:** " + ", ".join(f"{k}: {v}" for k, v in sorted(sentiments.items())))
        lines.append("**By Impact:** " + ", ".join(f"{k}: {v}" for k, v in sorted(impacts.items())))
        lines.append("**By Asset Class:** " + ", ".join(f"{k}: {v}" for k, v in sorted(asset_classes.items())))
        lines.append("")
    
    # Source breakdown
    lines.append("## 📰 Source Breakdown")
    lines.append("")
    by_source: Dict[str, int] = {}
    for a in output.articles:
        by_source[a.source_name] = by_source.get(a.source_name, 0) + 1
    for source, count in sorted(by_source.items()):
        lines.append(f"- **{source}:** {count} articles")
    
    lines.append("")
    lines.append("---")
    lines.append("*Report generated by Ethiopian Financial Intelligence Bureau*")
    
    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")
    root_report.write_text(report_text, encoding="utf-8")
    logger.info("Saved human-readable report to %s", report_path)


def persist_intelligence(output: PipelineOutput) -> int:
    # Save if SQLite is enabled OR if DATABASE_URL is set (PostgreSQL)
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return 0
    init_db()
    saved_count = 0
    
    # Use the intelligence_article_map if available (from new schema)
    intelligence_article_map = getattr(output, 'intelligence_article_map', {})
    
    for intel in output.intelligence:
        if isinstance(intel, MarketIntelligenceReport):
            # Try to get the matching article from the map
            matching_article = intelligence_article_map.get(id(intel))
            
            # If not in map, try headline matching as fallback
            if not matching_article:
                for article in output.articles:
                    if article.headline in intel.executive_summary or intel.executive_summary[:100] in article.headline:
                        matching_article = article
                        break
            
            # If still not found, skip this intelligence item
            if not matching_article:
                logger.warning("Could not find matching article for intelligence: %s", intel.executive_summary[:100])
                continue
            
            # Use the new save_intelligence_report function if available
            if save_intelligence_report:
                record_dict = _intel_to_db_record(intel, matching_article)
                if save_intelligence_report(record_dict):
                    saved_count += 1
            elif save_record:
                record_dict = _intel_to_db_record(intel, matching_article)
                if save_record(record_dict):
                    saved_count += 1
    
    logger.info("Persisted %d intelligence reports to database.", saved_count)
    return saved_count


async def broadcast_intelligence(output: PipelineOutput) -> int:
    reports = []
    # Use the intelligence_article_map if available (from new schema)
    intelligence_article_map = getattr(output, 'intelligence_article_map', {})
    
    for intel in output.intelligence:
        if isinstance(intel, MarketIntelligenceReport):
            # Try to get the matching article from the map
            matching_article = intelligence_article_map.get(id(intel))
            
            # If not in map, skip this intelligence item
            if not matching_article:
                logger.warning("Could not find matching article for Telegram broadcast: %s", intel.executive_summary[:100])
                continue
            
            # Build a rich report dict with ALL fields for Telegram
            report = {
                "source_name": matching_article.source_name,
                "headline": matching_article.headline,
                "url": str(matching_article.url),
                "normalized_date": matching_article.published_date or "Unknown",
                "event_type": intel.event_type.value,
                "sentiment": intel.sentiment.value,
                "impact_level": intel.impact_level.value,
                "primary_asset_class": intel.primary_asset_class.value,
                "time_horizon": intel.time_horizon.value,
                "confidence_score": intel.confidence_score,
                "affected_entities": list(intel.affected_entities),
                "executive_summary": intel.executive_summary,
                "trading_implication": intel.trading_implication,
                "key_metrics": [
                    m.model_dump() if hasattr(m, 'model_dump') else m 
                    for m in (intel.key_metrics or [])
                ],
                "actionable_signals": [
                    s.model_dump() if hasattr(s, 'model_dump') else s 
                    for s in (intel.actionable_signals or [])
                ],
                "historical_connections": [
                    h.model_dump() if hasattr(h, 'model_dump') else h 
                    for h in (intel.historical_connections or [])
                ],
                "synthesized_market_impact": intel.synthesized_market_impact,
            }
            reports.append(report)
    
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


def handle_rate_limit_error(error_msg: str) -> None:
    """
    Handle OpenRouter rate limit errors with helpful message.
    
    Args:
        error_msg: Error message from the API
    """
    if "Rate limit exceeded" in error_msg or "429" in error_msg:
        logger.error("=" * 60)
        logger.error("OPENROUTER RATE LIMIT EXCEEDED")
        logger.error("=" * 60)
        logger.error("Free tier limit: 50 requests/day")
        logger.error("")
        logger.error("Solutions:")
        logger.error("1. Wait for daily reset (midnight UTC)")
        logger.error("2. Add $10 credits at https://openrouter.ai/account")
        logger.error("   (unlocks 1,000 requests/day)")
        logger.error("3. Use OpenAI instead (add OPENAI_API_KEY to .env)")
        logger.error("4. Reduce --llm-max to use fewer requests")
        logger.error("=" * 60)


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
    parser.add_argument("--new-schema", action="store_true", help="Use enhanced schema with article mapping for better persistence and reports")
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
            # If using DB mode and no new records, skip Telegram
            if db_saved == 0:
                logger.info("Skipping Telegram - all intelligence already in database")
                telegram_sent = 0

        if args.telegram and output.intelligence and telegram_sent == 0:
            # Only broadcast if we haven't already sent Telegram alerts
            # If --db is enabled, only broadcast if we saved new records
            if args.db and db_saved == 0:
                # Already logged above, skip
                pass
            else:
                # No DB mode or new records saved - broadcast
                logger.info("Broadcasting %d intelligence reports via Telegram", len(output.intelligence))
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

        # Show intelligence summary if available
        if output.intelligence:
            print(f"\n  {'=' * 55}")
            print(f"  INTELLIGENCE SUMMARY")
            print(f"  {'=' * 55}")
            sentiment_counts = {}
            impact_counts = {}
            for intel in output.intelligence:
                if isinstance(intel, MarketIntelligenceReport):
                    s = intel.sentiment.value.upper()
                    i = intel.impact_level.value.upper()
                    sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
                    impact_counts[i] = impact_counts.get(i, 0) + 1
            print(f"  Sentiment: {sentiment_counts}")
            print(f"  Impact:    {impact_counts}")

        logger.info("Pipeline completed successfully")
        
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Pipeline failed with error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()