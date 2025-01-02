from telethon import TelegramClient
from telethon.tl.functions.messages import SearchRequest, GetHistoryRequest
from telethon.tl.types import InputMessagesFilterEmpty
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from src.api_keys import TELEGRAM_API_ID, TELEGRAM_API_HASH
from src.models.database import Job, TelegramChannel, SessionLocal
import re
import asyncio
import os


class TelegramJobClient:
    def __init__(self):
        # Use a fixed path in the container for the session file
        self.session_file = "/app/sessions/telegram_session"
        # Ensure the sessions directory exists
        os.makedirs(os.path.dirname(self.session_file), exist_ok=True)

        print(f"Initializing Telegram client with session file: {self.session_file}")
        print(f"Session file exists: {os.path.exists(f'{self.session_file}.session')}")

        self.client = TelegramClient(
            self.session_file,
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            system_version="4.16.30-vxCUSTOM",
            device_model="Desktop",
        )
        self.db = SessionLocal()
        self.job_keywords = ["hiring", "job", "position", "role", "vacancy", "opening"]
        self.tech_categories = {
            "frontend": [
                "react",
                "vue",
                "angular",
                "javascript",
                "typescript",
                "frontend",
                "front-end",
                "web developer",
            ],
            "backend": [
                "python",
                "java",
                "golang",
                "nodejs",
                "backend",
                "back-end",
                "ruby",
                "php",
            ],
            "fullstack": ["full stack", "fullstack", "full-stack", "mern", "mean"],
            "mobile": ["ios", "android", "react native", "flutter", "mobile developer"],
            "devops": ["devops", "aws", "kubernetes", "docker", "ci/cd", "sre"],
            "data": [
                "data scientist",
                "machine learning",
                "ml",
                "ai",
                "data engineer",
                "big data",
            ],
            "blockchain": [
                "blockchain",
                "web3",
                "smart contract",
                "solidity",
                "ethereum",
            ],
            "security": [
                "security engineer",
                "penetration tester",
                "security analyst",
                "cybersecurity",
            ],
        }
        self.monitoring = False
        self.auth_retries = 0
        self.max_auth_retries = 3

    async def get_active_channels(self) -> List[str]:
        """Get list of active channels from database"""
        channels = (
            self.db.query(TelegramChannel)
            .filter(TelegramChannel.is_active == True)
            .all()
        )
        return [channel.channel_name for channel in channels]

    async def start_job_monitoring(self):
        """Start monitoring job channels"""
        self.monitoring = True
        while self.monitoring:
            try:
                channels = await self.get_active_channels()
                if not channels:
                    print("No active channels configured in database")
                    await asyncio.sleep(300)  # Wait 5 minutes before checking again
                    continue

                print(f"Found {len(channels)} active channels to monitor")
                for channel in channels:
                    try:
                        await self._scrape_recent_jobs(channel)
                    except Exception as e:
                        print(f"Error scraping channel {channel}: {str(e)}")

                # Wait for 30 minutes before next scrape
                await asyncio.sleep(1800)
            except Exception as e:
                print(f"Error in job monitoring: {str(e)}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _scrape_recent_jobs(self, channel_name: str = None, limit: int = 50):
        """Scrape recent jobs from specified channel or all channels"""
        print("\n=== Starting Job Scraping ===")
        print(f"Message limit per channel: {limit}")

        channels_to_scrape = (
            [channel_name] if channel_name else await self.get_active_channels()
        )

        if not channels_to_scrape:
            print("No channels configured for scraping!")
            return

        for channel in channels_to_scrape:
            try:
                print(f"\n{'='*50}")
                print(f"Processing channel: {channel}")
                print(f"{'='*50}\n")

                # Get channel entity
                channel_entity = await self.client.get_entity(channel)
                print(f"Successfully got entity for channel: {channel}")

                # Update channel name in database with actual username
                channel_record = (
                    self.db.query(TelegramChannel)
                    .filter(TelegramChannel.channel_name == channel)
                    .first()
                )
                if channel_record:
                    channel_record.last_scraped = datetime.utcnow()
                    self.db.commit()

                # Get recent messages
                print(f"Fetching up to {limit} messages...")
                messages = await self.client(
                    GetHistoryRequest(
                        peer=channel_entity,
                        limit=limit,
                        offset_date=None,
                        offset_id=0,
                        max_id=0,
                        min_id=0,
                        add_offset=0,
                        hash=0,
                    )
                )
                print(f"Fetched {len(messages.messages)} messages from {channel}")

                job_count = 0
                for message in messages.messages:
                    print(f"\n{'-'*80}")
                    print("MESSAGE CONTENT:")
                    print(f"{'-'*80}")
                    print(f"Message ID: {message.id}")
                    print(f"Date: {message.date}")
                    print(f"Content:\n{message.message}")
                    print(f"{'-'*80}")

                    if self._is_job_post(message.message):
                        print(f"Found job post in message {message.id}")
                        result = await self._process_message(message, "", None)
                        if result:
                            job_count += 1
                            print(f"Successfully processed job: {result['title']}")
                        else:
                            print("Failed to process job post")
                    else:
                        print("Not a job post - skipping")

                print(f"\nFinished processing {channel}. Found {job_count} jobs.")

            except Exception as e:
                print(f"Error scraping channel {channel}: {str(e)}")
                # Update channel status in database
                channel_record = (
                    self.db.query(TelegramChannel)
                    .filter(TelegramChannel.channel_name == channel)
                    .first()
                )
                if channel_record:
                    print(f"Marking channel {channel} as inactive due to error")
                    channel_record.is_active = False
                    self.db.commit()

        print("\n=== Job Scraping Complete ===\n")

    def _is_job_post(self, text: str) -> bool:
        """Check if the message is likely a job post"""
        if not text:
            return False
        text = text.lower()
        matches = [keyword for keyword in self.job_keywords if keyword in text]
        if matches:
            print(f"Job keywords found: {matches}")
            return True
        return False

    def _categorize_job(self, text: str) -> List[str]:
        """Categorize job based on technologies and keywords"""
        text = text.lower()
        categories = []
        for category, keywords in self.tech_categories.items():
            if any(keyword in text for keyword in keywords):
                categories.append(category)
        return categories

    async def _process_message(
        self, message, search_title: str, location: Optional[str]
    ) -> Optional[Dict]:
        """Process a Telegram message into a job posting"""
        try:
            print(f"\nProcessing message ID: {message.id}")
            print(f"Message date: {message.date}")
            print(f"Channel ID: {message.peer_id.channel_id}")

            # Extract relevant information from the message
            text = message.message
            lines = text.split("\n")

            # Try to extract title
            title = next(
                (
                    line
                    for line in lines
                    if any(keyword in line.lower() for keyword in self.job_keywords)
                ),
                lines[0],
            )
            print(f"Extracted title: {title}")

            # Create unique job ID
            job_id = f"tg_{message.id}_{message.peer_id.channel_id}"
            print(f"Generated job ID: {job_id}")

            # Check for existing job first
            print(f"Checking for existing job with ID: {job_id}")
            existing_job = self.db.query(Job).filter(Job.job_id == job_id).first()
            if existing_job:
                print(
                    f"Found existing job in database. Last updated: {existing_job.updated_at}"
                )

            # Try to extract company name
            company_pattern = r"(?i)(?:at|@|company:?)\s*([A-Za-z0-9\s]+(?:Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation)?)"
            company_match = re.search(company_pattern, text)
            company_name = (
                company_match.group(1) if company_match else "Unknown Company"
            )
            print(f"Extracted company: {company_name}")

            # Try to extract location
            location_pattern = r"(?i)(?:location:?|based in:?|remote|on-site|hybrid)\s*([A-Za-z0-9\s,]+)"
            location_match = re.search(location_pattern, text)
            job_location = (
                location_match.group(1)
                if location_match
                else location or "Location not specified"
            )
            print(f"Extracted location: {job_location}")

            # Try to extract salary
            salary_pattern = (
                r"(?i)(?:salary:?|compensation:?|pay:?)\s*([A-Za-z0-9\s\$\-\,]+)"
            )
            salary_match = re.search(salary_pattern, text)
            salary_text = salary_match.group(1) if salary_match else None
            print(f"Extracted salary text: {salary_text}")

            # Categorize job
            categories = self._categorize_job(text)
            print(f"Categorized as: {categories}")

            # Collect all available message metadata
            metadata = {
                "message_id": message.id,
                "from_id": message.from_id.user_id if message.from_id else None,
                "peer_id": message.peer_id.channel_id,
                "date": message.date.isoformat() if message.date else None,
                "post": message.post,
                "post_author": (
                    message.post_author if hasattr(message, "post_author") else None
                ),
                "views": message.views if hasattr(message, "views") else None,
                "forwards": message.forwards if hasattr(message, "forwards") else None,
                "replies": (
                    message.replies.replies if hasattr(message, "replies") else None
                ),
                "edit_date": (
                    message.edit_date.isoformat()
                    if hasattr(message, "edit_date") and message.edit_date
                    else None
                ),
                "has_media": (
                    bool(message.media) if hasattr(message, "media") else False
                ),
                "grouped_id": (
                    message.grouped_id if hasattr(message, "grouped_id") else None
                ),
            }
            print(f"Collected metadata: {metadata}")

            print("Creating job object...")
            # Store in database
            job = Job(
                job_id=job_id,
                title=title[:255],
                company_name=company_name[:255],
                location=job_location[:255],
                description=text,
                url=f"https://t.me/c/{message.peer_id.channel_id}/{message.id}",
                remote="remote" in text.lower(),
                salary_min=(
                    self._extract_salary_min(salary_text) if salary_text else None
                ),
                salary_max=(
                    self._extract_salary_max(salary_text) if salary_text else None
                ),
                currency="USD",  # Default currency
                categories=categories,
                created_at=message.date,
                # New Telegram specific fields
                telegram_message_id=message.id,
                telegram_channel_id=message.peer_id.channel_id,
                telegram_channel_name=str(
                    message.peer_id.channel_id
                ),  # We'll update this later with actual name
                telegram_message_date=message.date,
                telegram_views=message.views if hasattr(message, "views") else None,
                telegram_forwards=(
                    message.forwards if hasattr(message, "forwards") else None
                ),
                telegram_raw_text=text,
                telegram_metadata=metadata,
            )

            if existing_job:
                print("Updating existing job...")
                # Update existing job
                for key, value in job.__dict__.items():
                    if key != "_sa_instance_state" and value is not None:
                        setattr(existing_job, key, value)
                existing_job.updated_at = datetime.utcnow()
                job = existing_job
                print(f"Job updated. New update time: {job.updated_at}")
            else:
                print("Adding new job to database...")
                self.db.add(job)

            print("Committing to database...")
            try:
                self.db.commit()
                print("Successfully committed to database!")
                self.db.refresh(job)
                print(f"Job refreshed. ID: {job.job_id}, Title: {job.title}")
                return {
                    "id": job.job_id,
                    "title": job.title,
                    "company": job.company_name,
                    "location": job.location,
                    "description": job.description,
                    "url": job.url,
                    "remote": job.remote,
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "currency": job.currency,
                    "categories": job.categories,
                    "telegram_metadata": metadata,
                }
            except Exception as e:
                print(f"Error committing to database: {str(e)}")
                self.db.rollback()
                raise

        except Exception as e:
            print(f"Error processing Telegram message: {str(e)}")
            print("Rolling back database transaction...")
            self.db.rollback()
            return None

    def _extract_salary_min(self, salary_str: Optional[str]) -> Optional[float]:
        """Extract minimum salary from salary string"""
        if not salary_str:
            return None
        try:
            # Remove currency symbols and commas
            cleaned = re.sub(r"[^\d\-\s]", "", salary_str)
            # Find first number in string
            match = re.search(r"\d+", cleaned)
            if match:
                return float(match.group())
        except:
            return None

    def _extract_salary_max(self, salary_str: Optional[str]) -> Optional[float]:
        """Extract maximum salary from salary string"""
        if not salary_str:
            return None
        try:
            # Remove currency symbols and commas
            cleaned = re.sub(r"[^\d\-\s]", "", salary_str)
            # Find all numbers in string
            numbers = re.findall(r"\d+", cleaned)
            if len(numbers) > 1:
                return float(numbers[-1])
        except:
            return None

    def __del__(self):
        """Cleanup"""
        self.db.close()
        if self.client.is_connected():
            import asyncio

            asyncio.run(self.client.disconnect())

    async def start(self):
        """Start the client and ensure authentication"""
        try:
            print("\n=== Starting Telegram Client ===")
            print(f"Session file path: {self.session_file}")
            print(
                f"Session file exists: {os.path.exists(f'{self.session_file}.session')}"
            )

            await self.client.connect()

            # Check if we're already authorized
            is_authorized = await self.client.is_user_authorized()
            print(f"Client authorized: {is_authorized}")

            if is_authorized:
                print("Successfully loaded existing session")
                return True

            # If we're not authorized and have a session file, something is wrong
            if os.path.exists(f"{self.session_file}.session"):
                print("Warning: Session file exists but client is not authorized")
                print("This might indicate a corrupted or invalid session")
                return False

            # No valid session, need to authenticate
            phone = os.getenv("TELEGRAM_PHONE")
            if not phone:
                print("TELEGRAM_PHONE environment variable not set")
                return False

            print(
                f"No valid session found. Attempting to authenticate with phone number: {phone}"
            )
            result = await self.client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            print("Verification code has been sent. Please run:")
            print(
                f'docker exec -it show-me-your-cv-app-1 python3 -c \'from src.telegram_client import TelegramJobClient; import asyncio; asyncio.run(TelegramJobClient().enter_code("{phone}", "{phone_code_hash}"))\''
            )
            return False

        except Exception as e:
            print(f"Error during Telegram authentication: {str(e)}")
            return False

    async def enter_code(self, phone, phone_code_hash):
        """Helper method to enter verification code"""
        try:
            print("\n=== Starting Telegram Authentication ===")
            print(f"Phone number: {phone}")
            print(f"Phone code hash: {phone_code_hash}")

            await self.client.connect()
            if await self.client.is_user_authorized():
                print("Already authenticated!")
                return

            code = input("Please enter the verification code you received: ").strip()
            if not code:
                print("Error: Code cannot be empty")
                return

            print(f"Received code: {code}")
            print("Attempting to sign in...")

            try:
                await self.client.sign_in(
                    phone=phone, code=code, phone_code_hash=phone_code_hash
                )
                print("Authentication successful!")
            except Exception as e:
                print(f"Error during sign in: {str(e)}")

        except Exception as e:
            print(f"Error during code verification: {str(e)}")
        finally:
            await self.client.disconnect()
            print("=== Authentication Process Complete ===\n")

    async def stop(self):
        """Stop the client"""
        self.monitoring = False
        await self.client.disconnect()
