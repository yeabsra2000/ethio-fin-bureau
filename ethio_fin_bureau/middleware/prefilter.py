"""Keyword-based relevance scoring and noise rejection."""

import re
from typing import List, Tuple

from ethio_fin_bureau.config import (
    LOW_SIGNAL_KEYWORDS,
    MIN_RELEVANCE_SCORE,
    NOISE_PATTERNS,
    NOISE_URL_FRAGMENTS,
    STRONG_SIGNAL_KEYWORDS,
    WEAK_SIGNAL_KEYWORDS,
)

NOISE_RES = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]


def _normalize(text: str) -> str:
    """Collapse whitespace/hyphens for fuzzy keyword matching."""
    return re.sub(r"[\s\-_]+", " ", text.lower()).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    return _normalize(keyword) in _normalize(text)


def is_noise(headline: str, url: str) -> bool:
    """Return True if headline/URL looks like navigation or junk."""
    headline_clean = headline.strip()
    if len(headline_clean) < 15:
        return True

    # Percent-encoded slugs used as headlines are not readable
    if "%" in headline_clean and re.search(r"%[0-9a-f]{2}", headline_clean, re.I):
        return True

    lower = headline_clean.lower()
    for pattern in NOISE_RES:
        if pattern.search(lower):
            return True

    url_lower = url.lower()
    for fragment in NOISE_URL_FRAGMENTS:
        if fragment in url_lower:
            return True

    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return True

    if re.search(r"/20\d{2}/", path):
        return False

    slug = path.split("/")[-1].lower()
    section_pages = {
        "investor-relations", "press-release", "news", "media",
        "latest-news", "category", "about", "contact",
    }
    if slug in section_pages:
        return True

    if len(slug) < 10 and not path.endswith(".pdf"):
        return True

    return False


def score_relevance(headline: str, tier: str, require_match: bool) -> Tuple[float, List[str]]:
    """
    Score headline relevance for capital-market intelligence (0.0–1.0).
    Tier 1 regulatory sources always get a high baseline score.
    Tier 2/3 require at least one strong signal keyword to pass.
    
    Returns:
        Tuple of (score 0.0-1.0, list of matched keywords)
    """
    text = headline.lower()
    matched: List[str] = []

    # Count strong keyword hits
    strong_hits = 0
    for kw in STRONG_SIGNAL_KEYWORDS:
        if _contains_keyword(text, kw):
            strong_hits += 1
            matched.append(kw)

    # Count weak keyword hits (avoid duplicates already in matched)
    weak_hits = 0
    for kw in WEAK_SIGNAL_KEYWORDS:
        if _contains_keyword(text, kw):
            if kw not in matched:
                weak_hits += 1
                matched.append(kw)

    # Count low signal hits (detractors - these lower the score)
    low_hits = 0
    for kw in LOW_SIGNAL_KEYWORDS:
        if _contains_keyword(text, kw):
            low_hits += 1
            # Don't add low signal to matched list - they're not useful

    # Calculate score with diminishing returns for multiple hits
    # Base score starts at 0.05
    # Each strong keyword adds 0.25 (max 0.75 from strong)
    # Each weak keyword adds 0.08 (max 0.24 from weak)
    # Each low signal keyword subtracts 0.10 (max -0.30 from low)
    strong_contribution = min(strong_hits * 0.25, 0.75)
    weak_contribution = min(weak_hits * 0.08, 0.24)
    low_penalty = min(low_hits * 0.10, 0.30)
    
    score = max(0.0, min(1.0, 0.05 + strong_contribution + weak_contribution - low_penalty))

    # Tier 1 regulatory sources always get a high baseline score
    if tier == "Tier_1_Regulatory":
        score = max(score, 0.85)
        return score, matched

    # For Tier 2/3 with require_match, if no strong keywords found, score is capped at 0.3
    if require_match and strong_hits == 0:
        score = min(score, 0.30)
        return score, matched

    # For Tier 2/3 with require_match, minimum score threshold applies
    if require_match and score < MIN_RELEVANCE_SCORE:
        return score, matched

    return score, matched