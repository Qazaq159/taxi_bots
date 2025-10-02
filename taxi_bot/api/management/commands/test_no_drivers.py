"""
Management command to test the no drivers available scenario
"""
from django.core.management.base import BaseCommand
from api.tasks import handle_no_drivers_available
from api.models import Ride


class Command(BaseCommand):
    help = 'Test the no drivers available notification system'

    def add_arguments(self, parser):
        parser.add_argument('ride_id', type=str, help='Ride ID to test with')

    def handle(self, *args, **options):
        ride_id = options['ride_id']
        
        try:
            # Check if ride exists
            ride = Ride.objects.get(id=ride_id)
            self.stdout.write(f'Testing no drivers scenario for ride: {ride_id}')
            self.stdout.write(f'Passenger: {ride.passenger.user.full_name}')
            self.stdout.write(f'Pickup: {ride.pickup_address}')
            
            # Test the no drivers available handler
            result = handle_no_drivers_available(ride_id)
            
            if result:
                self.stdout.write(
                    self.style.SUCCESS('✅ Successfully processed no drivers available scenario')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('❌ Failed to process no drivers available scenario')
                )
                
        except Ride.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Ride with ID {ride_id} does not exist')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error: {str(e)}')
            )
