from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
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


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_template', 'file_link', 'uploaded_at', 'updated_at')
    list_filter = ('is_template', 'uploaded_at')
    search_fields = ('title', 'description')
    readonly_fields = ('uploaded_at', 'updated_at')
    ordering = ('-uploaded_at',)
    
    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download PDF</a>', obj.file.url)
        return "No file"
    file_link.short_description = 'Resume File'


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'company_name', 'location', 'remote', 'telegram_channel_name', 'telegram_message_date', 'has_resume')
    list_filter = ('remote', 'telegram_channel_name', 'created_at')
    search_fields = ('title', 'company_name', 'location', 'description')
    ordering = ('-telegram_message_date',)
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('resume',)
    actions = ['generate_resume']
    fieldsets = (
        ('Basic Info', {
            'fields': ('job_id', 'title', 'company_name', 'location', 'description', 'url', 'remote')
        }),
        ('Resume', {
            'fields': ('resume',),
            'description': 'Attach a resume to this job application'
        }),
        ('Salary Info', {
            'fields': ('salary_min', 'salary_max', 'currency')
        }),
        ('Categories', {
            'fields': ('categories',)
        }),
        ('Telegram Metadata', {
            'fields': (
                'telegram_message_id', 'telegram_channel_id', 'telegram_channel_name',
                'telegram_message_date', 'telegram_views', 'telegram_forwards',
                'telegram_raw_text', 'telegram_metadata'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
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


@sync_to_async
def update_channel_last_scraped(channel):
    channel.last_scraped = timezone.now()
    channel.save()


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ('channel_name', 'is_active', 'last_scraped', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('channel_name',)
    ordering = ('channel_name',)
    readonly_fields = ('created_at', 'updated_at', 'last_scraped')
    actions = ['scrape_jobs']
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
        if not all([settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, settings.TELEGRAM_PHONE]):
            messages.error(request, "Telegram credentials are not properly configured. Please check your settings.")
            return

        try:
            client = TelegramClient()
            
            if client.needs_verification() or not client.is_connected():
                return HttpResponseRedirect(
                    reverse('admin:job_scraper_telegramchannel_verify')
                )
            
            success_count = 0
            error_count = 0
            
            for channel in queryset:
                if not channel.is_active:
                    messages.warning(request, f"Channel {channel.channel_name} is not active. Skipping.")
                    continue
                
                try:
                    new_jobs = client.scrape_channel(channel.channel_name)
                    success_count += new_jobs
                    sync_to_async(update_channel_last_scraped)(channel)
                    messages.success(request, f"Successfully scraped {new_jobs} new jobs from {channel.channel_name}")
                except ValueError as ve:
                    if "authentication required" in str(ve).lower():
                        return HttpResponseRedirect(
                            reverse('admin:job_scraper_telegramchannel_verify')
                        )
                    messages.error(request, f"Error with channel {channel.channel_name}: {str(ve)}")
                except Exception as e:
                    error_count += 1
                    messages.error(request, f"Error scraping {channel.channel_name}: {str(e)}")
            
            if success_count:
                messages.success(request, f"Successfully scraped {success_count} new jobs")
            if error_count:
                messages.warning(request, f"Failed to scrape {error_count} channels")
                
        except Exception as e:
            messages.error(request, f"Error initializing Telegram client: {str(e)}")
            
    scrape_jobs.short_description = "Scrape jobs from selected channels"
