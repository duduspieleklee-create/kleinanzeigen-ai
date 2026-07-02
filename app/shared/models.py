from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.shared.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Integer, default=1)
    # Admin users may manage scheduled admin searches and rotating proxies.
    is_admin = Column(Boolean, nullable=False, server_default="false")
    # Max searches a user may start per calendar day. 0 = unlimited (admin).
    # Legacy column — superseded by the plan/credit system but kept so that
    # daily_limit == 0 still marks unlimited accounts (admin/system).
    daily_limit = Column(Integer, nullable=False, server_default="3")
    # Subscription plan: basic (free) / core / pro — see app/shared/plans.py.
    plan = Column(String(20), nullable=False, server_default="basic")
    # Weekly result credits. One credit is consumed per NEW listing found
    # (deducted by the worker when the result is saved). Refilled lazily each
    # week (plans.ensure_weekly_credits).
    credits = Column(Integer, nullable=False, server_default="0")
    credits_reset_at = Column(DateTime(timezone=True))
    # Stripe billing references (set once the user has been through checkout).
    stripe_customer_id = Column(String(100), index=True)
    stripe_subscription_id = Column(String(100))
    # One-shot dashboard notice set by the downgrade sweep
    # (plans.enforce_plan_limits) when searches were cancelled or slowed to
    # fit the new plan. Shown once on the dashboard, then cleared.
    plan_notice = Column(Text)
    # Email verification. Google signups are verified automatically (Google
    # asserts the email); password signups must click the emailed link before
    # they can start searches. Existing accounts were backfilled as verified.
    email_verified = Column(Boolean, nullable=False, server_default="false")
    verify_token = Column(String(64), index=True)
    verify_token_expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    scrape_tasks = relationship("ScrapeTask", back_populates="user")
    push_subscriptions = relationship("PushSubscription", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    parameters = Column(JSON)                       # Stores search parameters as JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="scrape_tasks")
    results = relationship("ScrapeResult", back_populates="task")

    def __repr__(self):
        return f"<ScrapeTask(id={self.id}, status='{self.status}')>"


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("scrape_tasks.id"), nullable=False)
    title = Column(String(255))
    price = Column(String(50))
    price_value = Column(Integer)                   # parsed euros (0=free, null=unknown)
    location = Column(String(100))
    url = Column(Text)
    image_url = Column(Text)                        # listing thumbnail
    description = Column(Text)
    raw_data = Column(JSON)                         # Optional: store full raw data
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    task = relationship("ScrapeTask", back_populates="results")

    def __repr__(self):
        return f"<ScrapeResult(id={self.id}, title='{self.title}')>"


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="push_subscriptions")

    def __repr__(self):
        return f"<PushSubscription(id={self.id}, user_id={self.user_id})>"


class Proxy(Base):
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False, unique=True)  # e.g. http://user:pass@host:port
    # Only proxies that passed the live test are active and used by the scraper.
    is_active = Column(Boolean, nullable=False, default=True)
    last_status = Column(String(20))  # 'ok' | 'failed'
    last_tested_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Proxy(id={self.id}, active={self.is_active})>"


class SystemSetting(Base):
    """Simple key/value store for global feature flags (e.g. rotating proxy)."""
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(500))

    def __repr__(self):
        return f"<SystemSetting(key='{self.key}', value='{self.value}')>"


class AdminSearch(Base):
    __tablename__ = "admin_searches"

    id = Column(Integer, primary_key=True, index=True)
    keywords = Column(String(255), nullable=False)
    category = Column(String(100))
    location = Column(String(255))
    location_id = Column(Integer)
    price_min = Column(Integer)
    price_max = Column(Integer)
    radius = Column(Integer)
    interval_minutes = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AdminSearch(id={self.id}, keywords='{self.keywords}')>"
