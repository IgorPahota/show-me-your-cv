from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Job, TelegramChannel
from django.utils import timezone


@receiver(pre_save, sender=TelegramChannel)
def update_channel_timestamp(sender, instance, **kwargs):
    """Update the updated_at timestamp when a channel is modified."""
    instance.updated_at = timezone.now()


@receiver(pre_save, sender=Job)
def update_job_timestamp(sender, instance, **kwargs):
    """Update the updated_at timestamp when a job is modified."""
    instance.updated_at = timezone.now() 