"""Target feeds, keyword signals, and pipeline constants."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = PROJECT_ROOT / "output.json"

# HTTP
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

REQUEST_TIMEOUT = 20.0

# ---------------------------------------------------------------------------
# Keyword signals for capital-market relevance (prefilter scoring)
# ---------------------------------------------------------------------------
# Strong signals — at least one required for Tier 2/3 sources
STRONG_SIGNAL_KEYWORDS = [
    "securities", "exchange", "esx", "ecma", "listing", "listed", "ipo",
    "bond", "treasury", "t-bill", "t-bond", "equity", "dividend",
    "capital market", "investment bank", "broker", "custodian", "cmsp",
    "prospectus", "registration of securities", "shareholder",
    "annual report", "annual business", "business performance", "business plan",
    "financial statement", "semi annual", "semi-annual", "fiscal year",
    "receivable", "sustainable securities", "green bond", "corporate action",
    "monetary", "interest rate", "inflation", "forex", "telebirr",
    "notice of registration", "license", "nbe", "monetary policy",
    "t bill", "auctions", "budget",
]

# Weak signals — boost score but insufficient alone for Tier 2/3
WEAK_SIGNAL_KEYWORDS = [
    "share", "bank", "insurance", "birr", "financial", "revenue", "profit",
]

LOW_SIGNAL_KEYWORDS = [
    "partnership", "mou", "collaboration", "workshop", "visit", "delegation",
    "ceo", "ambassador", "cloud", "5g", "sim", "broadband", "festival",
    "holiday", "sports", "entertainment", "launch", "sign", "expand",
    "huawei", "mastercard", "dstv", "multichoice", "inspur",
]

# Headlines matching these patterns are dropped before LLM ingestion
NOISE_PATTERNS = [
    r"^our recent news$",
    r"^read more$",
    r"^click here$",
    r"^download$",
    r"^subscribe",
    r"^sign up",
    r"^menu$",
    r"^home$",
    r"^contact us$",
    r"^about us$",
    r"^privacy policy$",
    r"^investor relations$",
    r"^press release$",
    r"^latest news$",
    r"^organizational structure$",
    r"^management\b",
    r"^trading and operations$",
    r"^\d+$",
    r"\.\.\.$",  # truncated teaser headlines
]

# URL path fragments that indicate non-article pages
NOISE_URL_FRAGMENTS = [
    "/about/", "/contact", "/cart.php", "/web-builder/", "/myportal.",
    "/category/", "/tag/", "/author/", "/wp-login", "/#",
    "tiktok.com", "youtube.com", "facebook.com", "twitter.com", "instagram.com",
]

# Minimum relevance score (0–1) to pass prefilter for Tier 2/3 sources
MIN_RELEVANCE_SCORE = 0.40

# ---------------------------------------------------------------------------
# Scraper source definitions
# ---------------------------------------------------------------------------
TARGET_SOURCES = [
    {
        "source_name": "ESX",
        "url": "https://esx.et/news-and-resources/latest-news/",
        "tier": "Tier_1_Regulatory",
        "container_tag": "article",
        "title_tag": "h2",
        "link_tag": "a",
        "base_url": "https://esx.et",
        "require_keyword_match": False,
    },
    {
        "source_name": "ECMA_NEWS",
        "url": "https://ecma.gov.et/category/news/",
        "tier": "Tier_1_Regulatory",
        "container_tag": "article",
        "title_tag": "h2",
        "link_tag": "a",
        "base_url": "https://ecma.gov.et",
        "require_keyword_match": False,
    },
    {
        "source_name": "ECMA_MEDIA",
        "url": "https://ecma.gov.et/media/",
        "tier": "Tier_1_Regulatory",
        "container_tag": "tr",
        "title_tag": "td",
        "link_tag": "a",
        "base_url": "https://ecma.gov.et",
        "require_keyword_match": False,
    },
    {
        "source_name": "NBE",
        "url": "https://nbe.gov.et/news/",
        "tier": "Tier_1_Regulatory",
        "container_tag": "div",
        "title_tag": "h3",
        "link_tag": "a",
        "base_url": "https://nbe.gov.et",
        "require_keyword_match": False,
    },
    {
        "source_name": "CAPITAL_ETHIOPIA",
        "url": "https://capitalethiopia.com/category/news-news/",
        "tier": "Tier_2_Financial_Media",
        "container_tag": "div",
        "title_tag": "h3",
        "link_tag": "a",
        "base_url": "https://capitalethiopia.com",
        "require_keyword_match": True,
    },
    {
        "source_name": "THE_REPORTER_ETHIOPIA",
        "url": "https://www.thereporterethiopia.com/category/news/",
        "tier": "Tier_2_Financial_Media",
        "container_tag": "article",
        "title_tag": "h3",
        "link_tag": "a",
        "base_url": "https://www.thereporterethiopia.com",
        "require_keyword_match": True,
    },
    {
        "source_name": "ETHIO_TELECOM_IR",
        "url": "https://www.ethiotelecom.et/investor-relations/",
        "tier": "Tier_3_Issuer_IR",
        "container_tag": "article",
        "title_tag": "h2",
        "link_tag": "a",
        "base_url": "https://www.ethiotelecom.et",
        "container_css": "article.eael-grid-post",
        "require_keyword_match": True,
    },
    {
        "source_name": "ETHIO_TELECOM_PRESS",
        "url": "https://www.ethiotelecom.et/press-release/",
        "tier": "Tier_3_Issuer_IR",
        "container_tag": "article",
        "title_tag": "h2",
        "link_tag": "a",
        "base_url": "https://www.ethiotelecom.et",
        "container_css": "article.eael-grid-post",
        "require_keyword_match": True,
    },
    {
        "source_name": "AWASH_BANK_IR",
        "url": "https://awashbank.com/news/",
        "tier": "Tier_3_Issuer_IR",
        "container_tag": "article",
        "title_tag": "h2",
        "link_tag": "a",
        "base_url": "https://awashbank.com",
        "require_keyword_match": True,
    },
]

# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------
# Default model for OpenAI API
LLM_MODEL = "gpt-4o-mini"

# OpenRouter API configuration (set OPENROUTER_API_KEY environment variable)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

# Free OpenRouter model (no credits needed - rate limited)
# See https://openrouter.ai/models?order=free for available free models
OPENROUTER_FREE_MODEL = "openrouter/free"

# Legacy OpenAI configuration
LLM_BASE_URL = None  # set to Ollama URL e.g. "http://localhost:11434/v1"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"

# ---------------------------------------------------------------------------
# SQLite persistence (optional)
# ---------------------------------------------------------------------------
USE_SQLITE = True  # Set to True to enable SQLite persistence
SQLITE_PATH = PROJECT_ROOT / "data" / "financial_intelligence.db"

# ---------------------------------------------------------------------------
# Telegram alerting (optional)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
TELEGRAM_MIN_IMPACT = "MEDIUM"  # Minimum impact level to broadcast
