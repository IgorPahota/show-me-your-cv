from django.apps import AppConfig


class JobScraperConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "job_scraper"
    verbose_name = "Job Scraper"

    def ready(self):
        import job_scraper.signals  # noqa
