"""LLM execution layer using Instructor for structured output."""

import logging
import os
from typing import List, Optional, Tuple

from ethio_fin_bureau.config import LLM_BASE_URL, LLM_MODEL, OPENAI_API_KEY_ENV
from ethio_fin_bureau.llm.schemas import (
    MarketIntelligenceReport,
    ScrapedArticle,
    FinancialSentiment,
    MarketImpact,
    AssetCategory,
    EventType,
    TimeHorizon,
    NumericalIndicator,
    ActionableSignal,
)

logger = logging.getLogger(__name__)

# OpenRouter default model
OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-preview-02-05"


def _build_client():
    """Lazy-init OpenAI/Instructor client; returns None if unavailable."""
    from ethio_fin_bureau.config import OPENROUTER_API_KEY_ENV, OPENROUTER_BASE_URL, OPENROUTER_FREE_MODEL

    # Try OpenRouter first, then legacy OpenAI, then Ollama
    api_key = os.environ.get(OPENROUTER_API_KEY_ENV) or os.environ.get(OPENAI_API_KEY_ENV)
    if not api_key and not LLM_BASE_URL:
        return None

    try:
        import instructor
        from openai import OpenAI

        kwargs = {}
        base_url = os.environ.get("LLM_BASE_URL") or LLM_BASE_URL

        # If using OpenRouter, set the base URL
        if os.environ.get(OPENROUTER_API_KEY_ENV):
            base_url = OPENROUTER_BASE_URL
            kwargs["base_url"] = base_url
        elif base_url:
            kwargs["base_url"] = base_url

        if api_key:
            kwargs["api_key"] = api_key
        else:
            kwargs["api_key"] = "ollama"

        logger.info("Initializing LLM client with base_url=%s", kwargs.get("base_url", "default"))
        client = OpenAI(**kwargs)
        return instructor.from_openai(client)
    except ImportError:
        logger.warning("instructor/openai not installed — LLM analysis skipped.")
        return None


def _get_model() -> str:
    """Get the appropriate model name based on available API key."""
    from ethio_fin_bureau.config import OPENROUTER_API_KEY_ENV, OPENROUTER_FREE_MODEL

    if os.environ.get(OPENROUTER_API_KEY_ENV):
        return OPENROUTER_FREE_MODEL
    return LLM_MODEL


def _create_fallback_report(headline: str, source_name: str) -> MarketIntelligenceReport:
    """Create a fallback report when LLM analysis fails, preserving basic info."""
    return MarketIntelligenceReport(
        event_type=EventType.MARKET_NEWS,
        executive_summary=(
            f"Unclassified alert from {source_name}. "
            f"The headline '{headline[:100]}' could not be analyzed by the AI model. "
            "Manual review recommended for this item."
        ),
        sentiment=FinancialSentiment.NEUTRAL,
        impact_level=MarketImpact.LOW,
        primary_asset_class=AssetCategory.GENERAL_MACRO,
        time_horizon=TimeHorizon.SHORT_TERM,
        confidence_score=0.0,
        affected_entities=[source_name],
        key_metrics=None,
        trading_implication="No AI-generated analysis available. Review the source article directly.",
        actionable_signals=[],
        historical_connections=[],
        synthesized_market_impact=None,
    )


# ---------------------------------------------------------------------------
# Expert system prompt — designed to produce genuinely useful intelligence
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a Senior Financial Analyst at a top-tier East African investment bank.

Your role: Analyze Ethiopian financial news and produce institutional-grade intelligence.

## Your analysis MUST include:

1. **Event Classification**: Identify what type of event this is (regulatory change, monetary policy, listing, etc.)

2. **Executive Summary** (2-3 sentences): 
   - State WHAT happened, WHO is involved, and WHY it matters
   - Include the key numbers (interest rates, volumes, percentages, amounts)
   - Explain the real-world impact on markets and investors

3. **Sentiment & Impact**: 
   - BULLISH = positive for asset prices / economic outlook
   - BEARISH = negative for asset prices / economic outlook
   - NEUTRAL = informational, no clear directional bias
   - Impact level: CRITICAL > HIGH > MEDIUM > LOW

4. **Asset Class**: Map to the correct market (equities, forex, bonds, banking, monetary policy, or general macro)

5. **Time Horizon**: When will this impact materialize? (immediate, short-term, medium-term, long-term)

6. **Confidence Score** (0.0-1.0): 
   - 0.8-1.0: Official announcement with specific numbers
   - 0.5-0.7: Well-sourced news with clear implications
   - 0.2-0.4: Rumors, speculation, or unclear implications
   - 0.0-0.1: Unverifiable or too vague to assess

7. **Key Metrics**: Extract ALL numerical data points. For example:
   - "NBE sets interest rate at 15%" → name="interest rate", value="15%", context="new policy rate"
   - "50 million ETB raised in IPO" → name="offering size", value="50M ETB", context="IPO proceeds"
   - "Inflation at 23.5% YoY" → name="inflation rate", value="23.5%", context="year-on-year change"

8. **Trading Implication**: A specific, actionable 1-2 sentence recommendation. 
   - NOT generic like "monitor the situation"
   - SPECIFIC like "Expect increased demand for T-bills as rates rise to 15% — consider reallocating fixed-income portfolios toward short-term maturities"

9. **Actionable Signals**: List specific actions for different asset types:
   - signal_type: 'buy', 'sell', 'hold', 'watch', 'hedge', 'arbitrage', or 'avoid'
   - asset: which specific instrument/market
   - rationale: why this action makes sense
   - urgency: 'immediate', 'this_week', 'this_month', or 'monitor'

