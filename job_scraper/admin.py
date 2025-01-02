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


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'file_link', 'uploaded_at', 'updated_at')
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
