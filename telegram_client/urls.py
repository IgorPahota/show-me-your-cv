from django.urls import path
from . import views

app_name = 'telegram_client'

urlpatterns = [
    path('verify/', views.verify_telegram, name='verify'),
] 