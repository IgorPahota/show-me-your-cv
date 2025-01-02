from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from typing import Optional, List
from src.gemini_model import GeminiModel
from src.telegram_client import TelegramJobClient
from src.models.database import get_db, Job, TelegramChannel
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, text
import asyncio
from datetime import datetime

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
async def root(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Dashboard page with job cards and controls"""
    # Check Telegram client status
    telegram_status = "disconnected"
    telegram_error = None
    if telegram_client:
        try:
            is_authorized = await telegram_client.client.is_user_authorized()
            telegram_status = "connected" if is_authorized else "unauthorized"
        except Exception as e:
            telegram_status = "error"
            telegram_error = str(e)
    
    # Get service status
    service_status = {
        "telegram": {
            "status": telegram_status,
            "error": telegram_error
        },
        "database": {
            "status": "connected",
            "error": None
        }
    }
    
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        service_status["database"]["status"] = "error"
        service_status["database"]["error"] = str(e)

    # Add status alert HTML
    status_alerts = []
    if service_status["telegram"]["status"] != "connected":
        alert_type = "warning" if service_status["telegram"]["status"] == "unauthorized" else "danger"
        status_alerts.append(f"""
        <div class="alert alert-{alert_type} alert-dismissible fade show" role="alert">
            <strong>Telegram Status:</strong> {service_status["telegram"]["status"]}
            {f'<br><small>{service_status["telegram"]["error"]}</small>' if service_status["telegram"]["error"] else ''}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
        """)
    
    if service_status["database"]["status"] != "connected":
        status_alerts.append(f"""
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            <strong>Database Status:</strong> {service_status["database"]["status"]}
            {f'<br><small>{service_status["database"]["error"]}</small>' if service_status["database"]["error"] else ''}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
        """)

    # Add status indicators to the header
    status_indicators = f"""
    <div class="d-flex gap-2 align-items-center mb-3">
        <div class="d-flex align-items-center">
            <span class="badge rounded-pill bg-{'success' if service_status['telegram']['status'] == 'connected' else 'warning' if service_status['telegram']['status'] == 'unauthorized' else 'danger'} me-2">
                Telegram: {service_status["telegram"]["status"]}
            </span>
            <span class="badge rounded-pill bg-{'success' if service_status['database']['status'] == 'connected' else 'danger'} me-2">
                Database: {service_status["database"]["status"]}
            </span>
        </div>
    </div>
    """

    print("\n=== Loading Dashboard ===")
    
    # Get jobs with pagination
    offset = (page - 1) * per_page
    total_jobs = db.query(Job).count()
    print(f"Total jobs in database: {total_jobs}")
    
    total_pages = (total_jobs + per_page - 1) // per_page
    print(f"Total pages: {total_pages} (per_page: {per_page})")
    
    print(f"Loading page {page} with offset {offset}")
    jobs = db.query(Job).order_by(desc(Job.telegram_message_date)).offset(offset).limit(per_page).all()
    print(f"Retrieved {len(jobs)} jobs for current page")
    
    # Print some details about the jobs
    for job in jobs:
        print(f"Job ID: {job.job_id}, Title: {job.title}, Date: {job.telegram_message_date}")
    
    # Get channels
    channels = db.query(TelegramChannel).order_by(TelegramChannel.channel_name).all()
    print(f"Retrieved {len(channels)} channels")
    
    # Generate page links
    page_links = []
    for p in range(max(1, page - 2), min(total_pages + 1, page + 3)):
        page_links.append(f'<li class="page-item {"active" if p == page else ""}"><a class="page-link" href="/?page={p}">{p}</a></li>')
    
    print("=== Dashboard Loading Complete ===\n")
    
    # Generate job cards HTML
    job_cards = []
    for job in jobs:
        telegram_link = job.url
        job_date = job.telegram_message_date.strftime("%Y-%m-%d %H:%M:%S")
        
        card_html = f"""
        <div class="card mb-4" id="job-{job.job_id}">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="card-title mb-0">{job.title}</h5>
                <div class="d-flex gap-2 align-items-center">
                    <span class="badge bg-primary">{job.telegram_channel_name}</span>
                    <button 
                        onclick="deleteJob('{job.job_id}')" 
                        class="btn btn-sm btn-outline-danger"
                        title="Delete job"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-trash" viewBox="0 0 16 16">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
                            <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4zM2.5 3h11V2h-11z"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="mb-3" style="white-space: pre-wrap;">{job.telegram_raw_text}</div>
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <small class="text-muted">Posted: {job_date}</small>
                        {f'<br><small class="text-muted">Views: {job.telegram_views}</small>' if job.telegram_views else ''}
                        {f'<br><small class="text-muted">Forwards: {job.telegram_forwards}</small>' if job.telegram_forwards else ''}
                    </div>
                    <a href="{telegram_link}" target="_blank" class="btn btn-sm btn-outline-primary">
                        View on Telegram
                    </a>
                </div>
            </div>
            <div class="card-footer">
                <div class="d-flex flex-wrap gap-2">
                    {'<span class="badge bg-success">Remote</span>' if job.remote else ''}
                    {' '.join(f'<span class="badge bg-info">{cat}</span>' for cat in (job.categories or []))}
                </div>
            </div>
        </div>
        """
        job_cards.append(card_html)
    
    return f"""
    <html>
        <head>
            <title>Job Scraper Dashboard</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <style>
                .card {{ box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .badge {{ margin-right: 4px; }}
                pre {{ white-space: pre-wrap; }}
                #scrapeStatus {{ display: none; }}
                .alert-floating {{
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 1050;
                    min-width: 300px;
                    max-width: 500px;
                }}
                .status-indicator {{
                    width: 10px;
                    height: 10px;
                    border-radius: 50%;
                    display: inline-block;
                    margin-right: 5px;
                }}
                .status-connected {{ background-color: #28a745; }}
                .status-error {{ background-color: #dc3545; }}
                .status-warning {{ background-color: #ffc107; }}
            </style>
            <script>
                function showAlert(message, type = 'info') {{
                    const alertDiv = document.createElement('div');
                    alertDiv.className = `alert alert-${{type}} alert-dismissible fade show alert-floating`;
                    alertDiv.innerHTML = `
                        ${{message}}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    `;
                    document.body.appendChild(alertDiv);
                    
                    // Auto-dismiss after 5 seconds
                    setTimeout(() => {{
                        alertDiv.classList.remove('show');
                        setTimeout(() => alertDiv.remove(), 150);
                    }}, 5000);
                }}

                async function deleteJob(jobId) {{
                    if (!confirm('Are you sure you want to delete this job?')) return;
                    
                    try {{
                        const response = await fetch(`/jobs/${{jobId}}`, {{
                            method: 'DELETE'
                        }});
                        
                        if (!response.ok) throw new Error('Failed to delete job');
                        
                        const result = await response.json();
                        showAlert('Job deleted successfully', 'success');
                        
                        // Remove the job card from the UI
                        const jobCard = document.getElementById(`job-${{jobId}}`);
                        if (jobCard) {{
                            jobCard.remove();
                        }}
                    }} catch (error) {{
                        showAlert(`Error deleting job: ${{error.message}}`, 'danger');
                    }}
                }}

                async function scrapeJobs() {{
                    const limitInput = document.getElementById('messageLimit');
                    const limit = limitInput.value;
                    const status = document.getElementById('scrapeStatus');
                    const button = document.getElementById('scrapeButton');
                    const buttonText = document.getElementById('scrapeButtonText');
                    const spinner = document.getElementById('scrapeSpinner');
                    
                    // Update UI to show scraping is in progress
                    status.style.display = 'block';
                    status.textContent = 'Starting scraping process...';
                    button.disabled = true;
                    buttonText.textContent = 'Scraping...';
                    spinner.style.display = 'inline-block';
                    
                    try {{
                        const response = await fetch('/jobs/scrape?limit=' + limit, {{
                            method: 'POST'
                        }});
                        
                        const result = await response.json();
                        
                        if (!response.ok) {{
                            throw new Error(result.detail || 'Scraping failed');
                        }}
                        
                        showAlert(result.message, result.status === 'success' ? 'success' : 'warning');
                        status.textContent = 'Scraping completed! Refreshing page...';
                        
                        // Refresh the page after a short delay
                        setTimeout(() => window.location.reload(), 2000);
                    }} catch (error) {{
                        showAlert(`Error during scraping: ${{error.message}}`, 'danger');
                        status.textContent = 'Error during scraping';
                        button.disabled = false;
                        buttonText.textContent = 'Start Scraping';
                        spinner.style.display = 'none';
                    }}
                }}

                async function addChannel() {{
                    const channelInput = document.getElementById('newChannel');
                    const channel = channelInput.value.trim();
                    if (!channel) {{
                        showAlert('Please enter a channel name', 'warning');
                        return;
                    }}

                    try {{
                        const response = await fetch('/channels/add', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{ channel_name: channel }})
                        }});
                        
                        if (!response.ok) throw new Error('Failed to add channel');
                        
                        const result = await response.json();
                        showAlert('Channel added successfully', 'success');
                        window.location.reload();
                    }} catch (error) {{
                        showAlert(`Error adding channel: ${{error.message}}`, 'danger');
                    }}
                }}

                async function toggleChannel(id) {{
                    try {{
                        const response = await fetch('/channels/toggle/' + id, {{
                            method: 'POST'
                        }});
                        
                        if (!response.ok) throw new Error('Failed to toggle channel');
                        
                        const result = await response.json();
                        showAlert(`Channel ${{result.is_active ? 'activated' : 'deactivated'}} successfully`, 'success');
                        window.location.reload();
                    }} catch (error) {{
                        showAlert(`Error toggling channel: ${{error.message}}`, 'danger');
                    }}
                }}
            </script>
        </head>
        <body class="container py-5">
            <header class="mb-5">
                <h1 class="mb-4">Job Scraper Dashboard</h1>
                
                {status_indicators}
                {''.join(status_alerts)}
                
                <!-- Channel Management Section -->
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Channel Management</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h6>Add New Channel</h6>
                                <div class="input-group mb-3">
                                    <input type="text" id="newChannel" class="form-control" placeholder="@channel_name">
                                    <button class="btn btn-outline-primary" onclick="addChannel()">Add Channel</button>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <h6>Active Channels</h6>
                                <div class="list-group">
                                    {''.join(f'''
                                    <div class="list-group-item d-flex justify-content-between align-items-center">
                                        {channel.channel_name}
                                        <button 
                                            class="btn btn-sm {'btn-success' if channel.is_active else 'btn-secondary'}"
                                            onclick="toggleChannel({channel.id})"
                                        >
                                            {'Active' if channel.is_active else 'Inactive'}
                                        </button>
                                    </div>
                                    ''' for channel in channels)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Scraping Controls -->
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Scraping Controls</h5>
                    </div>
                    <div class="card-body">
                        <div class="row align-items-end">
                            <div class="col-md-4">
                                <label class="form-label">Messages per channel limit</label>
                                <input type="number" id="messageLimit" class="form-control" value="50" min="1" max="1000">
                            </div>
                            <div class="col-md-4">
                                <button id="scrapeButton" class="btn btn-primary" onclick="scrapeJobs()">
                                    <span id="scrapeButtonText">Start Scraping</span>
                                    <span id="scrapeSpinner" class="spinner-border spinner-border-sm ms-1" role="status" style="display: none;"></span>
                                </button>
                            </div>
                            <div class="col-md-4">
                                <div id="scrapeStatus" class="alert alert-info mb-0" style="display: none;"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="btn-group mb-4">
                    <a href="/docs" class="btn btn-outline-primary">API Documentation</a>
                    <a href="/jobs/stats" class="btn btn-outline-info">Job Statistics</a>
                </div>
                
                <div class="d-flex justify-content-between align-items-center">
                    <p class="mb-0">Total Jobs: {total_jobs}</p>
                    <div class="d-flex gap-2">
                        <button onclick="window.location.reload()" class="btn btn-outline-secondary">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-clockwise" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
                                <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
                            </svg>
                            Refresh List
                        </button>
                        <form class="d-flex" action="/" method="get">
                            <select name="per_page" class="form-select" onchange="this.form.submit()">
                                <option value="10" {"selected" if per_page == 10 else ""}>10 per page</option>
                                <option value="20" {"selected" if per_page == 20 else ""}>20 per page</option>
                                <option value="50" {"selected" if per_page == 50 else ""}>50 per page</option>
                            </select>
                        </form>
                    </div>
                </div>
            </header>
            
            <main>
                {''.join(job_cards)}
            </main>
            
            <nav aria-label="Page navigation" class="my-4">
                <ul class="pagination justify-content-center">
                    <li class="page-item {'' if page > 1 else 'disabled'}">
                        <a class="page-link" href="/?page={page-1}" tabindex="-1">Previous</a>
                    </li>
                    {''.join(page_links)}
                    <li class="page-item {'' if page < total_pages else 'disabled'}">
                        <a class="page-link" href="/?page={page+1}">Next</a>
                    </li>
                </ul>
            </nav>
            
            <footer class="text-center text-muted mt-5">
                <small>Last update: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</small>
            </footer>
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
    channels = db.query(TelegramChannel).all()
    for channel in channels:
        count = db.query(Job).filter(Job.telegram_channel_name == channel.channel_name).count()
        latest = db.query(Job).filter(Job.telegram_channel_name == channel.channel_name).order_by(desc(Job.telegram_message_date)).first()
        stats.append({
            "channel": channel.channel_name,
            "is_active": channel.is_active,
            "total_jobs": count,
            "latest_job_date": latest.telegram_message_date if latest else None,
            "last_scraped": channel.last_scraped
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
async def trigger_scraping(
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Manually trigger job scraping from Telegram channels with custom limit"""
    print("\n=== Starting Manual Scraping Process ===")
    print(f"Requested message limit per channel: {limit}")
    
    # Check Telegram client status
    if telegram_client is None:
        error_msg = "Telegram client not available"
        print(f"Error: {error_msg}")
        raise HTTPException(status_code=503, detail=error_msg)
    
    try:
        # Check if client is authorized
        is_authorized = await telegram_client.client.is_user_authorized()
        if not is_authorized:
            error_msg = "Telegram client not authorized. Please check authentication status."
            print(f"Error: {error_msg}")
            raise HTTPException(status_code=503, detail=error_msg)
        
        # Check if client is connected
        if not telegram_client.client.is_connected():
            error_msg = "Telegram client not connected. Attempting to reconnect..."
            print(error_msg)
            try:
                await telegram_client.client.connect()
            except Exception as e:
                error_msg = f"Failed to reconnect to Telegram: {str(e)}"
                print(f"Error: {error_msg}")
                raise HTTPException(status_code=503, detail=error_msg)
        
        # Get active channels from database
        active_channels = db.query(TelegramChannel).filter(TelegramChannel.is_active == True).all()
        print(f"Found {len(active_channels)} active channels")
        
        if not active_channels:
            print("Warning: No active channels configured")
            return {
                "status": "warning", 
                "message": "No active channels configured. Please add and activate channels first."
            }

        # Get initial job count
        initial_count = db.query(Job).count()
        print(f"Initial job count: {initial_count}")
        
        # Scrape each active channel
        scraped_channels = 0
        errors = []
        for channel in active_channels:
            try:
                print(f"\nScraping channel: {channel.channel_name}")
                await telegram_client._scrape_recent_jobs(channel.channel_name, limit)
                channel.last_scraped = datetime.utcnow()
                db.commit()
                scraped_channels += 1
                print(f"Successfully scraped channel: {channel.channel_name}")
            except Exception as e:
                error_msg = f"Error scraping channel {channel.channel_name}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                continue
        
        # Get final job count
        final_count = db.query(Job).count()
        new_jobs = final_count - initial_count
        print(f"\nScraping complete:")
        print(f"- Channels scraped: {scraped_channels}")
        print(f"- Initial job count: {initial_count}")
        print(f"- Final job count: {final_count}")
        print(f"- New jobs added: {new_jobs}")
        
        # Prepare response message
        if errors:
            status = "warning" if scraped_channels > 0 else "error"
            message = f"Scraped {scraped_channels} channels. Added {new_jobs} new jobs. Errors: {'; '.join(errors)}"
        else:
            status = "success"
            message = f"Successfully scraped {scraped_channels} channels. Added {new_jobs} new jobs."
        
        return {
            "status": status,
            "message": message,
            "details": {
                "channels_scraped": scraped_channels,
                "new_jobs": new_jobs,
                "errors": errors
            }
        }
    except Exception as e:
        error_msg = f"Error during scraping process: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        print("=== Manual Scraping Process Complete ===\n")

@app.get("/jobs/channels")
async def list_channels(db: Session = Depends(get_db)):
    """List all configured job channels"""
    if telegram_client is None:
        raise HTTPException(status_code=503, detail="Telegram client not available")
    
    channels = db.query(TelegramChannel).all()
    return {
        "channels": [
            {
                "id": channel.id,
                "name": channel.channel_name,
                "is_active": channel.is_active,
                "last_scraped": channel.last_scraped
            }
            for channel in channels
        ],
        "total": len(channels)
    }

@app.post("/channels/add")
async def add_channel(
    channel: dict,
    db: Session = Depends(get_db)
):
    """Add a new Telegram channel"""
    try:
        new_channel = TelegramChannel(
            channel_name=channel["channel_name"],
            is_active=True
        )
        db.add(new_channel)
        db.commit()
        return {"status": "success", "message": "Channel added successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/channels/toggle/{channel_id}")
async def toggle_channel(
    channel_id: int,
    db: Session = Depends(get_db)
):
    """Toggle channel active status"""
    channel = db.query(TelegramChannel).filter(TelegramChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.is_active = not channel.is_active
    db.commit()
    return {"status": "success", "is_active": channel.is_active}

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job posting"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        db.delete(job)
        db.commit()
        return {"status": "success", "message": "Job deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()