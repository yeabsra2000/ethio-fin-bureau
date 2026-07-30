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


def _truncate_at_word_boundary(text: str, max_length: int) -> str:
    """
    Truncate text at a word boundary to avoid cutting off mid-word.
    
    Args:
        text: Text to truncate
        max_length: Maximum character length (0 = no truncation)
        
    Returns:
        Truncated text with ellipsis if needed, or full text if max_length is 0
    """
    # If max_length is 0 or text is shorter than limit, return full text
    if max_length == 0 or len(text) <= max_length:
        return text
    
    # Truncate to max_length and find the last space
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > 0:
        # Truncate at the last word boundary
        truncated = truncated[:last_space]
    
    return truncated.rstrip() + "..."


def _format_report_message(report: Dict[str, Any]) -> str:
    """Format a single intelligence report as a Telegram message."""
    headline = report.get("headline", "No headline")
    source = report.get("source_name", "Unknown")
    sentiment = report.get("sentiment", "NEUTRAL")
    impact = report.get("impact_level", "LOW")
    asset_class = report.get("primary_asset_class", "Unknown")
    summary = report.get("executive_summary", "No summary available")
    trading_imp = report.get("trading_implication", "No trading implication")
    date = report.get("normalized_date", "Unknown")
    
    # Truncate long text at word boundaries (0 = no truncation, show full text)
    # Telegram allows up to 4096 characters per message, so we can show full summaries
    summary = _truncate_at_word_boundary(summary, 0)  # No truncation - show full summary
    trading_imp = _truncate_at_word_boundary(trading_imp, 0)  # No truncation - show full text
    
    message = f"""<b>📊 Financial Intelligence Alert</b>

<b>Headline:</b> {headline}

<b>Source:</b> {source}
<b>Date:</b> {date}
<b>Sentiment:</b> {sentiment}
<b>Impact Level:</b> {impact}
<b>Asset Class:</b> {asset_class}

<b>Executive Summary:</b>
{summary}

<b>Trading Implication:</b>
{trading_imp}

<i>Ethiopian Financial Intelligence Bureau</i>"""
    
    return message


async def broadcast_alerts(
    reports: List[Dict[str, Any]],
    min_impact: str = "MEDIUM",
) -> int:
    """
    Broadcast intelligence reports via Telegram.
    
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
    
    sent_count = 0
    for report in filtered_reports:
        message = _format_report_message(report)
        if await _send_telegram_message(bot_token, chat_id, message):
            sent_count += 1
    
    logger.info("Successfully sent %d/%d Telegram alerts.", sent_count, len(filtered_reports))
    return sent_count