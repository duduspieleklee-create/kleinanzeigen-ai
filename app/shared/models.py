from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.shared.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    parameters = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("scrape_tasks.id"))
    title = Column(String(255))
    price = Column(String(50))
    location = Column(String(100))
    url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
