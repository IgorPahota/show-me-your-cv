from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .client import TelegramClient

@staff_member_required
def verify_telegram(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        if code:
            try:
                client = TelegramClient()
                client.verify_code(code)
                messages.success(request, "Successfully verified with Telegram!")
                return redirect('admin:job_scraper_telegramchannel_changelist')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
    
    return render(request, 'telegram_client/verify.html')
