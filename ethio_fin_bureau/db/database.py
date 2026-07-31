"""Database initialization and operations for the Ethiopian Financial Intelligence Bureau."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import Session, sessionmaker

from ethio_fin_bureau.config import USE_SQLITE
from ethio_fin_bureau.db.models import Base, FinancialRecord, HAS_PGVECTOR

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


def _generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate vector embedding for text using simple TF-IDF-like approach.
    Falls back to None if pgvector is not available.
    
    Args:
        text: Text to embed
        
    Returns:
        List of floats representing the embedding, or None
    """
    if not HAS_PGVECTOR:
        return None
    
    try:
        # Simple embedding using character n-grams (384 dimensions)
        # In production, use OpenAI embeddings or similar
        text = text.lower().strip()
        embedding = np.zeros(384)
        
        # Character-level n-grams (3-grams)
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            idx = hash(ngram) % 384
            embedding[idx] += 1
        
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding.tolist()
    except Exception as e:
        logger.error("Failed to generate embedding: %s", e)
        return None


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
    """Check if a content hash already exists in the database.
    
    Uses raw SQL to avoid issues with missing columns (like embedding).
    """
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return False
    
    try:
        session = get_session()
        try:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT 1 FROM financial_records WHERE content_hash = :hash LIMIT 1"),
                {"hash": content_hash}
            ).scalar()
            return result is not None
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
                record_dict["affected_entities"] = json.dumps(affected_entities)
            
            # Generate embedding for vector search (if column exists)
            headline = record_dict.get("headline", "")
            summary = record_dict.get("executive_summary", "")
            embedding_text = f"{headline} {summary}"
            
            if HAS_PGVECTOR:
                embedding = _generate_embedding(embedding_text)
                if embedding:
                    record_dict["embedding"] = embedding
            
            record = FinancialRecord(**record_dict)
            session.add(record)
            session.commit()
            logger.debug("Saved record: %s", record_dict.get("headline", "")[:50])
            return True
        except Exception as e:
            session.rollback()
            # If error is about missing embedding column, try without it
            if "embedding" in str(e).lower() and "does not exist" in str(e).lower():
                logger.warning("Embedding column not found, saving without embedding")
                record_dict_without_embedding = {k: v for k, v in record_dict.items() if k != "embedding"}
                try:
                    record = FinancialRecord(**record_dict_without_embedding)
                    session.add(record)
                    session.commit()
                    logger.debug("Saved record without embedding: %s", record_dict.get("headline", "")[:50])
                    return True
                except Exception as e2:
                    session.rollback()
                    logger.error("Failed to save record even without embedding: %s", e2)
                    return False
            else:
                logger.error("Failed to save record: %s", e)
                return False
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to save record: %s", e)
        return False


