from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean, ARRAY, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import time
from sqlalchemy.exc import OperationalError, ProgrammingError
import os

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jobs_db")

def wait_for_db(retries=30, delay=2):
    """Wait for database to be ready"""
    for attempt in range(retries):
        try:
            # Try to connect to the server first (without database)
            engine = create_engine(DATABASE_URL.rsplit('/', 1)[0])
            with engine.connect() as conn:
                # Check if we can connect
                conn.execute(text("SELECT 1"))
                print("Successfully connected to PostgreSQL server")
                return True
        except OperationalError as e:
            if attempt == retries - 1:
                print(f"Could not connect to PostgreSQL server after {retries} attempts")
                raise
            print(f"Database server not ready (attempt {attempt + 1}/{retries})")
            time.sleep(delay)
    return False

def get_engine(retries=5, delay=2):
    """Get database engine with retries"""
    # First, wait for the database server
    wait_for_db()
    
    for attempt in range(retries):
        try:
            print(f"Attempting to connect to database with URL: {DATABASE_URL}")
            engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                echo=True  # Enable SQL logging
            )
            
            # Test the connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Successfully connected to the database")
            return engine
            
        except (OperationalError, ProgrammingError) as e:
            if attempt == retries - 1:
                print(f"Final connection attempt failed: {str(e)}")
                raise
            print(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True)
    title = Column(String)
    company_name = Column(String)
    location = Column(String)
    description = Column(Text)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    remote = Column(Boolean, default=False)
    url = Column(String)
    categories = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db():
    """Initialize database tables"""
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        raise

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize database tables
init_db() 