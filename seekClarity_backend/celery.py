import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'seekClarity_backend.settings')

app = Celery('seekClarity')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()