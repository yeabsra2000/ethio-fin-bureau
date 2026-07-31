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
    CRITICAL = "critical"
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


class TimeHorizon(str, Enum):
    """Expected time horizon for the market impact."""
    IMMEDIATE = "immediate"          # Hours to days
    SHORT_TERM = "short_term"        # Days to weeks
    MEDIUM_TERM = "medium_term"      # Weeks to months
    LONG_TERM = "long_term"          # Months to years


class CorrelationType(str, Enum):
    """Type of correlation with historical events."""
    TREND_CONTINUATION = "trend_continuation"
    TREND_REVERSAL = "trend_reversal"
    CAUSAL = "causal"
    COINCIDENTAL = "coincidental"


class TrendTrajectory(str, Enum):
    """How the current event relates to the established trend."""
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"
    NEW_DIRECTION = "new_direction"


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
    correlation_type: CorrelationType = Field(description="Type of correlation with past event")
    trend_trajectory: TrendTrajectory = Field(description="How this event relates to the trend")


class NumericalIndicator(BaseModel):
    """A specific numerical data point extracted from the news."""
    name: str = Field(description="What this number represents (e.g. 'interest rate', 'inflation', 'volume')")
    value: str = Field(description="The numerical value with units (e.g. '15%', '50M ETB', '2.5B birr')")
    context: str = Field(description="Brief context for this number (e.g. 'previous was 12%', 'year-on-year change')")


class ActionableSignal(BaseModel):
    """A specific, actionable signal for traders and investors."""
    signal_type: str = Field(description="Type: 'buy', 'sell', 'hold', 'watch', 'hedge', 'arbitrage', 'avoid'")
    asset: str = Field(description="The specific asset or instrument this applies to")
    rationale: str = Field(description="1-sentence rationale for this signal")
    urgency: str = Field(description="'immediate', 'this_week', 'this_month', 'monitor'")


class MarketIntelligenceReport(BaseModel):
    """Structured LLM output for institutional financial intelligence."""

    event_type: EventType = Field(
        description="Classification of what type of event this is"
    )
    executive_summary: str = Field(
        description="2-3 sentence summary tailored for institutional traders/investors. Include the key numbers and what they mean."
    )
    sentiment: FinancialSentiment
    impact_level: MarketImpact
    primary_asset_class: AssetCategory
    time_horizon: TimeHorizon = Field(
        description="Expected timeframe for this event's market impact to materialize"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Analyst confidence in this assessment (0.0-1.0)"
    )
    affected_entities: List[str] = Field(
        description="Companies, banks, regulators, or instruments mentioned"
    )
    key_metrics: Optional[List[NumericalIndicator]] = Field(
        default=None,
        description="Specific numerical data points extracted (interest rates, volumes, percentages, etc.)"
    )
    trading_implication: str = Field(
        description="1-2 sentence actionable risk/opportunity signal for capital allocators. Be specific about what to do."
    )
    actionable_signals: List[ActionableSignal] = Field(
        default_factory=list,
        description="Specific actionable signals for different asset types"
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