import os

# Telegram API credentials
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')

# List of Telegram channels to monitor for jobs
TELEGRAM_JOB_CHANNELS = [
    'remote_it_jobs',
    'remoteworkjobs',
    'jobsremotely',
    'remote_jobs_it',
    'remote_jobs_worldwide'
]

# Gemini API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '') 