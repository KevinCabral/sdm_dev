from django.contrib.auth import logout
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from django.utils.timezone import make_aware

class AutoLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated and 'last_activity' in request.session:
            last_activity_str = request.session['last_activity']
            
            last_activity = make_aware(datetime.strptime(last_activity_str, '%Y-%m-%d %H:%M:%S'))
            idle_time = timezone.now() - last_activity

            if idle_time.total_seconds() > settings.AUTO_LOGOUT_DELAY:
                logout(request)

        request.session['last_activity'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')

        return response