"""LLM execution layer using Instructor for structured output."""

import logging
import os
from typing import List, Optional

from ethio_fin_bureau.config import LLM_BASE_URL, LLM_MODEL, OPENAI_API_KEY_ENV
from ethio_fin_bureau.llm.schemas import (
    MarketIntelligence,
    MarketIntelligenceReport,
    ScrapedArticle,
    FinancialSentiment,
    MarketImpact,
    AssetCategory,
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
    """Create a neutral fallback report when LLM analysis fails."""
    return MarketIntelligenceReport(
        executive_summary=f"Unable to process: {headline[:80]}",
        sentiment=FinancialSentiment.NEUTRAL,
        impact_level=MarketImpact.LOW,
        primary_asset_class=AssetCategory.GENERAL_MACRO,
        affected_entities=[source_name],
        key_metrics=None,
        trading_implication="No actionable intelligence available."
    )


def analyze_financial_payload(
    headline: str,
    body: Optional[str] = None,
    normalized_date: str = "UNKNOWN",
    source_name: str = "UNKNOWN",
    tier: str = "Tier_1_Regulatory",
    keywords: Optional[List[str]] = None
) -> MarketIntelligenceReport:
    """
    Analyze a financial news payload and return structured intelligence.
    
    Args:
        headline: News headline
        body: Optional article body text
        normalized_date: ISO-8601 date string
        source_name: Source identifier
        tier: Source tier classification
        keywords: List of matched keywords
    
    Returns:
        MarketIntelligenceReport with structured analysis
    """
    client = _build_client()
    if client is None:
        logger.info("LLM analysis skipped (no API key or base URL configured).")
        return _create_fallback_report(headline, source_name)

    system_prompt = (
        "You are a Senior Financial Analyst & Quantitative Macro Strategist "
        "specializing in East African Capital Markets (ESX, NBE, ECMA). "
        "Analyze the provided financial news and produce structured intelligence "
        "for institutional investors and prediction models. "
        "Focus on: regulatory shifts, foreign exchange rules, liquidity moves, "
        "share issuances, banking sector dynamics, and monetary policy changes. "
        "Be factual, concise, and provide actionable insights."
    )

    user_prompt = (
        f"Source: {source_name} ({tier})\n"
        f"Headline: {headline}\n"
        f"Date: {normalized_date}\n"
        f"Keywords: {', '.join(keywords) if keywords else 'none'}\n"
        f"Body: {body[:500] if body else 'Not available'}"
    )

    model = _get_model()
    try:
        intel = client.chat.completions.create(
            model=model,
            response_model=MarketIntelligenceReport,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return intel
    except Exception as exc:
        logger.warning("LLM analysis failed for '%s': %s", headline[:50], exc)
        return _create_fallback_report(headline, source_name)


def analyze_articles(articles: List[ScrapedArticle], max_items: int = 10) -> List[MarketIntelligence]:
    """
    Run LLM structured analysis on top-scored articles.
    Skips gracefully when no API key / Ollama endpoint is configured.
    
    Note: This function returns the legacy MarketIntelligence format for backward compatibility.
    For new code, use analyze_financial_payload() which returns MarketIntelligenceReport.
    """
    client = _build_client()
    if client is None:
        logger.info("LLM analysis skipped (no API key or base URL configured).")
        return []

    results: List[MarketIntelligence] = []
    batch = sorted(articles, key=lambda a: a.relevance_score, reverse=True)[:max_items]

    system_prompt = (
        "You are a senior Ethiopian capital markets analyst. "
        "Given a news headline and metadata, produce structured intelligence "
        "for institutional investors and prediction models. Be factual and concise."
    )

    for article in batch:
        user_prompt = (
            f"Source: {article.source_name} ({article.tier})\n"
            f"Headline: {article.headline}\n"
            f"URL: {article.url}\n"
            f"Date: {article.published_date or 'unknown'}\n"
            f"Keywords: {', '.join(article.keywords_matched) or 'none'}"
        )
        model = _get_model()
        try:
            intel = client.chat.completions.create(
                model=model,
                response_model=MarketIntelligence,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            results.append(intel)
        except Exception as exc:
            logger.warning("LLM analysis failed for '%s': %s", article.headline[:50], exc)

    return results


def analyze_articles_new(articles: List[ScrapedArticle], max_items: int = 10) -> List[MarketIntelligenceReport]:
    """
    Run LLM structured analysis on top-scored articles using the new schema.
    Returns MarketIntelligenceReport objects with enhanced financial intelligence.
    """
    client = _build_client()
    if client is None:
        logger.info("LLM analysis skipped (no API key or base URL configured).")
        return [_create_fallback_report(a.headline, a.source_name) for a in articles[:max_items]]

    results: List[MarketIntelligenceReport] = []
    batch = sorted(articles, key=lambda a: a.relevance_score, reverse=True)[:max_items]

    system_prompt = (
        "You are a Senior Financial Analyst & Quantitative Macro Strategist "
        "specializing in East African Capital Markets (ESX, NBE, ECMA). "
        "Analyze the provided financial news and produce structured intelligence "
        "for institutional investors and prediction models. "
        "Focus on: regulatory shifts, foreign exchange rules, liquidity moves, "
        "share issuances, banking sector dynamics, and monetary policy changes. "
        "Be factual, concise, and provide actionable insights."
    )

    for article in batch:
        user_prompt = (
            f"Source: {article.source_name} ({article.tier})\n"
            f"Headline: {article.headline}\n"
            f"URL: {article.url}\n"
            f"Date: {article.published_date or 'unknown'}\n"
            f"Keywords: {', '.join(article.keywords_matched) or 'none'}"
        )
        model = _get_model()
        try:
            intel = client.chat.completions.create(
                model=model,
                response_model=MarketIntelligenceReport,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            results.append(intel)
        except Exception as exc:
            logger.warning("LLM analysis failed for '%s': %s", article.headline[:50], exc)
            results.append(_create_fallback_report(article.headline, article.source_name))

    return results