def save_intelligence_report(record_dict: Dict[str, Any]) -> bool:
    """
    Save an enhanced intelligence report with all new fields.
    Handles JSON serialization of complex fields automatically.
    
    Args:
        record_dict: Dictionary containing record data with all enhanced fields
        
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
            # Convert list fields to JSON strings
            for field in ["affected_entities", "key_metrics", "actionable_signals", "historical_connections"]:
                value = record_dict.get(field)
                if isinstance(value, (list, dict)):
                    record_dict[field] = json.dumps(value, ensure_ascii=False)
            
            # Generate embedding for vector search (if column exists)
            headline = record_dict.get("headline", "")
            summary = record_dict.get("executive_summary", "")
            embedding_text = f"{headline} {summary}"
            
            if HAS_PGVECTOR:
                embedding = _generate_embedding(embedding_text)
                if embedding:
                    record_dict["embedding"] = embedding
            
            record = FinancialRecord(**record_dict)
            session.add(record)
            session.commit()
            logger.debug("Saved intelligence report: %s", record_dict.get("headline", "")[:50])
            return True
        except Exception as e:
            session.rollback()
            # If error is about missing columns, try without new fields
            error_str = str(e).lower()
            if any(col in error_str for col in ["event_type", "time_horizon", "confidence_score", "key_metrics", "actionable_signals"]):
                logger.warning("New columns not found in database, saving with basic fields only")
                # Strip new fields and try again
                basic_fields = {k: v for k, v in record_dict.items() 
                              if k not in ["event_type", "time_horizon", "confidence_score", 
                                          "key_metrics", "actionable_signals", 
                                          "synthesized_market_impact", "historical_connections"]}
                try:
                    record = FinancialRecord(**basic_fields)
                    session.add(record)
                    session.commit()
                    logger.debug("Saved basic record: %s", record_dict.get("headline", "")[:50])
                    return True
                except Exception as e2:
                    session.rollback()
                    logger.error("Failed to save basic record: %s", e2)
                    return False
            elif "embedding" in error_str and "does not exist" in error_str:
                logger.warning("Embedding column not found, saving without embedding")
                record_dict_without_embedding = {k: v for k, v in record_dict.items() if k != "embedding"}
                try:
                    record = FinancialRecord(**record_dict_without_embedding)
                    session.add(record)
                    session.commit()
                    return True
                except Exception as e2:
                    session.rollback()
                    logger.error("Failed to save record without embedding: %s", e2)
                    return False
            else:
                logger.error("Failed to save intelligence report: %s", e)
                return False
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to save intelligence report: %s", e)
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
            
            # Get event type distribution
            event_type_counts = {}
            try:
                for event_type, count in session.query(
                    FinancialRecord.event_type, func.count(FinancialRecord.id)
                ).group_by(FinancialRecord.event_type).all():
                    event_type_counts[event_type or "UNKNOWN"] = count
            except Exception:
                event_type_counts = {"N/A": 0}
            
            return {
                "enabled": True,
                "total_records": total,
                "by_sentiment": sentiment_counts,
                "by_impact": impact_counts,
                "by_event_type": event_type_counts,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to get stats: %s", e)
        return {"enabled": False, "error": str(e)}


def search_similar_records(headline: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Search for similar historical records using vector similarity (PostgreSQL)
    or keyword matching (SQLite fallback).
    
    Args:
        headline: Headline to search for
        limit: Maximum number of results to return
        
    Returns:
        List of similar records with similarity scores
    """
    if not USE_SQLITE and not os.environ.get("DATABASE_URL"):
        return []
    
    # Try pgvector first if available
    if HAS_PGVECTOR:
        try:
            embedding = _generate_embedding(headline)
            if embedding:
                session = get_session()
                try:
                    from sqlalchemy import text
                    query = text("""
                        SELECT id, headline, executive_summary, sentiment, impact_level, 
                               created_at, 1 - (embedding <=> :embedding) as similarity
                        FROM financial_records
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> :embedding
                        LIMIT :limit
                    """)
                    results = session.execute(query, {"embedding": str(embedding), "limit": limit})
                    similar_records = []
                    for row in results:
                        similar_records.append({
                            "id": row[0],
                            "headline": row[1],
                            "executive_summary": row[2],
                            "sentiment": row[3],
                            "impact_level": row[4],
                            "created_at": row[5].isoformat() if row[5] else None,
                            "similarity": float(row[6]),
                        })
                    if similar_records:
                        return similar_records
                finally:
                    session.close()
        except Exception as e:
            logger.debug("pgvector search failed, falling back to keyword: %s", e)
    
    # Fallback: keyword-based search for SQLite
    try:
        session = get_session()
        try:
            # Extract meaningful keywords from the headline
            keywords = _extract_search_keywords(headline)
            
            if not keywords:
                return []
            
            # Build LIKE conditions for each keyword
            conditions = []
            for kw in keywords:
                conditions.append(FinancialRecord.headline.ilike(f"%{kw}%"))
                conditions.append(FinancialRecord.executive_summary.ilike(f"%{kw}%"))
            
            if not conditions:
                return []
            
            # Query records matching any keyword
            from sqlalchemy import text
            query = session.query(
                FinancialRecord.id,
                FinancialRecord.headline,
                FinancialRecord.executive_summary,
                FinancialRecord.sentiment,
                FinancialRecord.impact_level,
                FinancialRecord.created_at,
            ).filter(or_(*conditions)).order_by(
                FinancialRecord.created_at.desc()
            ).limit(limit * 2)  # Get extra for scoring
            
            results = query.all()
            
            if not results:
                return []
            
            # Score results by keyword match density
            scored_results = []
            headline_lower = headline.lower()
            for row in results:
                # Calculate similarity score based on keyword overlap
                record_text = f"{row.headline} {row.executive_summary or ''}".lower()
                match_count = sum(1 for kw in keywords if kw.lower() in record_text)
                similarity = min(1.0, match_count / max(len(keywords), 1))
                
                scored_results.append({
                    "id": row.id,
                    "headline": row.headline,
                    "executive_summary": row.executive_summary,
                    "sentiment": row.sentiment,
                    "impact_level": row.impact_level,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "similarity": similarity,
                })
            
            # Sort by similarity and return top results
            scored_results.sort(key=lambda r: r["similarity"], reverse=True)
            return scored_results[:limit]
            
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to search similar records: %s", e)
        return []


def _extract_search_keywords(text: str) -> List[str]:
    """
    Extract meaningful search keywords from text.
    Filters out common stop words and short words.
    
    Args:
        text: Text to extract keywords from
        
    Returns:
        List of meaningful keywords
    """
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "by", "with", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can", "not",
        "no", "nor", "its", "it's", "this", "that", "these", "those",
        "new", "news", "latest", "update", "report", "announcement",
    }
    
    # Split into words and filter
    words = text.lower().split()
    keywords = []
    
    for word in words:
        # Clean the word
        word = word.strip(".,!?;:'\"()[]{}")
        
        # Skip short words, stop words, and purely numeric tokens
        if len(word) < 4:
            continue
        if word in stop_words:
            continue
        if word.isdigit():
            continue
        
        keywords.append(word)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    return unique_keywords[:10]  # Limit to 10 keywords