from django.core.management.base import BaseCommand

from bot_service.driver.main import main


class Command(BaseCommand):
    def handle(self, **options):
        print('Bot Started Driver!')
        main()
