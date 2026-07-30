"""Pydantic schemas for LLM structured market intelligence output."""

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class FinancialSentiment(str, Enum):
    """Financial sentiment classification for Ethiopian capital markets."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class MarketImpact(str, Enum):
    """Market impact level classification."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssetCategory(str, Enum):
    """Asset categories for Ethiopian capital markets."""
    EQUITIES_ESX = "equities_esx"
    MONETARY_NBE = "monetary_nbe"
    DEBT_BONDS = "debt_bonds"
    FOREX_ETB = "forex_etb"
    BANKING_SECTOR = "banking_sector"
    GENERAL_MACRO = "general_macro"


class EventType(str, Enum):
    """Event type classification for news items."""
    LISTING = "listing"
    LICENSING = "licensing"
    REGULATORY = "regulatory"
    MONETARY_POLICY = "monetary_policy"
    CORPORATE_ACTION = "corporate_action"
    FINANCIAL_RESULTS = "financial_results"
    MARKET_NEWS = "market_news"
    OTHER = "other"


class ScrapedArticle(BaseModel):
    """Cleaned article payload ready for LLM analysis."""

    source_name: str
    tier: str
    headline: str
    url: HttpUrl
    published_date: Optional[str] = Field(None, description="ISO-8601 YYYY-MM-DD")
    relevance_score: float = Field(ge=0.0, le=1.0)
    keywords_matched: List[str] = Field(default_factory=list)


class HistoricalConnection(BaseModel):
    """Represents a connection to a historical event."""
    
    headline: str = Field(description="Headline of the historical event")
    summary: str = Field(description="Brief summary of what happened")
    sentiment: FinancialSentiment = Field(description="Sentiment of the historical event")
    impact_level: MarketImpact = Field(description="Impact level of the historical event")
    similarity: float = Field(ge=0.0, le=1.0, description="Similarity score to current event")
    correlation_type: str = Field(description="Type of correlation: 'trend_continuation', 'trend_reversal', 'causal', 'coincidental'")
    trend_trajectory: str = Field(description="How this event relates to the trend: 'accelerating', 'decelerating', 'stable', 'new_direction'")


class MarketIntelligenceReport(BaseModel):
    """Structured LLM output for institutional financial intelligence."""

    executive_summary: str = Field(
        description="2-sentence summary tailored for institutional traders/investors"
    )
    sentiment: FinancialSentiment
    impact_level: MarketImpact
    primary_asset_class: AssetCategory
    affected_entities: List[str] = Field(
        description="Companies, banks, regulators, or instruments mentioned"
    )
    key_metrics: Optional[List[str]] = Field(
        default=None,
        description="Key metrics like '15% interest rate', '50M ETB volume'"
    )
    trading_implication: str = Field(
        description="1-sentence actionable risk/opportunity signal for capital allocators"
    )
    historical_connections: List[HistoricalConnection] = Field(
        default_factory=list,
        description="Correlations with past events from long-term memory"
    )
    synthesized_market_impact: Optional[str] = Field(
        default=None,
        description="Synthesized impact considering historical context and current event"
    )


class MarketIntelligence(BaseModel):
    """Structured LLM output for a single news item (legacy format)."""

    headline: str
    source_name: str
    event_type: EventType
    affected_entities: List[str] = Field(
        description="Companies, banks, regulators, or instruments mentioned"
    )
    summary: str = Field(description="2-3 sentence factual summary for traders/analysts")
    market_impact: str = Field(description="Expected impact on Ethiopian capital markets")
    sentiment: FinancialSentiment = FinancialSentiment.NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0, description="Analyst confidence in assessment")
    key_signals: List[str] = Field(description="Actionable signals for prediction models")


class PipelineOutput(BaseModel):
    """Final persisted output schema."""

    model_config = ConfigDict(extra='allow')  # Allow arbitrary attributes
    
    scraped_at: str
    total_items: int
    articles: List[ScrapedArticle]
    intelligence: List[Union[MarketIntelligenceReport, MarketIntelligence]] = Field(
        default_factory=list,
        description="LLM-generated intelligence reports (supports both new and legacy formats)"
    )
