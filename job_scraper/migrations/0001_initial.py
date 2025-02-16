# Generated by Django 4.2.17 on 2025-01-02 21:19

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Resume',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to='resumes/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf'])])),
                ('description', models.TextField(blank=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Resume',
                'verbose_name_plural': 'Resumes',
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='TelegramChannel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel_name', models.CharField(max_length=255, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('last_scraped', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_id', models.CharField(max_length=255, unique=True)),
                ('title', models.CharField(max_length=255)),
                ('company_name', models.CharField(blank=True, max_length=255, null=True)),
                ('location', models.CharField(blank=True, max_length=255, null=True)),
                ('description', models.TextField()),
                ('url', models.URLField(max_length=500)),
                ('remote', models.BooleanField(default=False)),
                ('salary_min', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('salary_max', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('currency', models.CharField(blank=True, max_length=3, null=True)),
                ('categories', models.JSONField(blank=True, default=list)),
                ('telegram_message_id', models.BigIntegerField()),
                ('telegram_channel_id', models.BigIntegerField()),
                ('telegram_channel_name', models.CharField(max_length=255)),
                ('telegram_message_date', models.DateTimeField()),
                ('telegram_views', models.IntegerField(default=0)),
                ('telegram_forwards', models.IntegerField(default=0)),
                ('telegram_raw_text', models.TextField()),
                ('telegram_metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resume', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='job_scraper.resume')),
            ],
            options={
                'ordering': ['-telegram_message_date'],
                'indexes': [models.Index(fields=['-telegram_message_date'], name='job_scraper_telegra_5683ec_idx'), models.Index(fields=['telegram_channel_name'], name='job_scraper_telegra_c5dbc6_idx'), models.Index(fields=['remote'], name='job_scraper_remote_14bf34_idx')],
            },
        ),
    ]
