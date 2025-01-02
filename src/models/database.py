from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, JSON, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import os
from datetime import datetime

Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True)
    job_id = Column(String(255), unique=True, nullable=False)
    
    # Basic job info
    title = Column(String(255))
    company_name = Column(String(255))
    location = Column(String(255))
    description = Column(Text)
    url = Column(String(255))
    remote = Column(Boolean, default=False)
    salary_min = Column(Float)
    salary_max = Column(Float)
    currency = Column(String(10))
    categories = Column(JSON)
    
    # Telegram specific metadata
    telegram_message_id = Column(BigInteger)
    telegram_channel_id = Column(BigInteger)
    telegram_channel_name = Column(String(255))
    telegram_message_date = Column(DateTime)
    telegram_views = Column(Integer)
    telegram_forwards = Column(Integer)
    telegram_raw_text = Column(Text)  # Original unprocessed message
    telegram_metadata = Column(JSON)  # Store any additional metadata
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/jobs_db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables
Base.metadata.create_all(bind=engine) 