import os
import logging
import asyncio
import threading
import nest_asyncio
from telethon import TelegramClient as TelethonClient
from telethon.tl.functions.messages import GetHistoryRequest
from django.conf import settings
from job_scraper.models import Job
from django.utils import timezone
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class TelegramClient:
    _instance = None
    _phone_code_hash = None
    _lock = threading.Lock()
    _loop = None
    _needs_verification = False
    _is_connected = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TelegramClient, cls).__new__(cls)
                    cls._instance._initialized = False
                    cls._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(cls._loop)
                    nest_asyncio.apply(cls._loop)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        with self._lock:
            if not self._initialized:
                session_file = os.path.join(settings.TELEGRAM_SESSION_DIR, "scraper")
                self.client = TelethonClient(
                    session_file,
                    settings.TELEGRAM_API_ID,
                    settings.TELEGRAM_API_HASH,
                    loop=self._loop
                )
                self._initialized = True
                try:
                    self._run_async(self._connect())
                except Exception as e:
                    logger.error(f"Failed to connect during initialization: {str(e)}")

    @sync_to_async
    def _save_job(self, job_id, defaults):
        """Save job to database"""
        try:
            job, created = Job.objects.update_or_create(
                job_id=job_id,
                defaults=defaults
            )
            return created
        except Exception as e:
            logger.error(f"Database error saving job {job_id}: {str(e)}")
            return False

    async def _process_job_post(self, channel_id, channel_name, message):
        """Process and store a job post"""
        try:
            # Remove @ from channel name if present
            clean_channel_name = channel_name.lstrip('@')
            job_id = f"{clean_channel_name}_{message['id']}"
            
            logger.info(f"Processing job post: {job_id}")
            logger.info(f"Message content: {message['text'][:100]}...")  # Log first 100 chars
            
            defaults = {
                'title': message['text'][:255],
                'description': message['text'],
                'telegram_message_id': message['id'],
                'telegram_channel_id': channel_id,
                'telegram_channel_name': clean_channel_name,
                'telegram_message_date': message['date'],
                'telegram_views': message['views'],
                'telegram_forwards': message['forwards'],
                'telegram_raw_text': message['text'],
                'url': f"https://t.me/{clean_channel_name}/{message['id']}"
            }
            
            logger.info(f"Attempting to create/update job with ID: {job_id}")
            created = await self._save_job(job_id, defaults)
            
            if created:
                logger.info(f"Created new job: {job_id}")
            else:
                logger.info(f"Updated existing job: {job_id}")
            
            return created
            
        except Exception as e:
            logger.error(f"Error processing job post: {str(e)}")
            logger.error(f"Job data: channel_id={channel_id}, channel_name={channel_name}, message_id={message.get('id')}")
            return False

    async def _get_channel_messages(self, channel_name, limit=100):
        """Get messages from a channel"""
        try:
            await self._ensure_connected()
            channel = await self.client.get_entity(channel_name)
            
            messages = []
            async for message in self.client.iter_messages(channel, limit=limit):
                if message.message:
                    messages.append({
                        'id': message.id,
                        'text': message.message,
                        'date': message.date,
                        'views': getattr(message, 'views', 0),
                        'forwards': getattr(message, 'forwards', 0)
                    })
            
            return channel.id, messages
            
        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}")
            raise

    async def _scrape_channel_async(self, channel_name):
        """Scrape jobs from a channel"""
        await self._ensure_connected()
        logger.info(f"Starting to scrape channel: {channel_name}")
        
        channel_id, messages = await self._get_channel_messages(channel_name)
        logger.info(f"Retrieved {len(messages)} messages from channel {channel_name}")
        
        new_jobs_count = 0
        for message in messages:
            if await self._process_job_post(channel_id, channel_name, message):
                new_jobs_count += 1
        
        logger.info(f"Finished scraping channel {channel_name}. Added {new_jobs_count} new jobs.")
        return new_jobs_count

    async def _connect(self):
        """Connect and check authorization status"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
                
            if not await self.client.is_user_authorized():
                if not settings.TELEGRAM_PHONE:
                    raise ValueError("TELEGRAM_PHONE not set in environment variables")
                    
                self._phone_code_hash = await self.client.send_code_request(settings.TELEGRAM_PHONE)
                self._needs_verification = True
                self._is_connected = False
                logger.info("Verification code sent to Telegram phone number")
                return False
            
            self._is_connected = True
            self._needs_verification = False
            return True
            
        except Exception as e:
            self._is_connected = False
            logger.error(f"Connection error: {str(e)}")
            raise

    async def _verify_code(self, code):
        """Verify the Telegram code"""
        try:
            if not self._phone_code_hash:
                raise ValueError("No pending verification")
                
            await self.client.sign_in(
                phone=settings.TELEGRAM_PHONE,
                code=code,
                phone_code_hash=self._phone_code_hash.phone_code_hash
            )
            self._needs_verification = False
            self._is_connected = True
            return True
            
        except Exception as e:
            self._is_connected = False
            logger.error(f"Verification error: {str(e)}")
            raise

    async def _ensure_connected(self):
        """Ensure the client is connected and authorized"""
        if not self._is_connected:
            if not await self._connect():
                raise ValueError("Authentication required")

    def _run_async(self, coro):
        """Run a coroutine in the event loop"""
        try:
            return self._loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"Error in async operation: {str(e)}")
            raise

    def verify_code(self, code):
        """Verify Telegram code"""
        return self._run_async(self._verify_code(code))

    def scrape_channel(self, channel_name):
        """Scrape jobs from a channel"""
        return self._run_async(self._scrape_channel_async(channel_name))

    def needs_verification(self):
        """Check if verification is needed"""
        return self._needs_verification

    def is_connected(self):
        """Check if client is connected and authorized"""
        return self._is_connected

    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'client') and self.client.is_connected():
            try:
                self._run_async(self.client.disconnect())
            except:
                pass 