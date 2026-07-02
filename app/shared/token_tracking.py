"""Token usage tracking and analytics.

Provides utilities for tracking daily token consumption per user and search,
and for generating usage reports for the dashboard.
"""
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Dict
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.shared.models import TokenUsage, ScrapeTask


def get_daily_token_usage(db: Session, user_id: int, days: int = 1) -> int:
    """Get total tokens used by a user in the last N days.
    
    Args:
        db: Database session
        user_id: User ID
        days: Number of days to look back (default: 1 for last 24 hours)
    
    Returns:
        Total tokens consumed in the period
    """
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    
    result = db.query(func.sum(TokenUsage.tokens)).filter(
        and_(
            TokenUsage.user_id == user_id,
            TokenUsage.date >= cutoff_date,
        )
    ).scalar()
    
    return result or 0


def get_token_usage_by_task(
    db: Session, user_id: int, days: int = 1
) -> List[Dict]:
    """Get token usage broken down by search task for a user.
    
    Returns a list of dicts with: task_id, task_name, total_tokens, last_used
    
    FIXED: Removed JSON column from GROUP BY. PostgreSQL cannot use JSON columns
    in GROUP BY clauses. Now uses subquery approach to aggregate tokens by task_id only.
    """
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    
    # Aggregate token usage by task (group by task_id only, avoid JSON in GROUP BY)
    token_agg = db.query(
        TokenUsage.task_id,
        func.sum(TokenUsage.tokens).label("total_tokens"),
        func.max(TokenUsage.date).label("last_used"),
    ).filter(
        and_(
            TokenUsage.user_id == user_id,
            TokenUsage.date >= cutoff_date,
        )
    ).group_by(
        TokenUsage.task_id
    ).all()
    
    # Now fetch task parameters for each aggregated result
    usage_list = []
    for task_id, total_tokens, last_used in token_agg:
        task = db.query(ScrapeTask.parameters).filter(
            ScrapeTask.id == task_id
        ).first()
        
        params = task[0] if task else None
        
        # Extract search keywords from parameters
        keywords = ""
        if params and isinstance(params, dict):
            keywords = params.get("keywords", "")
        
        usage_list.append({
            "task_id": task_id,
            "keywords": keywords,
            "total_tokens": total_tokens or 0,
            "last_used": last_used,
        })
    
    return usage_list


def log_token_usage(
    db: Session, user_id: int, task_id: int, tokens: int, date_: Optional[date] = None
) -> TokenUsage:
    """Log token usage for a user and task.
    
    If a record for the same user/task/date already exists, increment the token count.
    Otherwise, create a new record.
    
    Args:
        db: Database session
        user_id: User ID
        task_id: Task ID
        tokens: Number of tokens to log
        date_: Date for the usage (default: today UTC)
    
    Returns:
        The TokenUsage record (created or updated)
    """
    if date_ is None:
        date_ = datetime.now(timezone.utc).date()
    
    # Try to find existing record for this user/task/date
    existing = db.query(TokenUsage).filter(
        and_(
            TokenUsage.user_id == user_id,
            TokenUsage.task_id == task_id,
            TokenUsage.date == date_,
        )
    ).first()
    
    if existing:
        existing.tokens += tokens
        db.commit()
        return existing
    else:
        new_usage = TokenUsage(
            user_id=user_id,
            task_id=task_id,
            tokens=tokens,
            date=date_,
        )
        db.add(new_usage)
        db.commit()
        return new_usage


def get_token_usage_stats(db: Session, user_id: int) -> Dict:
    """Get comprehensive token usage statistics for a user.
    
    Returns a dict with:
    - last_24h: tokens used in last 24 hours
    - last_7d: tokens used in last 7 days
    - total: total tokens ever used
    - by_task: breakdown by search task
    """
    last_24h = get_daily_token_usage(db, user_id, days=1)
    last_7d = get_daily_token_usage(db, user_id, days=7)
    
    total = db.query(func.sum(TokenUsage.tokens)).filter(
        TokenUsage.user_id == user_id
    ).scalar() or 0
    
    by_task = get_token_usage_by_task(db, user_id, days=7)
    
    return {
        "last_24h": last_24h,
        "last_7d": last_7d,
        "total": total,
        "by_task": by_task,
    }
