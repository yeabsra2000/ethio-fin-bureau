"""SQLAlchemy models for the Ethiopian Financial Intelligence Bureau."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, DateTime, Integer, Text, Float, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except (ImportError, ModuleNotFoundError):
    HAS_PGVECTOR = False


class Base(DeclarativeBase):
    pass


class FinancialRecord(Base):
    """Persistent storage for LLM-analyzed financial intelligence reports."""

    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_hash = Column(String(64), unique=True, index=True, nullable=False)
    source_name = Column(String(100), nullable=False)
    tier = Column(String(50), nullable=False)
    headline = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    normalized_date = Column(String(20), nullable=True)
    executive_summary = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=True)
    impact_level = Column(String(20), nullable=True)
    primary_asset_class = Column(String(50), nullable=True)
    affected_entities = Column(Text, nullable=True)
    trading_implication = Column(Text, nullable=True)
    
    # New fields for enhanced intelligence
    event_type = Column(String(50), nullable=True)
    time_horizon = Column(String(20), nullable=True)
    confidence_score = Column(Float, nullable=True)
    key_metrics = Column(Text, nullable=True)  # JSON string
    actionable_signals = Column(Text, nullable=True)  # JSON string
    synthesized_market_impact = Column(Text, nullable=True)
    historical_connections = Column(Text, nullable=True)  # JSON string
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Vector embedding for semantic search (requires pgvector)
    # Only define column if pgvector is actually installed
    if HAS_PGVECTOR:
        embedding = Column(Vector(384), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "content_hash": self.content_hash,
            "source_name": self.source_name,
            "tier": self.tier,
            "headline": self.headline,
            "url": self.url,
            "normalized_date": self.normalized_date,
            "executive_summary": self.executive_summary,
            "sentiment": self.sentiment,
            "impact_level": self.impact_level,
            "primary_asset_class": self.primary_asset_class,
            "affected_entities": self.affected_entities,
            "trading_implication": self.trading_implication,
            "event_type": self.event_type,
            "time_horizon": self.time_horizon,
            "confidence_score": self.confidence_score,
            "key_metrics": self.key_metrics,
            "actionable_signals": self.actionable_signals,
            "synthesized_market_impact": self.synthesized_market_impact,
            "historical_connections": self.historical_connections,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return result

    def get_affected_entities_list(self) -> List[str]:
        """Deserialize affected_entities from JSON string."""
        if not self.affected_entities:
            return []
        try:
            return json.loads(self.affected_entities)
        except (json.JSONDecodeError, TypeError):
            return [e.strip() for e in self.affected_entities.split(",") if e.strip()]

    def get_key_metrics_list(self) -> List[Dict[str, str]]:
        """Deserialize key_metrics from JSON string."""
        if not self.key_metrics:
            return []
        try:
            return json.loads(self.key_metrics)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_actionable_signals_list(self) -> List[Dict[str, str]]:
        """Deserialize actionable_signals from JSON string."""
        if not self.actionable_signals:
            return []
        try:
            return json.loads(self.actionable_signals)
        except (json.JSONDecodeError, TypeError):
            return []

    def __repr__(self) -> str:
        return f"<FinancialRecord(id={self.id}, source={self.source_name}, sentiment={self.sentiment})>"