## CRITICAL RULES:
- Be factual and concise. Do NOT speculate beyond what the news supports.
- If the news has no clear market implication, say so honestly.
- Extract ALL numbers mentioned — they are the most valuable part of financial news.
- The trading_implication should be SPECIFIC enough that a trader could act on it.
- Confidence score should reflect how reliable the information source is."""


def _build_historical_context(article: ScrapedArticle) -> str:
    """
    Search for similar historical records to provide context for analysis.
    Returns a formatted string of historical context, or empty string.
    """
    try:
        from ethio_fin_bureau.db.database import search_similar_records
        similar_records = search_similar_records(article.headline, limit=3)
        
        if not similar_records:
            return ""
        
        lines = [
            "\n\n[HISTORICAL CONTEXT — Similar past events for reference]",
            "The following similar events from the past may provide trend context:\n"
        ]
        
        for i, record in enumerate(similar_records, 1):
            sentiment_emoji = {
                "BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"
            }.get(record.get('sentiment', '').upper(), "⚪")
            
            lines.append(
                f"{i}. {sentiment_emoji} [{record['impact_level']}] {record['headline'][:80]}"
            )
            lines.append(f"   Date: {record.get('created_at', 'unknown')}")
            summary = (record.get('executive_summary') or '')[:200]
            if summary:
                lines.append(f"   Summary: {summary}...")
            lines.append(f"   Similarity: {record['similarity']:.0%} match\n")
        
        lines.append(
            "Consider these patterns when analyzing: Is this a continuation of a trend, "
            "a reversal, or a new development? Synthesize the combined market impact."
        )
        
        return "\n".join(lines)
    except Exception as e:
        logger.debug("Could not retrieve historical context: %s", e)
        return ""


def _build_user_prompt(article: ScrapedArticle, historical_context: str = "") -> str:
    """Build a detailed user prompt for the LLM."""
    parts = [
        f"## Source Information",
        f"Source: {article.source_name} ({article.tier})",
        f"Headline: {article.headline}",
        f"URL: {article.url}",
        f"Date: {article.published_date or 'unknown'}",
        f"Matched Keywords: {', '.join(article.keywords_matched) or 'none'}",
        f"Relevance Score: {article.relevance_score:.2f}/1.0",
    ]
    
    if historical_context:
        parts.append(historical_context)
    
    parts.append(
        "\n## Instructions\n"
        "Analyze this news item and produce structured intelligence. "
        "Be specific. Extract all numbers. Provide actionable trading signals."
    )
    
    return "\n".join(parts)


def analyze_articles(
    articles: List[ScrapedArticle],
    max_items: int = 10,
) -> List[MarketIntelligenceReport]:
    """
    Run LLM structured analysis on top-scored articles.
    Returns list of MarketIntelligenceReport objects.
    Each report includes event_type, time_horizon, confidence_score,
    key_metrics, actionable_signals, and historical context.
    
    Args:
        articles: List of scraped articles to analyze
        max_items: Maximum number of articles to analyze
        
    Returns:
        List of MarketIntelligenceReport objects (one per article)
    """
    client = _build_client()
    if client is None:
        logger.info("LLM analysis skipped (no API key or base URL configured).")
        return []

    results: List[MarketIntelligenceReport] = []
    batch = sorted(articles, key=lambda a: a.relevance_score, reverse=True)[:max_items]

    for article in batch:
        historical_context = _build_historical_context(article)
        user_prompt = _build_user_prompt(article, historical_context)
        model = _get_model()
        
        try:
            intel = client.chat.completions.create(
                model=model,
                response_model=MarketIntelligenceReport,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_retries=2,
            )
            if intel is None:
                raise ValueError("LLM returned None response")
            results.append(intel)
        except Exception as exc:
            logger.warning("LLM analysis failed for '%s': %s", article.headline[:50], exc)
            results.append(_create_fallback_report(article.headline, article.source_name))

    return results


def analyze_articles_new(articles: List[ScrapedArticle], max_items: int = 10) -> List[Tuple[MarketIntelligenceReport, ScrapedArticle]]:
    """
    Run LLM structured analysis on top-scored articles using the new schema.
    Returns list of tuples: (MarketIntelligenceReport, ScrapedArticle)
    Includes long-term memory by searching for similar historical records.
    
    Note: This is the recommended function for new code. It returns the article
    along with the intelligence report for traceability.
    """
    client = _build_client()
    if client is None:
        logger.info("LLM analysis skipped (no API key or base URL configured).")
        return [(_create_fallback_report(a.headline, a.source_name), a) for a in articles[:max_items]]

    results: List[Tuple[MarketIntelligenceReport, ScrapedArticle]] = []
    batch = sorted(articles, key=lambda a: a.relevance_score, reverse=True)[:max_items]

    for article in batch:
        # Build historical context
        historical_context = _build_historical_context(article)
        user_prompt = _build_user_prompt(article, historical_context)
        model = _get_model()
        
        try:
            intel = client.chat.completions.create(
                model=model,
                response_model=MarketIntelligenceReport,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_retries=2,
            )
            if intel is None:
                raise ValueError("LLM returned None response")
            results.append((intel, article))
        except Exception as exc:
            logger.warning("LLM analysis failed for '%s': %s", article.headline[:50], exc)
            results.append((_create_fallback_report(article.headline, article.source_name), article))

    return results