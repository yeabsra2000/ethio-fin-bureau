"""Database initialization and operations for the Ethiopian Financial Intelligence Bureau."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from ethio_fin_bureau.config import USE_SQLITE
from ethio_fin_bureau.db.models import Base, FinancialRecord

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_SessionFactory = None


def _get_database_url() -> str:
    """
    Get database URL from environment or fallback to SQLite.
    
    Supports:
    - DATABASE_URL environment variable (PostgreSQL, MySQL, etc.)
    - Falls back to local SQLite if not set
    
    Returns:
        SQLAlchemy database URL
    """
    # Check for DATABASE_URL environment variable (PostgreSQL, etc.)
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        # Ensure the URL uses the correct format for SQLAlchemy
        if database_url.startswith("postgres://"):
            # Heroku-style postgres:// URLs need to be converted
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        logger.info("Using external database (PostgreSQL/MySQL)")
        return database_url
    
    # Fallback to SQLite
    db_path = Path(__file__).parent.parent / "data" / "bureau.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Using local SQLite database at %s", db_path)
    return f"sqlite:///{db_path}"


def _init_engine():
    """Initialize the SQLAlchemy engine and session factory."""
    global _engine, _SessionFactory
    
    if _engine is not None:
        return
    
    database_url = _get_database_url()
    
    # Configure engine based on database type
    if database_url.startswith("sqlite"):
        _engine = create_engine(database_url, echo=False)
    else:
        # PostgreSQL/MySQL with connection pooling
        _engine = create_engine(
            database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using them
            pool_recycle=3600,   # Recycle connections after 1 hour
        )
    
    _SessionFactory = sessionmaker(bind=_engine)


def init_db() -> None:
    """
    Initialize the database and create all tables.
    
    Works with both SQLite (local) and PostgreSQL (via DATABASE_URL).
    """
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        logger.info("SQLite persistence is disabled in config.")
        return
    
    try:
        _init_engine()
        Base.metadata.create_all(_engine)
        logger.info("Database initialized successfully")
        db_url = _get_database_url()
        logger.debug("Database URL: %s", db_url.replace("://", "://[REDACTED]@") if "://" in db_url else db_url)
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise


def get_session() -> Session:
    """Get a new database session."""
    if _SessionFactory is None:
        _init_engine()
    return _SessionFactory()


def is_hash_exists(content_hash: str) -> bool:
    """Check if a content hash already exists in the database."""
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return False
    
    try:
        session = get_session()
        try:
            exists = session.query(FinancialRecord).filter(
                FinancialRecord.content_hash == content_hash
            ).first() is not None
            return exists
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to check hash existence: %s", e)
        return False


def save_record(record_dict: Dict[str, Any]) -> bool:
    """
    Save a financial intelligence record to the database.
    
    Args:
        record_dict: Dictionary containing record data
        
    Returns:
        True if saved successfully, False otherwise
    """
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return False
    
    try:
        # Check for duplicate
        content_hash = record_dict.get("content_hash")
        if content_hash and is_hash_exists(content_hash):
            logger.debug("Record with hash %s already exists, skipping.", content_hash[:16])
            return False
        
        session = get_session()
        try:
            # Convert affected_entities list to JSON string
            affected_entities = record_dict.get("affected_entities", [])
            if isinstance(affected_entities, list):
                import json
                record_dict["affected_entities"] = json.dumps(affected_entities)
            
            record = FinancialRecord(**record_dict)
            session.add(record)
            session.commit()
            logger.debug("Saved record: %s", record_dict.get("headline", "")[:50])
            return True
        except Exception as e:
            session.rollback()
            logger.error("Failed to save record: %s", e)
            return False
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to save record: %s", e)
        return False


def get_stats() -> Dict[str, Any]:
    """
    Get database statistics.
    
    Returns:
        Dictionary containing statistics
    """
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return {"enabled": False}
    
    try:
        session = get_session()
        try:
            total = session.query(func.count(FinancialRecord.id)).scalar() or 0
            
            # Get sentiment distribution
            sentiment_counts = {}
            for sentiment, count in session.query(
                FinancialRecord.sentiment, func.count(FinancialRecord.id)
            ).group_by(FinancialRecord.sentiment).all():
                sentiment_counts[sentiment or "UNKNOWN"] = count
            
            # Get impact level distribution
            impact_counts = {}
            for impact, count in session.query(
                FinancialRecord.impact_level, func.count(FinancialRecord.id)
            ).group_by(FinancialRecord.impact_level).all():
                impact_counts[impact or "UNKNOWN"] = count
            
            return {
                "enabled": True,
                "total_records": total,
                "by_sentiment": sentiment_counts,
                "by_impact": impact_counts,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to get stats: %s", e)
        return {"enabled": False, "error": str(e)}