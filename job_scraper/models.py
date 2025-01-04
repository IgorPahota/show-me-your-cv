from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator
import os


class TelegramChannel(models.Model):
    channel_name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.channel_name


class Resume(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(
        upload_to='resumes/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])]
    )
    description = models.TextField(blank=True)
    is_template = models.BooleanField(default=False, help_text="Mark this resume as a template for generating other resumes")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} {'(Template)' if self.is_template else ''}"

    def delete(self, *args, **kwargs):
        # Delete the file when the model instance is deleted
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
        super().delete(*args, **kwargs)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Resume'
        verbose_name_plural = 'Resumes'


class Job(models.Model):
    # Unique identifier
    job_id = models.CharField(max_length=255, unique=True)
    
    # Basic job information
    title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField()
    url = models.URLField(max_length=500)
    remote = models.BooleanField(default=False)
    
    # Salary information
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, null=True, blank=True)  # e.g., USD, EUR
    
    # Categories and tags
    categories = models.JSONField(default=list, blank=True)
    
    # Telegram-specific fields
    telegram_message_id = models.BigIntegerField()
    telegram_channel_id = models.BigIntegerField()
    telegram_channel_name = models.CharField(max_length=255)
    telegram_message_date = models.DateTimeField()
    telegram_views = models.IntegerField(default=0)
    telegram_forwards = models.IntegerField(default=0)
    telegram_raw_text = models.TextField()
    telegram_metadata = models.JSONField(default=dict, blank=True)
    
    # Resume association
    resume = models.ForeignKey(Resume, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-telegram_message_date']
        indexes = [
            models.Index(fields=['-telegram_message_date']),
            models.Index(fields=['telegram_channel_name']),
            models.Index(fields=['remote']),
        ]

    def __str__(self):
        return f"{self.title} ({self.telegram_channel_name})"
