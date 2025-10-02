"""
Management command to test driver notifications
"""
from django.core.management.base import BaseCommand
from api.utils import send_driver_notification


class Command(BaseCommand):
    help = 'Test driver notifications'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=str, help='Driver Telegram ID')
        parser.add_argument('notification_type', type=str, 
                          choices=['document_approved', 'document_rejected', 'driver_verified'],
                          help='Type of notification to send')
        parser.add_argument('--document-type', type=str, default='Driver License',
                          help='Document type for document notifications')

    def handle(self, *args, **options):
        telegram_id = options['telegram_id']
        notification_type = options['notification_type']
        document_type = options.get('document_type', 'Driver License')

        context_data = {}
        if notification_type in ['document_approved', 'document_rejected']:
            context_data['document_type'] = document_type

        success = send_driver_notification(telegram_id, notification_type, context_data)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully sent {notification_type} notification to {telegram_id}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'Failed to send {notification_type} notification to {telegram_id}')
            )
