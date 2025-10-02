from django.core.management.base import BaseCommand

from bot_service.passenger.main import main


class Command(BaseCommand):
    def handle(self, **options):
        print('Bot Started Passenger!')
        main()
