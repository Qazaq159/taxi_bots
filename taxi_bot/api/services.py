"""
API Services for Bot Integration
Handles database operations for Telegram bots
"""
import random
import string
import requests
from decimal import Decimal
from geopy.distance import geodesic
from django.db import transaction
from django.db import models
from django.utils import timezone
from django.conf import settings
from .models import User, Passenger, Driver, Vehicle, DriverDocument, Ride, Rating
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations"""

    @staticmethod
    def get_or_create_user(telegram_id, username=None, full_name=None, language='kaz'):
        """Get existing user or create new one"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            return user, False
        except User.DoesNotExist:
            # Create new user
            if not username:
                username = f"user_{telegram_id}"

            user = User.objects.create(
                username=username,
                telegram_id=telegram_id,
                full_name=full_name or '',
                language=language
            )
            return user, True

    @staticmethod
    def update_user_language(telegram_id, language):
        """Update user language preference"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            user.language = language
            user.save()
            return True
        except User.DoesNotExist:
            return False

    @staticmethod
    def get_user_by_phone(phone_number):
        """Get user by phone number"""
        try:
            # Clean phone number for search
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            if not cleaned_phone.startswith('7') and cleaned_phone.startswith('8'):
                cleaned_phone = '7' + cleaned_phone[1:]
            if not cleaned_phone.startswith('+'):
                cleaned_phone = '+' + cleaned_phone

            user = User.objects.get(phone_number=cleaned_phone, is_phone_verified=True)
            return user
        except User.DoesNotExist:
            return None

    @staticmethod
    def verify_phone_number(telegram_id, phone_number):
        """Verify phone number using Telegram contact"""
        try:
            user = User.objects.get(telegram_id=telegram_id)

            # Clean phone number (remove spaces, dashes, etc.)
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            if not cleaned_phone.startswith('7') and cleaned_phone.startswith('8'):
                cleaned_phone = '7' + cleaned_phone[1:]
            if not cleaned_phone.startswith('+'):
                cleaned_phone = '+' + cleaned_phone

            user.phone_number = cleaned_phone
            user.is_phone_verified = True
            user.save()

            logger.info(f"Phone verified for user {telegram_id}: {cleaned_phone}")
            return True, cleaned_phone
        except User.DoesNotExist:
            logger.error(f"User not found for telegram_id: {telegram_id}")
            return False, None
        except Exception as e:
            logger.error(f"Error verifying phone for {telegram_id}: {str(e)}")
            return False, None


class PassengerService:
    """Service for passenger operations"""

    @staticmethod
    def get_or_create_passenger(telegram_id):
        """Get or create passenger profile"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            passenger, created = Passenger.objects.get_or_create(user=user)
            return passenger, created
        except User.DoesNotExist:
            return None, False

    @staticmethod
    def update_current_address(telegram_id, address):
        """Update passenger's current address"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            passenger = user.passenger_profile
            passenger.current_address = address
            passenger.save()
            return True
        except (User.DoesNotExist, Passenger.DoesNotExist):
            return False

    @staticmethod
    def get_passenger_by_telegram_id(telegram_id):
        """Get passenger by telegram ID"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            return user.passenger_profile
        except (User.DoesNotExist, Passenger.DoesNotExist):
            return None

    @staticmethod
    def get_user_by_telegram_id(telegram_id):
        """Get user by telegram ID"""
        try:
            return User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            return None


    @staticmethod
    def create_ride_request(telegram_id, pickup_address, pickup_lat, pickup_lng,
                           destination_address, destination_lat, destination_lng):
        """Create new ride request with fixed pricing"""
        try:
            from .models import AppSettings

            print(f"[PASSENGER_LOG] Creating ride request for {telegram_id}")
            print(f"[PASSENGER_LOG] Pickup: {pickup_address} ({pickup_lat}, {pickup_lng})")
            print(f"[PASSENGER_LOG] Destination: {destination_address} ({destination_lat}, {destination_lng})")

            user = User.objects.get(telegram_id=telegram_id)
            print(f"[PASSENGER_LOG] Found user: {user}, phone verified: {user.is_phone_verified}")

            passenger = user.passenger_profile
            print(f"[PASSENGER_LOG] Found passenger profile: {passenger}")

            # Calculate distance for duration estimate only
            pickup = (float(pickup_lat), float(pickup_lng))
            destination = (float(destination_lat), float(destination_lng))
            distance_km = geodesic(pickup, destination).kilometers

            # Use fixed cost from settings
            estimated_cost = AppSettings.get_default_ride_cost()

            print(f"[PASSENGER_LOG] Creating ride object with estimated_cost: {estimated_cost}")

            ride = Ride.objects.create(
                passenger=passenger,
                pickup_address=pickup_address,
                pickup_lat=pickup_lat,
                pickup_lng=pickup_lng,
                destination_address=destination_address,
                destination_lat=destination_lat,
                destination_lng=destination_lng,
                estimated_cost=estimated_cost,
                current_cost=estimated_cost  # Set initial current cost
            )

            print(f"[PASSENGER_LOG] Ride created successfully with ID: {ride.id}")
            return ride, distance_km, int((distance_km / 30) * 60)  # estimated duration
        except Exception as e:
            print(f"[PASSENGER_LOG] ERROR creating ride for {telegram_id}: {str(e)}")
            logger.error(f"Error creating ride for {telegram_id}: {str(e)}")
            return None, None, None

    @staticmethod
    def boost_ride_fare(telegram_id, ride_id):
        """Boost the fare for a ride and re-notify drivers"""
        try:
            from .models import Ride

            user = User.objects.get(telegram_id=telegram_id)
            passenger = user.passenger_profile

            # Get the ride and verify ownership
            ride = Ride.objects.get(id=ride_id, passenger=passenger, status='requested')

            # Boost the fare
            success, message = ride.boost_fare()

            if success:
                # Re-notify drivers with the new fare
                try:
                    from .tasks import notify_drivers_about_boosted_ride
                    notify_drivers_about_boosted_ride.delay(ride.id)
                except ImportError:
                    # Fallback without Celery
                    logger.warning(f"Celery not available for ride boost notification {ride.id}")

                return True, message, ride.display_cost
            else:
                return False, message, None

        except Ride.DoesNotExist:
            return False, "Ride not found or cannot be boosted", None
        except Exception as e:
            logger.error(f"Error boosting ride fare for {telegram_id}: {str(e)}")
            return False, "Error boosting fare", None

    @staticmethod
    def get_passenger_rides(telegram_id, status=None, limit=10):
        """Get passenger's ride history with optional filtering"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            passenger = user.passenger_profile

            rides = passenger.rides.all()
            if status:
                rides = rides.filter(status=status)

            rides = rides.order_by('-created_at')
            if limit:
                rides = rides[:limit]

            return rides
        except (User.DoesNotExist, Passenger.DoesNotExist):
            return []

    @staticmethod
    def get_nearby_rides_for_new_ride(ride, radius_km=5):
        """
        Get all online verified drivers for a newly created ride
        NOTE: Now ignores location and radius - sends to ALL online drivers

        Args:
            ride: Ride object with pickup_lat, pickup_lng
            radius_km: Search radius in kilometers (IGNORED - kept for compatibility)

        Returns:
            List of dicts with 'driver' and 'distance_km' keys
        """
        try:
            pickup_location = (float(ride.pickup_lat), float(ride.pickup_lng))
            available_drivers = []

            # Find all online and verified drivers - IGNORE location and distance
            for driver in Driver.objects.filter(is_online=True, is_verified=True):
                distance_km = 0  # Default distance

                # Calculate distance if location is available, but don't filter by it
                if driver.current_lat and driver.current_lng:
                    try:
                        driver_location = (float(driver.current_lat), float(driver.current_lng))
                        distance_km = round(geodesic(driver_location, pickup_location).kilometers, 2)
                    except:
                        distance_km = 0  # If calculation fails, use 0

                # Add driver regardless of distance or location
                available_drivers.append({
                    'driver': driver,
                    'distance_km': distance_km
                })

            # Sort by distance (closest first, drivers without location will be at the top)
            available_drivers.sort(key=lambda x: x['distance_km'])
            return available_drivers

        except Exception as e:
            import logging
            logging.error(f"Error finding available drivers for ride {ride.id}: {str(e)}")
            return []


class DriverService:
    """Service for driver operations"""

    @staticmethod
    def get_or_create_driver(telegram_id):
        """Get or create driver profile"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver, created = Driver.objects.get_or_create(user=user)
            return driver, created
        except User.DoesNotExist:
            return None, False

    @staticmethod
    def update_driver_location(telegram_id, lat, lng):
        """Update driver's current location"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile
            driver.current_lat = lat
            driver.current_lng = lng
            driver.save()
            return True
        except (User.DoesNotExist, Driver.DoesNotExist):
            return False

    @staticmethod
    def set_driver_online_status(telegram_id, is_online):
        """Set driver online/offline status"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile

            if not driver.is_verified:
                return False, "Driver not verified"

            driver.is_online = is_online
            driver.save()
            return True, "Status updated"
        except (User.DoesNotExist, Driver.DoesNotExist):
            return False, "Driver not found"

    @staticmethod
    def update_driver_status(telegram_id, is_online):
        """Update driver online status (simplified version)"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile
            driver.is_online = is_online
            driver.save()
            return driver
        except (User.DoesNotExist, Driver.DoesNotExist):
            return None

    @staticmethod
    def get_driver_by_telegram_id(telegram_id):
        """Get driver by telegram ID"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            return user.driver_profile
        except (User.DoesNotExist, Driver.DoesNotExist):
            return None

    @staticmethod
    def get_user_by_telegram_id(telegram_id):
        """Get user by telegram ID"""
        try:
            return User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_driver_rides(telegram_id, limit=10):
        """Get driver's recent rides"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile
            return driver.rides.order_by('-created_at')[:limit]
        except (User.DoesNotExist, Driver.DoesNotExist):
            return []

    @staticmethod
    def create_vehicle(telegram_id, make, model, year, color, license_plate):
        """Create vehicle for driver"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile

            # Delete existing vehicle if any
            if hasattr(driver, 'vehicle'):
                driver.vehicle.delete()

            vehicle = Vehicle.objects.create(
                driver=driver,
                make=make,
                model=model,
                year=year,
                color=color,
                license_plate=license_plate
            )
            return vehicle
        except Exception as e:
            logger.error(f"Error creating vehicle for {telegram_id}: {str(e)}")
            return None

    @staticmethod
    def get_nearby_rides(telegram_id, radius_km=5):
        """Get nearby ride requests for driver"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile

            if not driver.is_online or not driver.is_verified:
                return []

            if not driver.current_lat or not driver.current_lng:
                return []

            driver_location = (float(driver.current_lat), float(driver.current_lng))
            nearby_rides = []

            for ride in Ride.objects.filter(status='requested'):
                pickup_location = (float(ride.pickup_lat), float(ride.pickup_lng))
                distance = geodesic(driver_location, pickup_location).kilometers

                if distance <= radius_km:
                    ride_data = {
                        'ride': ride,
                        'distance_km': round(distance, 2)
                    }
                    nearby_rides.append(ride_data)

            # Sort by distance
            nearby_rides.sort(key=lambda x: x['distance_km'])
            return nearby_rides

        except Exception as e:
            logger.error(f"Error getting nearby rides for {telegram_id}: {str(e)}")
            return []

    @staticmethod
    def accept_ride(telegram_id, ride_id):
        """Accept a ride request"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile

            # Check if driver has active rides
            active_rides = Ride.objects.filter(
                driver=driver,
                status__in=['assigned', 'driver_enroute', 'driver_arrived', 'in_progress']
            )

            if active_rides.exists():
                return False, "У вас есть активная поездка. Завершите её перед принятием новой."

            ride = Ride.objects.get(id=ride_id, status='requested')
            ride.driver = driver
            ride.update_status('assigned', 'Driver assigned')

            return True, ride
        except Ride.DoesNotExist:
            return False, "Ride not available"
        except Exception as e:
            logger.error(f"Error accepting ride for {telegram_id}: {str(e)}")
            return False, "Error accepting ride"

    @staticmethod
    def get_driver_earnings(telegram_id):
        """Get driver earnings summary"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            driver = user.driver_profile

            completed_rides = driver.rides.filter(status='completed')
            today_rides = completed_rides.filter(completed_at__date=timezone.now().date())

            total_earnings = sum(ride.final_cost or 0 for ride in completed_rides)
            today_earnings = sum(ride.final_cost or 0 for ride in today_rides)

            return {
                'balance': driver.balance,
                'total_rides': driver.total_rides,
                'average_rating': driver.average_rating,
                'total_earnings': total_earnings,
                'today_earnings': today_earnings,
                'today_rides_count': today_rides.count()
            }
        except Exception as e:
            logger.error(f"Error getting earnings for {telegram_id}: {str(e)}")
            return None


class RideService:
    """Service for ride management"""

    @staticmethod
    def update_ride_status(ride_id, new_status, notes='', telegram_id=None):
        """Update ride status"""
        try:
            ride = Ride.objects.get(id=ride_id)

            # Verify user has permission to update
            if telegram_id:
                user = User.objects.get(telegram_id=telegram_id)
                if not (
                    (hasattr(user, 'passenger_profile') and ride.passenger.user == user) or
                    (hasattr(user, 'driver_profile') and ride.driver and ride.driver.user == user)
                ):
                    return False, "Permission denied"

            ride.update_status(new_status, notes)

            # Update counters on completion
            if new_status == 'completed':
                if ride.driver:
                    ride.driver.total_rides += 1
                    ride.driver.save()

                ride.passenger.total_rides += 1
                ride.passenger.save()

            return True, ride
        except Exception as e:
            logger.error(f"Error updating ride status: {str(e)}")
            return False, None

    @staticmethod
    def cancel_ride(ride_id, telegram_id, reason=''):
        """Cancel a ride"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            ride = Ride.objects.get(id=ride_id)

            # Determine cancellation type
            if hasattr(user, 'passenger_profile') and ride.passenger.user == user:
                status = 'cancelled_by_passenger'
            elif hasattr(user, 'driver_profile') and ride.driver and ride.driver.user == user:
                status = 'cancelled_by_driver'
            else:
                return False, "Permission denied"

            ride.update_status(status, reason)
            return True, ride
        except Exception as e:
            logger.error(f"Error cancelling ride: {str(e)}")
            return False, None

    @staticmethod
    def increase_ride_cost(ride_id, telegram_id):
        """Increase ride cost to attract more drivers"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            ride = Ride.objects.get(id=ride_id)

            # Check if user is the passenger
            if not hasattr(user, 'passenger_profile') or ride.passenger.user != user:
                return False, "Permission denied"

            # Check if ride is still in requested status
            if ride.status != 'requested':
                return False, "Ride already assigned or in progress"

            # Use the ride's boost_fare method which uses App Settings
            success, message = ride.boost_fare()

            if not success:
                return False, message

            logger.info(f"Boosted fare for ride {ride_id}: {message}")

            # Re-notify drivers with updated cost
            from api.tasks import notify_drivers_about_boosted_ride
            notify_drivers_about_boosted_ride.delay(str(ride.id))

            return True, ride

        except Exception as e:
            logger.error(f"Error increasing ride cost: {str(e)}")
            return False, None

    @staticmethod
    def rate_ride(ride_id, telegram_id, stars, comment=''):
        """Rate a completed ride"""
        try:
            user = User.objects.get(telegram_id=telegram_id)
            ride = Ride.objects.get(id=ride_id, status='completed')

            # Check if already rated
            if Rating.objects.filter(ride=ride, rated_by=user).exists():
                return False, "Already rated"

            # Determine who is being rated
            if hasattr(user, 'passenger_profile') and ride.passenger.user == user:
                rated_user = ride.driver.user
            elif hasattr(user, 'driver_profile') and ride.driver.user == user:
                rated_user = ride.passenger.user
            else:
                return False, "Permission denied"

            rating = Rating.objects.create(
                ride=ride,
                rated_by=user,
                rated_user=rated_user,
                stars=stars,
                comment=comment
            )

            # Update driver's average rating if passenger rated driver
            if hasattr(user, 'passenger_profile'):
                driver = ride.driver
                avg_rating = Rating.objects.filter(
                    rated_user=driver.user
                ).aggregate(avg=models.Avg('stars'))['avg']
                driver.average_rating = avg_rating or 0
                driver.save()

            return True, rating
        except Exception as e:
            logger.error(f"Error rating ride: {str(e)}")
            return False, None


def send_sms_code(phone_number):
    """Send SMS verification code (placeholder)"""
    # Generate 4-digit code
    code = ''.join(random.choices(string.digits, k=4))

    # TODO: Integrate with SMS service (e.g., Twilio, SMS.ru, etc.)
    logger.info(f"SMS code for {phone_number}: {code}")

    return code


def geocode_address(address):
    """Geocode address to coordinates (placeholder)"""
    # TODO: Integrate with geocoding service (Google Maps, Yandex, etc.)
    # For now, return dummy coordinates for Almaty
    return 43.2220, 76.8512
