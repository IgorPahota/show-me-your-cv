from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from typing import Optional, List
from src.gemini_model import GeminiModel
from src.telegram_client import TelegramJobClient
from src.models.database import get_db, Job
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
import asyncio
from datetime import datetime
from src.api_keys import TELEGRAM_JOB_CHANNELS

app = FastAPI(
    title="Job Search API",
    description="API for searching and viewing jobs scraped from Telegram channels",
    version="1.0.0",
    docs_url="/docs",   # Swagger UI endpoint
    redoc_url="/redoc"  # ReDoc endpoint
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
gemini_model = None
telegram_client = None

class JobResponse(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    remote: bool
    salary_min: Optional[float]
    salary_max: Optional[float]
    currency: Optional[str]
    categories: Optional[List[str]]
    # Add Telegram specific fields
    telegram_channel: str
    telegram_message_date: datetime
    telegram_views: Optional[int]
    telegram_forwards: Optional[int]

@app.get("/", response_class=HTMLResponse)
async def root():
    """Simple dashboard page"""
    return """
    <html>
        <head>
            <title>Job Scraper Dashboard</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body class="container mt-5">
            <h1>Job Scraper Dashboard</h1>
            <div class="list-group mt-4">
                <a href="/docs" class="list-group-item list-group-item-action">Interactive API Documentation (Swagger UI)</a>
                <a href="/redoc" class="list-group-item list-group-item-action">Alternative API Documentation (ReDoc)</a>
                <a href="/jobs/latest" class="list-group-item list-group-item-action">View Latest Jobs</a>
                <a href="/jobs/stats" class="list-group-item list-group-item-action">View Job Statistics</a>
                <a href="/jobs/channels" class="list-group-item list-group-item-action">View Monitored Channels</a>
            </div>
        </body>
    </html>
    """

@app.get("/jobs/latest", response_model=List[JobResponse])
async def get_latest_jobs(
    limit: int = Query(10, description="Number of jobs to return"),
    skip: int = Query(0, description="Number of jobs to skip"),
    channel: str = Query(None, description="Filter by Telegram channel"),
    db: Session = Depends(get_db)
):
    """Get the latest scraped jobs"""
    query = db.query(Job).order_by(desc(Job.telegram_message_date))
    
    if channel:
        query = query.filter(Job.telegram_channel_name == channel)
    
    jobs = query.offset(skip).limit(limit).all()
    
    return [
        JobResponse(
            id=job.job_id,
            title=job.title,
            company=job.company_name,
            location=job.location,
            description=job.telegram_raw_text,  # Use raw text instead of processed description
            url=job.url,
            remote=job.remote,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            currency=job.currency,
            categories=job.categories,
            telegram_channel=job.telegram_channel_name,
            telegram_message_date=job.telegram_message_date,
            telegram_views=job.telegram_views,
            telegram_forwards=job.telegram_forwards
        )
        for job in jobs
    ]

@app.get("/jobs/channels/stats")
async def get_channel_stats(db: Session = Depends(get_db)):
    """Get statistics for each Telegram channel"""
    stats = []
    for channel in TELEGRAM_JOB_CHANNELS:
        count = db.query(Job).filter(Job.telegram_channel_name == channel).count()
        latest = db.query(Job).filter(Job.telegram_channel_name == channel).order_by(desc(Job.telegram_message_date)).first()
        stats.append({
            "channel": channel,
            "total_jobs": count,
            "latest_job_date": latest.telegram_message_date if latest else None
        })
    return stats

@app.get("/jobs/search", response_model=List[JobResponse])
async def search_jobs(
    query: str = Query(None, description="Search in title or description"),
    channel: str = Query(None, description="Filter by Telegram channel"),
    remote: bool = Query(None, description="Filter by remote jobs"),
    categories: List[str] = Query(None, description="Filter by job categories"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Number of records to return"),
    db: Session = Depends(get_db)
):
    """Search jobs with various filters"""
    jobs_query = db.query(Job)

    if query:
        jobs_query = jobs_query.filter(
            or_(
                Job.title.ilike(f"%{query}%"),
                Job.telegram_raw_text.ilike(f"%{query}%")
            )
        )
    
    if channel:
        jobs_query = jobs_query.filter(Job.telegram_channel_name == channel)
    
    if remote is not None:
        jobs_query = jobs_query.filter(Job.remote == remote)
    
    if categories:
        jobs_query = jobs_query.filter(Job.categories.overlap(categories))

    total = jobs_query.count()
    jobs = jobs_query.order_by(desc(Job.telegram_message_date)).offset(skip).limit(limit).all()

    return [
        JobResponse(
            id=job.job_id,
            title=job.title,
            company=job.company_name,
            location=job.location,
            description=job.telegram_raw_text,
            url=job.url,
            remote=job.remote,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            currency=job.currency,
            categories=job.categories,
            telegram_channel=job.telegram_channel_name,
            telegram_message_date=job.telegram_message_date,
            telegram_views=job.telegram_views,
            telegram_forwards=job.telegram_forwards
        )
        for job in jobs
    ]

@app.on_event("startup")
async def startup_event():
    global gemini_model, telegram_client
    try:
        gemini_model = GeminiModel()
        print("Successfully initialized Gemini model")
    except Exception as e:
        print(f"Failed to load Gemini model: {e}")
    
    try:
        telegram_client = TelegramJobClient()
        auth_success = await telegram_client.start()
        if auth_success:
            print("Successfully initialized and authenticated Telegram client")
            # Start initial job scraping
            asyncio.create_task(telegram_client.start_job_monitoring())
        else:
            print("Failed to authenticate Telegram client")
    except Exception as e:
        print(f"Failed to initialize Telegram client: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if telegram_client:
        await telegram_client.stop()

@app.get("/health")
async def health_check():
    """Check the health of the service"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "ai": gemini_model is not None,
            "telegram": telegram_client is not None
        }
    }

@app.post("/ai/analyze")
async def analyze_job(job_id: str, db: Session = Depends(get_db)):
    """Analyze a job posting using AI"""
    if gemini_model is None:
        raise HTTPException(status_code=503, detail="AI model not available")
    
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        prompt = f"""Analyze this job posting and provide key insights:
        Title: {job.title}
        Company: {job.company_name}
        Location: {job.location}
        Description: {job.description}
        
        Please provide:
        1. Required skills
        2. Experience level
        3. Key responsibilities
        4. Company culture hints
        5. Red flags (if any)
        """
        
        analysis = gemini_model.generate_text(prompt, max_length=1000)
        return {"analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/stats")
async def get_job_stats(db: Session = Depends(get_db)):
    """Get statistics about stored jobs"""
    try:
        total_jobs = db.query(Job).count()
        remote_jobs = db.query(Job).filter(Job.remote == True).count()
        with_salary = db.query(Job).filter(Job.salary_min.isnot(None)).count()
        
        # Get category distribution
        category_stats = {}
        jobs_with_categories = db.query(Job).filter(Job.categories.isnot(None)).all()
        for job in jobs_with_categories:
            for category in (job.categories or []):
                category_stats[category] = category_stats.get(category, 0) + 1
        
        return {
            "total_jobs": total_jobs,
            "remote_jobs": remote_jobs,
            "jobs_with_salary": with_salary,
            "category_distribution": category_stats,
            "last_update": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/scrape")
async def trigger_scraping():
    """Manually trigger job scraping from Telegram channels"""
    if telegram_client is None:
        raise HTTPException(status_code=503, detail="Telegram client not available")
    
    try:
        await telegram_client._scrape_recent_jobs()
        return {"status": "success", "message": "Job scraping completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/channels")
async def list_channels():
    """List all configured job channels"""
    if telegram_client is None:
        raise HTTPException(status_code=503, detail="Telegram client not available")
    
    return {
        "channels": TELEGRAM_JOB_CHANNELS,
        "total": len(TELEGRAM_JOB_CHANNELS)
    }

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()