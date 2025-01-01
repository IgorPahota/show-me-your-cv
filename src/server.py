from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
import uvicorn
from typing import Optional, List
from src.gemini_model import GeminiModel
from src.telegram_client import TelegramJobClient
from src.models.database import get_db, Job
from sqlalchemy.orm import Session
from sqlalchemy import or_
import asyncio
from datetime import datetime

app = FastAPI(
    title="Job Search and AI Assistant",
    description="Search jobs from Telegram channels and use AI to analyze job descriptions",
    version="1.0.0"
)

# Initialize services
gemini_model = None
telegram_client = None

class QueryRequest(BaseModel):
    prompt: str
    max_length: int = 200

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
        await telegram_client.start()
        print("Successfully initialized Telegram client")
        # Start initial job scraping
        asyncio.create_task(telegram_client.start_job_monitoring())
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

@app.get("/jobs/search", response_model=List[JobResponse])
async def search_jobs(
    query: str = Query(None, description="Search in title, company, or description"),
    location: str = Query(None, description="Filter by location"),
    remote: bool = Query(None, description="Filter by remote jobs"),
    min_salary: float = Query(None, description="Filter by minimum salary"),
    categories: List[str] = Query(None, description="Filter by job categories"),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Search jobs in the database"""
    try:
        # Build query
        jobs_query = db.query(Job)

        # Apply filters
        if query:
            jobs_query = jobs_query.filter(
                or_(
                    Job.title.ilike(f"%{query}%"),
                    Job.company_name.ilike(f"%{query}%"),
                    Job.description.ilike(f"%{query}%")
                )
            )
        
        if location:
            jobs_query = jobs_query.filter(Job.location.ilike(f"%{location}%"))
        
        if remote is not None:
            jobs_query = jobs_query.filter(Job.remote == remote)
        
        if min_salary:
            jobs_query = jobs_query.filter(Job.salary_min >= min_salary)
            
        if categories:
            jobs_query = jobs_query.filter(Job.categories.overlap(categories))

        # Apply pagination
        total = jobs_query.count()
        jobs = jobs_query.offset(skip).limit(limit).all()

        return [
            JobResponse(
                id=job.job_id,
                title=job.title,
                company=job.company_name,
                location=job.location,
                description=job.description,
                url=job.url,
                remote=job.remote,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                currency=job.currency,
                categories=job.categories
            )
            for job in jobs
        ]
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

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()