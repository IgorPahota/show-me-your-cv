import os

# Telegram API credentials
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')

# List of Telegram channels to monitor for jobs
TELEGRAM_JOB_CHANNELS = [
    '@jobs_in_it_remoute',
    '@dev_connectablejobs'
]

# Gemini API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '') 