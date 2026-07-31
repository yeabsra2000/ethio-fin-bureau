"""Telegram alert delivery for the Ethiopian Financial Intelligence Bureau."""

import logging
import os
from typing import Any, Dict, List

import httpx

from ethio_fin_bureau.config import (
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
)

logger = logging.getLogger(__name__)


async def _send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    """
    Send a single message to a Telegram chat.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        text: Message text
        parse_mode: Parse mode (HTML or Markdown)
        
    Returns:
        True if sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                return True
            else:
                logger.error("Telegram API error: %s", result.get("description"))
                return False
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def _format_impact_emoji(impact: str) -> str:
    """Get appropriate emoji for impact level."""
    impact_map = {
        "CRITICAL": "🚨",
        "HIGH": "🔥",
        "MEDIUM": "📌",
        "LOW": "💡",
    }
    return impact_map.get(impact.upper(), "📊")


def _format_sentiment_emoji(sentiment: str) -> str:
    """Get appropriate emoji for sentiment."""
    sentiment_map = {
        "BULLISH": "🟢",
        "BEARISH": "🔴",
        "NEUTRAL": "⚪",
    }
    return sentiment_map.get(sentiment.upper(), "⚪")


def _format_asset_class_emoji(asset_class: str) -> str:
    """Get appropriate emoji for asset class."""
    asset_map = {
        "equities_esx": "🏢",
        "monetary_nbe": "🏦",
        "debt_bonds": "📜",
        "forex_etb": "💵",
        "banking_sector": "🏛️",
        "general_macro": "🌍",
    }
    return asset_map.get(asset_class, "📊")


def _get_asset_class_display(asset_class: str) -> str:
    """Get human-readable asset class name."""
    display_map = {
        "equities_esx": "ESX Equities",
        "monetary_nbe": "NBE Monetary Policy",
        "debt_bonds": "Debt & Bonds",
        "forex_etb": "FX / ETB",
        "banking_sector": "Banking Sector",
        "general_macro": "General Macro",
    }
    return display_map.get(asset_class, asset_class.replace("_", " ").title())


def _format_report_message(report: Dict[str, Any]) -> str:
    """
    Format a single intelligence report as a rich Telegram message.
    Designed to be genuinely useful for institutional investors.
    """
    # Extract all fields with defaults
    headline = report.get("headline", "No headline")
    source = report.get("source_name", "Unknown")
    sentiment = report.get("sentiment", "NEUTRAL")
    impact = report.get("impact_level", "LOW")
    asset_class = report.get("primary_asset_class", "general_macro")
    event_type = report.get("event_type", "market_news")
    time_horizon = report.get("time_horizon", "short_term")
    confidence = report.get("confidence_score", 0.0)
    summary = report.get("executive_summary", "No summary available")
    trading_imp = report.get("trading_implication", "No trading implication")
    date = report.get("normalized_date", "Unknown")
    affected_entities = report.get("affected_entities", [])
    key_metrics = report.get("key_metrics", [])
    actionable_signals = report.get("actionable_signals", [])
    url = report.get("url", None)
    synthesized_impact = report.get("synthesized_market_impact", None)
    historical_connections = report.get("historical_connections", [])

    # Emojis
    impact_emoji = _format_impact_emoji(impact)
    sentiment_emoji = _format_sentiment_emoji(sentiment)
    asset_emoji = _format_asset_class_emoji(asset_class)
    
    # Event type display
    event_display = event_type.replace("_", " ").title()
    
    # Time horizon display
    horizon_display = {
        "immediate": "⚡ Immediate",
        "short_term": "📅 Short-term (days-weeks)",
        "medium_term": "📆 Medium-term (weeks-months)",
        "long_term": "🗓️ Long-term (months-years)",
    }.get(time_horizon, time_horizon.replace("_", " ").title())

    # Asset class display
    asset_display = _get_asset_class_display(asset_class)

    # Confidence stars
    confidence_stars = "★" * max(1, round(confidence * 5)) + "☆" * max(0, 5 - round(confidence * 5))
    confidence_pct = f"{confidence * 100:.0f}%"

    # Build the message
    parts = [
        f"{impact_emoji} <b>Financial Intelligence Alert</b>",
        f"{sentiment_emoji} Sentiment: <b>{sentiment}</b> | Impact: <b>{impact}</b>",
        "",
        f"<b>📰 {headline}</b>",
        "",
    ]

    # Source line
    source_line = f"<b>Source:</b> {source} | <b>Date:</b> {date}"
    if url:
        source_line += f"\n<a href=\"{url}\">🔗 View Source Article</a>"
    parts.append(source_line)
    parts.append("")

    # Classification
    parts.append(
        f"<b>Classification:</b> {asset_emoji} {asset_display} | {event_display}"
    )
    parts.append(f"<b>Time Horizon:</b> {horizon_display}")
    parts.append(f"<b>Confidence:</b> {confidence_stars} ({confidence_pct})")
    parts.append("")

    # Affected entities
    if affected_entities:
        entities_str = ", ".join(affected_entities[:5])
        if len(affected_entities) > 5:
            entities_str += f" +{len(affected_entities) - 5} more"
        parts.append(f"<b>Affected:</b> {entities_str}")
        parts.append("")

    # Executive Summary
    parts.append(f"<b>📋 Executive Summary</b>")
    parts.append(summary)
    parts.append("")

    # Key Metrics
    if key_metrics:
        parts.append(f"<b>📊 Key Metrics</b>")
        for metric in key_metrics:
            if isinstance(metric, dict):
                name = metric.get("name", "Metric")
                value = metric.get("value", "")
                context = metric.get("context", "")
                if context:
                    parts.append(f"• <b>{name}:</b> {value} <i>({context})</i>")
                else:
                    parts.append(f"• <b>{name}:</b> {value}")
            else:
                parts.append(f"• {metric}")
        parts.append("")

    # Trading Implication
    parts.append(f"<b>🎯 Trading Implication</b>")
    parts.append(trading_imp)
    parts.append("")

    # Actionable Signals
    if actionable_signals:
        parts.append(f"<b>⚡ Actionable Signals</b>")
        urgency_emoji = {"immediate": "🚨", "this_week": "📅", "this_month": "📆", "monitor": "👁️"}
        for signal in actionable_signals:
            if isinstance(signal, dict):
                sig_type = signal.get("signal_type", "watch").upper()
                asset = signal.get("asset", "N/A")
                rationale = signal.get("rationale", "")
                urgency = signal.get("urgency", "monitor")
                u_emoji = urgency_emoji.get(urgency, "👁️")
                parts.append(f"• <b>{sig_type}</b> {asset}: {rationale} ({u_emoji})")
            else:
                parts.append(f"• {signal}")
        parts.append("")

    # Synthesized Market Impact (from historical context)
    if synthesized_impact:
        parts.append(f"<b>🔗 Historical Context Impact</b>")
        parts.append(synthesized_impact)
        parts.append("")

    # Historical connections
    if historical_connections:
        parts.append(f"<b>📜 Related Historical Events</b>")
        for conn in historical_connections:
            if isinstance(conn, dict):
                conn_headline = conn.get("headline", "Unknown")
                conn_similarity = conn.get("similarity", 0)
                conn_correlation = conn.get("correlation_type", "coincidental").replace("_", " ")
                parts.append(f"• {conn_headline[:60]} ({conn_similarity:.0%} match, {conn_correlation})")
            else:
                parts.append(f"• {conn}")
        parts.append("")

    # Footer
    parts.append("<i>Ethiopian Financial Intelligence Bureau</i>")

    message = "\n".join(parts)

    # Telegram has a 4096 character limit per message
    if len(message) > 4096:
        # Truncate gracefully - keep the most important parts
        message = message[:4090] + "\n\n<i>...message truncated due to length. View full report in the web dashboard.</i>"

    return message


def _format_digest_message(reports: List[Dict[str, Any]]) -> str:
    """
    Format multiple reports as a consolidated digest message.
    Used when there are 2+ reports for efficiency.
    """
    digest_lines = [
        "<b>📊 Financial Intelligence Digest</b>",
        f"<i>{len(reports)} new intelligence reports</i>\n",
    ]

    for i, report in enumerate(reports, 1):
        headline = report.get("headline", "No headline")[:100]
        source = report.get("source_name", "Unknown")
        sentiment = report.get("sentiment", "NEUTRAL")
        impact = report.get("impact_level", "LOW")
        event_type = report.get("event_type", "market_news").replace("_", " ").title()
        asset_class = report.get("primary_asset_class", "general_macro")
        summary = report.get("executive_summary", "No summary available")[:250]
        trading_imp = report.get("trading_implication", "No trading implication")[:150]
        confidence = report.get("confidence_score", 0.0)
        key_metrics = report.get("key_metrics", [])
        url = report.get("url", None)
        
        sentiment_emoji = _format_sentiment_emoji(sentiment)
        impact_emoji = _format_impact_emoji(impact)
        asset_emoji = _format_asset_class_emoji(asset_class)
        
        digest_lines.append(f"\n{sentiment_emoji} <b>#{i}: {headline}</b>")
        digest_lines.append(f"{impact_emoji} {source} | {asset_emoji} {_get_asset_class_display(asset_class)} | {event_type}")
        digest_lines.append(f"Sentiment: {sentiment} | Impact: {impact} | Confidence: {confidence * 100:.0f}%")
        
        # Key metrics in digest (compact format)
        if key_metrics:
            metric_strs = []
            for m in key_metrics[:3]:
                if isinstance(m, dict):
                    metric_strs.append(f"{m.get('name', '')}: {m.get('value', '')}")
                else:
                    metric_strs.append(str(m))
            if metric_strs:
                digest_lines.append(f"📊 Metrics: {' | '.join(metric_strs)}")
        
        digest_lines.append(f"📋 {summary}")
        digest_lines.append(f"🎯 {trading_imp}")
        
        if url:
            digest_lines.append(f"🔗 <a href=\"{url}\">View Source</a>")

    digest_lines.append("\n<i>Ethiopian Financial Intelligence Bureau</i>")
    
    message = "\n".join(digest_lines)

    # Telegram has a 4096 character limit per message
    if len(message) > 4096:
        # Truncate at the last complete report before the limit
        message = message[:4080] + "\n\n<i>...digest truncated. Some reports omitted.</i>"

    return message


async def broadcast_alerts(
    reports: List[Dict[str, Any]],
    min_impact: str = "MEDIUM",
) -> int:
    """
    Broadcast intelligence reports via Telegram.
    High/Critical impact reports are sent individually for prominence.
    Medium/Low impact reports are batched into a digest.
    
    Args:
        reports: List of intelligence report dictionaries
        min_impact: Minimum impact level to broadcast (LOW, MEDIUM, HIGH, CRITICAL)
        
    Returns:
        Number of alerts successfully sent
    """
    bot_token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV)
    
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram credentials not configured. Set %s and %s environment variables.",
            TELEGRAM_BOT_TOKEN_ENV,
            TELEGRAM_CHAT_ID_ENV,
        )
        return 0
    
    # Filter by impact level
    impact_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    try:
        min_index = impact_levels.index(min_impact.upper())
    except ValueError:
        min_index = 1  # Default to MEDIUM
    
    filtered_reports = []
    for report in reports:
        impact = report.get("impact_level", "LOW").upper()
        try:
            impact_index = impact_levels.index(impact)
            if impact_index >= min_index:
                filtered_reports.append(report)
        except ValueError:
            continue
    
    if not filtered_reports:
        logger.info("No reports meet the minimum impact threshold (%s).", min_impact)
        return 0

    logger.info("Broadcasting %d alerts via Telegram...", len(filtered_reports))
    
    # Separate HIGH/CRITICAL from MEDIUM/LOW
    high_priority = [r for r in filtered_reports if r.get("impact_level", "LOW").upper() in ("HIGH", "CRITICAL")]
    normal_priority = [r for r in filtered_reports if r.get("impact_level", "LOW").upper() not in ("HIGH", "CRITICAL")]
    
    sent_count = 0
    
    # Send HIGH/CRITICAL alerts individually (they deserve their own message)
    for report in high_priority:
        message = _format_report_message(report)
        if await _send_telegram_message(bot_token, chat_id, message):
            sent_count += 1
            logger.info("Sent individual high-priority alert: %s", report.get("headline", "")[:50])
    
    # Send MEDIUM/LOW alerts as a digest
    if normal_priority:
        if len(normal_priority) == 1:
            # Single normal report - use individual format
            message = _format_report_message(normal_priority[0])
            if await _send_telegram_message(bot_token, chat_id, message):
                sent_count += 1
        else:
            # Multiple reports - batch into digest
            message = _format_digest_message(normal_priority)
            if await _send_telegram_message(bot_token, chat_id, message):
                sent_count += len(normal_priority)
                logger.info("Sent consolidated digest with %d reports.", len(normal_priority))
    
    return sent_count