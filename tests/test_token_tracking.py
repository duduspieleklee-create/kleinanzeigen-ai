"""Tests for token tracking module.

Tests verify that token usage statistics can be retrieved without PostgreSQL
GROUP BY errors on JSON columns.
"""
import pytest
from datetime import datetime, timedelta, timezone, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.shared.database import Base
from app.shared.models import User, ScrapeTask, TokenUsage
from app.shared.token_tracking import (
    get_daily_token_usage,
    get_token_usage_by_task,
    get_token_usage_stats,
    log_token_usage,
)


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def create_test_user(db: Session, username: str = "testuser") -> User:
    """Helper to create a test user."""
    user = User(
        username=username,
        email=f"{username}@test.com",
        hashed_password="hashed_pwd",
    )
    db.add(user)
    db.commit()
    return user


def create_test_task(db: Session, user_id: int, keywords: str = "test keywords") -> ScrapeTask:
    """Helper to create a test scrape task with parameters."""
    task = ScrapeTask(
        user_id=user_id,
        url="https://example.com",
        status="completed",
        parameters={"keywords": keywords, "category": "test"},
    )
    db.add(task)
    db.commit()
    return task


class TestTokenTracking:
    """Test suite for token tracking functions."""

    def test_get_daily_token_usage_no_data(self, test_db):
        """Test getting daily token usage when no data exists."""
        user = create_test_user(test_db)
        result = get_daily_token_usage(test_db, user.id, days=1)
        assert result == 0

    def test_get_daily_token_usage_with_data(self, test_db):
        """Test getting daily token usage with existing data."""
        user = create_test_user(test_db)
        task = create_test_task(test_db, user.id)
        
        # Log some token usage
        log_token_usage(test_db, user.id, task.id, 100)
        
        result = get_daily_token_usage(test_db, user.id, days=1)
        assert result == 100

    def test_get_daily_token_usage_multiple_entries(self, test_db):
        """Test aggregating token usage across multiple entries."""
        user = create_test_user(test_db)
        task1 = create_test_task(test_db, user.id, "keywords1")
        task2 = create_test_task(test_db, user.id, "keywords2")
        
        log_token_usage(test_db, user.id, task1.id, 100)
        log_token_usage(test_db, user.id, task2.id, 50)
        
        result = get_daily_token_usage(test_db, user.id, days=1)
        assert result == 150

    def test_get_token_usage_by_task_no_data(self, test_db):
        """Test getting token usage by task when no data exists."""
        user = create_test_user(test_db)
        result = get_token_usage_by_task(test_db, user.id, days=1)
        assert result == []

    def test_get_token_usage_by_task_with_data(self, test_db):
        """Test getting token usage by task - the key test for the JSON GROUP BY fix."""
        user = create_test_user(test_db)
        task = create_test_task(test_db, user.id, "laptop")
        
        log_token_usage(test_db, user.id, task.id, 150)
        
        # This should NOT raise a PostgreSQL error about JSON equality operator
        result = get_token_usage_by_task(test_db, user.id, days=1)
        
        assert len(result) == 1
        assert result[0]["task_id"] == task.id
        assert result[0]["keywords"] == "laptop"
        assert result[0]["total_tokens"] == 150

    def test_get_token_usage_by_task_multiple_tasks(self, test_db):
        """Test getting token usage for multiple tasks with different parameters."""
        user = create_test_user(test_db)
        task1 = create_test_task(test_db, user.id, "keywords1")
        task2 = create_test_task(test_db, user.id, "keywords2")
        task3 = create_test_task(test_db, user.id, "keywords3")
        
        log_token_usage(test_db, user.id, task1.id, 100)
        log_token_usage(test_db, user.id, task2.id, 200)
        log_token_usage(test_db, user.id, task3.id, 300)
        
        result = get_token_usage_by_task(test_db, user.id, days=1)
        
        assert len(result) == 3
        task_ids = {r["task_id"] for r in result}
        assert task_ids == {task1.id, task2.id, task3.id}
        
        # Verify aggregation
        token_sum = sum(r["total_tokens"] for r in result)
        assert token_sum == 600

    def test_log_token_usage_creates_new_record(self, test_db):
        """Test logging token usage creates a new record."""
        user = create_test_user(test_db)
        task = create_test_task(test_db, user.id)
        
        result = log_token_usage(test_db, user.id, task.id, 100)
        
        assert result.user_id == user.id
        assert result.task_id == task.id
        assert result.tokens == 100

    def test_log_token_usage_increments_existing(self, test_db):
        """Test logging token usage increments existing record for same day."""
        user = create_test_user(test_db)
        task = create_test_task(test_db, user.id)
        
        log_token_usage(test_db, user.id, task.id, 100)
        result = log_token_usage(test_db, user.id, task.id, 50)
        
        assert result.tokens == 150

    def test_log_token_usage_different_days(self, test_db):
        """Test logging token usage creates separate records for different days."""
        user = create_test_user(test_db)
        task = create_test_task(test_db, user.id)
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        log_token_usage(test_db, user.id, task.id, 100, date_=yesterday)
        log_token_usage(test_db, user.id, task.id, 50, date_=today)
        
        # Query and verify both records exist
        records = test_db.query(TokenUsage).filter(
            TokenUsage.user_id == user.id,
            TokenUsage.task_id == task.id,
        ).all()
        
        assert len(records) == 2

    def test_get_token_usage_stats(self, test_db):
        """Test getting comprehensive token usage statistics."""
        user = create_test_user(test_db)
        task1 = create_test_task(test_db, user.id, "keywords1")
        task2 = create_test_task(test_db, user.id, "keywords2")
        
        log_token_usage(test_db, user.id, task1.id, 100)
        log_token_usage(test_db, user.id, task2.id, 200)
        
        stats = get_token_usage_stats(test_db, user.id)
        
        assert stats["last_24h"] == 300
        assert stats["last_7d"] == 300
        assert stats["total"] == 300
        assert len(stats["by_task"]) == 2

    def test_get_token_usage_stats_multiple_users(self, test_db):
        """Test that token usage stats are isolated per user."""
        user1 = create_test_user(test_db, "user1")
        user2 = create_test_user(test_db, "user2")
        
        task1 = create_test_task(test_db, user1.id)
        task2 = create_test_task(test_db, user2.id)
        
        log_token_usage(test_db, user1.id, task1.id, 100)
        log_token_usage(test_db, user2.id, task2.id, 999)
        
        user1_stats = get_token_usage_stats(test_db, user1.id)
        user2_stats = get_token_usage_stats(test_db, user2.id)
        
        assert user1_stats["total"] == 100
        assert user2_stats["total"] == 999

    def test_json_parameters_extraction(self, test_db):
        """Test that JSON parameters are correctly extracted from task."""
        user = create_test_user(test_db)
        keywords = "high-end laptop keyboard"
        task = create_test_task(test_db, user.id, keywords)
        
        log_token_usage(test_db, user.id, task.id, 75)
        
        result = get_token_usage_by_task(test_db, user.id, days=1)
        
        assert len(result) == 1
        assert result[0]["keywords"] == keywords


class TestPostgreSQLCompatibility:
    """Tests to verify the fix for PostgreSQL JSON GROUP BY issue."""

    def test_group_by_fix_no_equality_error(self, test_db):
        """
        CRITICAL TEST: Verify that get_token_usage_by_task() doesn't fail
        with "could not identify an equality operator for type json".
        
        This test would fail with the old code that did:
        .group_by(TokenUsage.task_id, ScrapeTask.parameters)
        
        The fix groups only by task_id, avoiding JSON column in GROUP BY.
        """
        user = create_test_user(test_db)
        
        # Create multiple tasks with different JSON parameters
        tasks = []
        for i in range(5):
            task = create_test_task(test_db, user.id, f"keywords_{i}")
            tasks.append(task)
            log_token_usage(test_db, user.id, task.id, (i + 1) * 100)
        
        # This call should succeed without PostgreSQL errors
        result = get_token_usage_by_task(test_db, user.id, days=1)
        
        # Verify all tasks are aggregated correctly
        assert len(result) == 5
        task_ids_result = {r["task_id"] for r in result}
        task_ids_expected = {t.id for t in tasks}
        assert task_ids_result == task_ids_expected
