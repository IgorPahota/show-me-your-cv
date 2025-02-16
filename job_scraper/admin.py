from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html
from .models import Job, TelegramChannel, Resume
from telegram_client.client import TelegramClient
from django.conf import settings
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from src.services.gemini_service import GeminiService
import uuid
import logging
import tempfile
import subprocess
import os


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_template', 'file_links', 'uploaded_at', 'updated_at')
    list_filter = ('is_template', 'uploaded_at')
    search_fields = ('title', 'description')
    readonly_fields = ('uploaded_at', 'updated_at')
    ordering = ('-uploaded_at',)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:resume_id>/download-pdf/',
                self.admin_site.admin_view(self.download_pdf_view),
                name='resume-download-pdf',
            ),
        ]
        return custom_urls + urls
    
    def file_links(self, obj):
        if obj.file:
            latex_link = format_html('<a href="{}" target="_blank">Download LaTeX</a>', obj.file.url)
            pdf_link = format_html(
                '<a href="{}" target="_blank">Download PDF</a>',
                reverse('admin:resume-download-pdf', args=[obj.pk])
            )
            return format_html('{} | {}', latex_link, pdf_link)
        return "No file"
    file_links.short_description = 'Resume Files'

    def download_pdf_view(self, request, resume_id):
        try:
            resume = Resume.objects.get(pk=resume_id)
            
            # Read LaTeX content
            resume.file.seek(0)
            latex_content = resume.file.read().decode('utf-8')
            
            # Create temporary directory for LaTeX compilation
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write LaTeX content to file
                tex_path = os.path.join(temp_dir, 'resume.tex')
                with open(tex_path, 'w', encoding='utf-8') as f:
                    f.write(latex_content)
                
                # Run pdflatex twice to resolve references
                for _ in range(2):
                    result = subprocess.run(
                        ['pdflatex', '-interaction=nonstopmode', 'resume.tex'],
                        capture_output=True,
                        text=True,
                        check=True,
                        cwd=temp_dir
                    )
                
                # Read the generated PDF
                pdf_path = os.path.join(temp_dir, 'resume.pdf')
                with open(pdf_path, 'rb') as pdf_file:
                    response = HttpResponse(pdf_file.read(), content_type='application/pdf')
                    # Change to inline to display in browser
                    response['Content-Disposition'] = f'inline; filename="{os.path.basename(resume.file.name).replace(".tex", ".pdf")}"'
                    return response
                    
        except Resume.DoesNotExist:
            messages.error(request, "Resume not found.")
            return HttpResponseRedirect(reverse('admin:job_scraper_resume_changelist'))
        except subprocess.CalledProcessError as e:
            messages.error(request, f"Failed to compile LaTeX: {e.stderr}")
            return HttpResponseRedirect(reverse('admin:job_scraper_resume_changelist'))
        except Exception as e:
            messages.error(request, f"Error generating PDF: {str(e)}")
            return HttpResponseRedirect(reverse('admin:job_scraper_resume_changelist'))


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'company_name', 'location', 'recruiter_contact', 'telegram_channel_name', 'telegram_message_date', 'has_resume')
    list_filter = ('telegram_channel_name', 'created_at', 'processed_by_llm')
    search_fields = ('title', 'company_name', 'location', 'description', 'recruiter_contact')
    ordering = ('-telegram_message_date',)
    readonly_fields = ('created_at', 'updated_at', 'processed_by_llm')
    raw_id_fields = ('resume',)
    actions = ['generate_resume']
    
    fieldsets = (
        ('Main Information', {
            'fields': (
                'title',
                'company_name',
                'location',
                'recruiter_contact',
                'description',
                'url',
            ),
            'classes': ('wide',)
        }),
        ('Job Details', {
            'fields': (
                'remote',
                'salary_min',
                'salary_max',
                'currency',
                'categories',
            ),
            'classes': ('collapse',)
        }),
        ('Telegram Information', {
            'fields': (
                'telegram_channel_name',
                'telegram_message_id',
                'telegram_channel_id',
                'telegram_message_date',
                'telegram_views',
                'telegram_forwards',
                'telegram_raw_text',
                'telegram_metadata',
            ),
            'classes': ('collapse',)
        }),
        ('Resume', {
            'fields': ('resume',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': (
                'job_id',
                'processed_by_llm',
                'extracted_data',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    def has_resume(self, obj):
        return bool(obj.resume)
    has_resume.boolean = True
    has_resume.short_description = 'Has Resume'

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Add dynamic actions for each template resume
        template_resumes = Resume.objects.filter(is_template=True)
        for template in template_resumes:
            action_name = f'generate_resume_from_template_{template.id}'
            action_function = self._create_template_action(template)
            actions[action_name] = (
                action_function,
                action_name,
                f'Generate resume using template: {template.title}'
            )
        return actions

    def _create_template_action(self, template_resume):
        def generate_resume_from_template(modeladmin, request, queryset):
            logger = logging.getLogger(__name__)
            logger.info(f"Starting resume generation with template: {template_resume.title}")

            if not settings.GEMINI_API_KEY:
                logger.error("Gemini API key not configured")
                messages.error(request, "Gemini API key is not configured. Please check your settings.")
                return

            gemini_service = GeminiService()
            success_count = 0
            error_count = 0

            for job in queryset:
                try:
                    logger.info(f"Processing job: {job.title}")
                    
                    # Check template file
                    if not template_resume.file:
                        logger.error("Template file is missing")
                        raise Exception("Template file is missing")
                        
                    # Log template file info
                    logger.info(f"Template file: {template_resume.file.name}")
                    logger.info(f"Template file size: {template_resume.file.size}")
                    
                    # Pass the file object directly to the service
                    template_resume.file.seek(0)  # Reset file pointer to beginning
                    logger.info("Calling adapt_template_resume")
                    latex_content = gemini_service.adapt_template_resume(template_resume.file, job.description)
                    
                    if not latex_content:
                        logger.error("No content generated")
                        raise Exception("No content generated")
                    
                    logger.info(f"Generated LaTeX content length: {len(latex_content)}")
                    
                    # Create unique filename for LaTeX
                    unique_id = uuid.uuid4().hex[:8]
                    latex_filename = f"resume_{unique_id}.tex"
                    logger.info(f"Generated filename: {latex_filename}")
                    
                    # Truncate job title if it's too long
                    truncated_title = job.title[:200] + "..." if len(job.title) > 200 else job.title
                    
                    # Create a new Resume object for the LaTeX
                    resume = Resume(
                        title=f"Modified Resume for {truncated_title} (Based on {template_resume.title})",
                        description=f"Modified from template: {template_resume.title}\nJob: {job.title}\nCompany: {job.company_name or 'Unknown Company'}"
                    )
                    
                    # Save the LaTeX file
                    logger.info("Saving LaTeX file")
                    resume.file.save(latex_filename, ContentFile(latex_content.encode('utf-8')), save=True)
                    
                    # Link the resume to the job
                    job.resume = resume
                    job.save()
                    logger.info("Successfully saved resume and linked to job")
                    
                    success_count += 1
                    messages.success(request, f"Successfully generated modified resume for: {truncated_title}")
                    
                except Exception as e:
                    logger.error(f"Error processing job {job.title}: {str(e)}")
                    error_count += 1
                    messages.error(request, f"Error generating resume for {job.title[:100]}...: {str(e)}")
            
            if success_count:
                logger.info(f"Successfully generated {success_count} resumes")
                messages.success(request, f"Successfully generated {success_count} resumes")
            if error_count:
                logger.warning(f"Failed to generate {error_count} resumes")
                messages.warning(request, f"Failed to generate {error_count} resumes")
                    
        generate_resume_from_template.short_description = f'Generate resume using template: {template_resume.title}'
        return generate_resume_from_template

    def generate_resume(self, request, queryset):
        if not settings.GEMINI_API_KEY:
            messages.error(request, "Gemini API key is not configured. Please check your settings.")
            return

        gemini_service = GeminiService()
        success_count = 0
        error_count = 0

        for job in queryset:
            try:
                # Generate resume text using Gemini
                resume_text = gemini_service.generate_resume(job.description)
                
                # Convert text to PDF
                pdf_bytes = gemini_service.create_pdf(resume_text)
                
                # Create a unique filename
                filename = f"resume_{uuid.uuid4().hex[:8]}.pdf"
                
                # Truncate job title if it's too long (leave room for prefix)
                truncated_title = job.title[:200] + "..." if len(job.title) > 200 else job.title
                
                # Create a new Resume object with truncated title
                resume = Resume(
                    title=f"AI Generated Resume for {truncated_title}",
                    description=f"Automatically generated resume for job: {job.title}\nCompany: {job.company_name or 'Unknown Company'}\nLocation: {job.location or 'Not specified'}"
                )
                
                # Save the PDF file
                resume.file.save(filename, ContentFile(pdf_bytes), save=True)
                
                # Link the resume to the job
                job.resume = resume
                job.save()
                
                success_count += 1
                messages.success(request, f"Successfully generated resume for: {truncated_title}")
                
            except Exception as e:
                error_count += 1
                messages.error(request, f"Error generating resume for {job.title[:100]}...: {str(e)}")
        
        if success_count:
            messages.success(request, f"Successfully generated {success_count} resumes")
        if error_count:
            messages.warning(request, f"Failed to generate {error_count} resumes")
            
    generate_resume.short_description = "Generate AI resume for selected jobs"


def update_channel_last_scraped(channel):
    """Update the last_scraped timestamp for a channel"""
    channel.last_scraped = timezone.now()
    channel.save()


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ('channel_name', 'is_active', 'last_scraped', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('channel_name',)
    ordering = ('channel_name',)
    readonly_fields = ('created_at', 'updated_at', 'last_scraped')
    actions = ['scrape_jobs', 'process_unprocessed_jobs']
    fieldsets = (
        (None, {
            'fields': ('channel_name', 'is_active', 'last_scraped')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('verify-telegram/', 
                 self.admin_site.admin_view(self.verify_telegram_view),
                 name='job_scraper_telegramchannel_verify'),
        ]
        return custom_urls + urls

    def verify_telegram_view(self, request):
        if request.method == 'POST':
            code = request.POST.get('code')
            if code:
                try:
                    client = TelegramClient()
                    client.verify_code(code)
                    messages.success(request, 'Telegram verification successful!')
                    return HttpResponseRedirect('../')
                except Exception as e:
                    messages.error(request, f'Verification failed: {str(e)}')
            else:
                messages.error(request, 'Please enter the verification code')

        context = {
            'title': 'Verify Telegram',
            'site_title': self.admin_site.site_title,
            'site_header': self.admin_site.site_header,
            'site_url': self.admin_site.site_url,
            'has_permission': self.admin_site.has_permission(request),
            'available_apps': self.admin_site.get_app_list(request),
        }
        
        return TemplateResponse(request, 'admin/verify_telegram.html', context)

    def scrape_jobs(self, request, queryset):
        try:
            client = TelegramClient()
            
            if client.needs_verification() or not client.is_connected():
                return HttpResponseRedirect(
                    reverse('admin:job_scraper_telegramchannel_verify')
                )
            
            success_count = 0
            error_count = 0
            new_jobs_ids = []  # Track newly scraped jobs
            
            for channel in queryset:
                if not channel.is_active:
                    messages.warning(request, f"Channel {channel.channel_name} is not active. Skipping.")
                    continue
                
                try:
                    new_jobs = client.scrape_channel(channel.channel_name)
                    # Get IDs of newly scraped jobs
                    new_jobs_ids.extend(Job.objects.filter(
                        telegram_channel_name=channel.channel_name,
                        processed_by_llm=False
                    ).values_list('id', flat=True))
                    
                    success_count += new_jobs
                    update_channel_last_scraped(channel)
                    messages.success(request, f"Successfully scraped {new_jobs} new jobs from {channel.channel_name}")
                except Exception as e:
                    error_count += 1
                    messages.error(request, f"Error scraping {channel.channel_name}: {str(e)}")
            
            # Process new jobs with Gemini
            if new_jobs_ids:
                self.process_jobs_with_gemini(new_jobs_ids)
                
        except Exception as e:
            messages.error(request, f"Error initializing Telegram client: {str(e)}")
            
    def process_unprocessed_jobs(self, request, queryset):
        """Process unprocessed jobs in batches of 10"""
        try:
            # Get all unprocessed jobs
            unprocessed_jobs = Job.objects.filter(processed_by_llm=False).order_by('-telegram_message_date')
            total_jobs = unprocessed_jobs.count()
            
            if total_jobs == 0:
                messages.info(request, "No unprocessed jobs found.")
                return
                
            # Process in batches of 10
            batch_size = 10
            processed_count = 0
            error_count = 0
            
            for i in range(0, total_jobs, batch_size):
                batch = unprocessed_jobs[i:i + batch_size]
                job_ids = [job.id for job in batch]
                
                try:
                    self.process_jobs_with_gemini(job_ids)
                    processed_count += len(batch)
                    messages.success(request, f"Successfully processed batch {i//batch_size + 1} ({len(batch)} jobs)")
                except Exception as e:
                    error_count += len(batch)
                    messages.error(request, f"Error processing batch {i//batch_size + 1}: {str(e)}")
            
            if processed_count:
                messages.success(request, f"Successfully processed {processed_count} jobs")
            if error_count:
                messages.warning(request, f"Failed to process {error_count} jobs")
                
        except Exception as e:
            messages.error(request, f"Error during batch processing: {str(e)}")
    
    process_unprocessed_jobs.short_description = "Process unprocessed jobs with LLM (batches of 10)"
    
    def process_jobs_with_gemini(self, job_ids):
        """Process jobs with Gemini to extract structured information"""
        gemini_service = GeminiService()
        logger = logging.getLogger(__name__)
        
        for job_id in job_ids:
            try:
                job = Job.objects.get(id=job_id)
                
                # Skip if already processed
                if job.processed_by_llm:
                    continue
                
                # Extract information using Gemini
                prompt = f"""Extract the following information from this job posting. Return a JSON object with these fields:
                - company_name: The name of the company (null if not found)
                - location: Work location or office location (null if not found)
                - recruiter_contact: Any contact information for the recruiter/HR (email, telegram username, phone, etc.) (null if not found)

                Focus on finding:
                1. Company name - look for phrases like "company:", "at", "with", or company names followed by common suffixes (Inc, LLC, Ltd)
                2. Location - look for city names, country names, or phrases like "location:", "based in", "office in"
                3. Recruiter contact - look for:
                   - Telegram usernames (starting with @)
                   - Email addresses
                   - Phone numbers
                   - Links to contact forms or profiles
                   - Phrases like "contact", "apply", "send CV to", "HR"

                Job Posting:
                {job.telegram_raw_text}
                """
                
                extracted_data = gemini_service.extract_job_info(prompt)
                
                # Update job with extracted information
                job.extracted_data = extracted_data
                job.processed_by_llm = True
                
                # Update fields from extracted data
                if extracted_data.get('company_name'):
                    job.company_name = extracted_data['company_name']
                if extracted_data.get('location'):
                    job.location = extracted_data['location']
                if extracted_data.get('recruiter_contact'):
                    job.recruiter_contact = extracted_data['recruiter_contact']
                
                job.save()
                logger.info(f"Successfully processed job {job_id} with Gemini")
                
            except Exception as e:
                logger.error(f"Error processing job {job_id} with Gemini: {str(e)}")
                raise  # Re-raise to handle in the batch processor

    scrape_jobs.short_description = "Scrape jobs from selected channels"
