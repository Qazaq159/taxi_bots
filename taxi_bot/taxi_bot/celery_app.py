"""
Celery app configuration for taxi_bot project
"""
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'taxi_bot.settings')

app = Celery('taxi_bot')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    'check-ride-timeouts': {
        'task': 'api.tasks.check_ride_timeouts',
        'schedule': 60.0,  # Run every minute
    },
}

app.conf.timezone = 'Asia/Almaty'


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
