"""
Celery Tasks for Asynchronous Operations
Handles background tasks like notifications, ride matching, etc.
"""
import os
import sys
from celery import shared_task
from django.conf import settings

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logger = logging.getLogger(__name__)


@shared_task
def notify_drivers_about_new_ride(ride_id):
    """Notify nearby drivers about a new ride request"""
    try:
        from api.models import Ride
        from api.services import DriverService, PassengerService

        # Get the ride
        ride = Ride.objects.get(id=ride_id, status='requested')

        # Find nearby drivers
        nearby_drivers = PassengerService.get_nearby_rides_for_new_ride(ride)

        if not nearby_drivers:
            logger.warning(f"No drivers found for ride {ride_id}")
            return False

        # Send notifications to each driver
        notifications_sent = 0
        for driver_data in nearby_drivers:
            driver = driver_data['driver']
            distance = driver_data['distance_km']

            success = send_driver_notification(
                driver.user.telegram_id,
                ride,
                distance
            )

            if success:
                notifications_sent += 1

        logger.info(f"Sent {notifications_sent} notifications for ride {ride_id}")
        return notifications_sent > 0

    except Exception as e:
        logger.error(f"Error notifying drivers about ride {ride_id}: {str(e)}")
        return False


@shared_task
def notify_passenger_driver_assigned(ride_id):
    """Notify passenger when driver is assigned"""
    try:
        from api.models import Ride

        ride = Ride.objects.get(id=ride_id, status='assigned')

        if ride.driver:
            success = send_passenger_notification(
                ride.passenger.user.telegram_id,
                ride.driver
            )

            logger.info(f"Notified passenger {ride.passenger.user.telegram_id} about driver assignment")
            return success

    except Exception as e:
        logger.error(f"Error notifying passenger about ride {ride_id}: {str(e)}")
        return False


def send_driver_notification(driver_telegram_id, ride, distance_km):
    """Send Telegram notification to driver"""
    try:
        from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
        from bot_service.driver.dictionary import translations
        from api.models import User

        # Get bot token
        bot_token = os.getenv('TG_BOT_TOKEN_DRIVER')
        if not bot_token:
            logger.error("Driver bot token not found")
            return False

        bot = Bot(token=bot_token)

        # Get driver language
        try:
            driver_user = User.objects.get(telegram_id=str(driver_telegram_id))
            language = driver_user.language
        except:
            language = 'kaz'

        # Create notification message
        pickup_address = ride.pickup_address[:50] + "..." if len(ride.pickup_address) > 50 else ride.pickup_address
        destination_address = ride.destination_address[:50] + "..." if len(ride.destination_address) > 50 else ride.destination_address

        message = translations['new_ride_request'][language].format(
            pickup=pickup_address,
            destination=destination_address,
            cost=int(ride.display_cost),
            distance=round(distance_km, 1) if distance_km > 0 else "N/A"
        )

        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    translations['buttons']['accept'][language],
                    callback_data=f"accept_ride_{ride.id}"
                ),
                InlineKeyboardButton(
                    translations['buttons']['reject'][language],
                    callback_data=f"reject_ride_{ride.id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send notification and get message object
        sent_message = bot.send_message(
            chat_id=driver_telegram_id,
            text=message,
            reply_markup=reply_markup
        )

        # Schedule auto-reject task with message ID for deletion
        auto_reject_ride.apply_async(
            args=[ride.id, driver_telegram_id, sent_message.message_id],
            countdown=60  # 60 seconds delay (1 minute)
        )

        return True

    except Exception as e:
        logger.error(f"Error sending notification to driver {driver_telegram_id}: {str(e)}")
        return False


def send_passenger_notification(passenger_telegram_id, driver):
    """Send Telegram notification to passenger"""
    try:
        from telegram import Bot
        from bot_service.passenger.dictionary import translations
        from api.models import User

        # Get bot token
        bot_token = os.getenv('TG_BOT_TOKEN_PASSENGER')
        if not bot_token:
            logger.error("Passenger bot token not found")
            return False

        bot = Bot(token=bot_token)

        # Get passenger language
        try:
            passenger_user = User.objects.get(telegram_id=str(passenger_telegram_id))
            language = passenger_user.language
        except:
            language = 'kaz'

        # Create driver assignment message
        message = translations['driver_assigned'][language].format(
            driver_name=driver.user.full_name,
            rating=driver.average_rating,
            car=f"{driver.vehicle.make} {driver.vehicle.model}" if driver.vehicle else "N/A",
            phone=driver.user.phone_number
        )

        # Send notification
        bot.send_message(
            chat_id=passenger_telegram_id,
            text=message
        )

        return True

    except Exception as e:
        logger.error(f"Error sending notification to passenger {passenger_telegram_id}: {str(e)}")
        return False


@shared_task
def auto_reject_ride(ride_id, driver_telegram_id, message_id=None):
    """Auto-reject ride after timeout - delete original message and reassign to another driver"""
    try:
        from api.models import Ride
        from telegram import Bot
        from bot_service.driver.dictionary import translations
        from api.models import User

        # Check if ride is still available
        ride = Ride.objects.get(id=ride_id, status='requested')

        # Get driver language
        try:
            driver_user = User.objects.get(telegram_id=str(driver_telegram_id))
            language = driver_user.language
        except:
            language = 'kaz'

        # Delete original message if message_id is provided
        bot_token = os.getenv('TG_BOT_TOKEN_DRIVER')
        if bot_token and message_id:
            try:
                bot = Bot(token=bot_token)
                bot.delete_message(
                    chat_id=driver_telegram_id,
                    message_id=message_id
                )
                logger.info(f"Deleted original ride notification message {message_id} for driver {driver_telegram_id}")
            except Exception as e:
                logger.warning(f"Could not delete original message {message_id}: {str(e)}")

        # Send timeout message
        if bot_token:
            bot = Bot(token=bot_token)
            bot.send_message(
                chat_id=driver_telegram_id,
                text=translations['ride_timeout'][language]
            )

        # Reassign ride to another driver
        try:
            reassign_ride_to_next_driver(ride_id, driver_telegram_id)
        except Exception as e:
            logger.error(f"Error reassigning ride {ride_id}: {str(e)}")

        logger.info(f"Auto-rejected ride {ride_id} for driver {driver_telegram_id}, reassigned to another driver")
        return True

    except Ride.DoesNotExist:
        # Ride already taken or cancelled
        logger.info(f"Ride {ride_id} no longer available for auto-reject")
        return True
    except Exception as e:
        logger.error(f"Error auto-rejecting ride {ride_id}: {str(e)}")
        return False


def reassign_ride_to_next_driver(ride_id, exclude_driver_telegram_id=None):
    """Reassign ride to the next available driver (excluding the one who timed out)"""
    try:
        from api.models import Ride
        from api.services import PassengerService

        # Get the ride
        ride = Ride.objects.get(id=ride_id, status='requested')

        # Find available drivers (same logic as original notification)
        available_drivers = PassengerService.get_nearby_rides_for_new_ride(ride)

        if not available_drivers:
            logger.warning(f"No drivers available for ride {ride_id}")
            # Cancel the ride since no drivers are available
            cancel_ride_no_drivers(ride_id)
            return False

        # Find the next driver (excluding the one who timed out)
        next_driver = None
        for driver_data in available_drivers:
            driver = driver_data['driver']
            if exclude_driver_telegram_id and str(driver.user.telegram_id) == str(exclude_driver_telegram_id):
                continue  # Skip the driver who timed out
            next_driver = driver_data
            break

        if not next_driver:
            logger.warning(f"No other drivers available for ride {ride_id} (excluding {exclude_driver_telegram_id})")
            # Cancel the ride since only the excluded driver is available
            cancel_ride_no_drivers(ride_id)
            return False

        driver = next_driver['driver']
        distance = next_driver['distance_km']

        logger.info(f"Reassigning ride {ride_id} to driver {driver.user.telegram_id} (excluding {exclude_driver_telegram_id})")

        # Send notification to the next driver
        success = send_driver_notification(
            driver.user.telegram_id,
            ride,
            distance
        )

        if success:
            logger.info(f"Successfully reassigned ride {ride_id} to driver {driver.user.telegram_id}")
        else:
            logger.error(f"Failed to notify driver {driver.user.telegram_id} about reassigned ride {ride_id}")
            # If notification failed, try to cancel the ride
            cancel_ride_no_drivers(ride_id)

        return success

    except Exception as e:
        logger.error(f"Error reassigning ride {ride_id}: {str(e)}")
        return False


def cancel_ride_no_drivers(ride_id):
    """Cancel a ride when no drivers are available"""
    try:
        from api.models import Ride

        ride = Ride.objects.get(id=ride_id, status='requested')

        # Cancel the ride directly (system cancellation)
        ride.update_status('cancelled_by_system', "No drivers available")
        logger.info(f"Cancelled ride {ride_id} due to no available drivers")

        # Notify passenger
        try:
            notify_passenger_ride_cancelled.delay(ride_id)
        except:
            logger.warning(f"Could not schedule passenger notification for cancelled ride {ride_id}")

        return True

    except Exception as e:
        logger.error(f"Error cancelling ride {ride_id} due to no drivers: {str(e)}")
        return False


@shared_task
def check_ride_timeouts():
    """Check for rides that have been waiting too long and cancel them"""
    try:
        from api.models import Ride
        from django.utils import timezone
        from datetime import timedelta

        # Find rides that have been waiting for more than 10 minutes
        timeout_threshold = timezone.now() - timedelta(minutes=10)
        stale_rides = Ride.objects.filter(
            status='requested',
            created_at__lt=timeout_threshold
        )

        cancelled_count = 0
        for ride in stale_rides:
            ride.update_status('cancelled_by_system', 'No drivers available')
            cancelled_count += 1

            # Notify passenger about cancellation
            notify_passenger_ride_cancelled.delay(ride.id)

        logger.info(f"Cancelled {cancelled_count} stale rides")
        return cancelled_count

    except Exception as e:
        logger.error(f"Error checking ride timeouts: {str(e)}")
        return 0


@shared_task
def notify_passenger_ride_cancelled(ride_id):
    """Notify passenger that their ride was cancelled"""
    try:
        from api.models import Ride
        from telegram import Bot
        from bot_service.passenger.dictionary import translations

        ride = Ride.objects.get(id=ride_id)
        passenger = ride.passenger

        # Get bot token
        bot_token = os.getenv('TG_BOT_TOKEN_PASSENGER')
        if not bot_token:
            return False

        bot = Bot(token=bot_token)
        language = passenger.user.language

        # Send cancellation message
        message = translations['ride_cancelled_no_drivers'][language] if 'no_drivers' in ride.cancellation_reason else translations['ride_cancelled'][language]

        bot.send_message(
            chat_id=passenger.user.telegram_id,
            text=message
        )

        return True

    except Exception as e:
        logger.error(f"Error notifying passenger about cancelled ride {ride_id}: {str(e)}")
        return False


@shared_task
def notify_driver_document_approved(driver_telegram_id, document_type):
    """Notify driver that their document was approved"""
    try:
        from .utils import send_driver_notification
        return send_driver_notification(driver_telegram_id, 'document_approved', {
            'document_type': document_type
        })
    except Exception as e:
        logger.error(f"Error notifying driver {driver_telegram_id} about document approval: {str(e)}")
        return False


@shared_task
def notify_driver_document_rejected(driver_telegram_id, document_type):
    """Notify driver that their document was rejected"""
    try:
        from .utils import send_driver_notification
        return send_driver_notification(driver_telegram_id, 'document_rejected', {
            'document_type': document_type
        })
    except Exception as e:
        logger.error(f"Error notifying driver {driver_telegram_id} about document rejection: {str(e)}")
        return False


@shared_task
def notify_driver_verified(driver_telegram_id):
    """Notify driver that they are fully verified and can start receiving orders"""
    try:
        from .utils import send_driver_notification
        return send_driver_notification(driver_telegram_id, 'driver_verified', {})
    except Exception as e:
        logger.error(f"Error notifying driver {driver_telegram_id} about verification: {str(e)}")
        return False


@shared_task
def notify_drivers_about_boosted_ride(ride_id):
    """Notify drivers about a ride with boosted fare"""
    try:
        from api.models import Ride
        from api.services import PassengerService

        # Get the ride
        ride = Ride.objects.get(id=ride_id, status='requested')

        # Find available drivers (same as regular ride notification)
        available_drivers = PassengerService.get_nearby_rides_for_new_ride(ride)

        if not available_drivers:
            logger.warning(f"No drivers found for boosted ride {ride_id}")
            return False

        # Send boosted fare notifications to each driver
        notifications_sent = 0
        for driver_data in available_drivers:
            driver = driver_data['driver']
            distance = driver_data['distance_km']

            success = send_boosted_ride_notification(
                driver.user.telegram_id,
                ride,
                distance
            )

            if success:
                notifications_sent += 1

        logger.info(f"Sent {notifications_sent} boosted fare notifications for ride {ride_id}")
        return notifications_sent > 0

    except Exception as e:
        logger.error(f"Error notifying drivers about boosted ride {ride_id}: {str(e)}")
        return False


def send_boosted_ride_notification(driver_telegram_id, ride, distance_km):
    """Send Telegram notification to driver about boosted fare ride"""
    try:
        from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
        from bot_service.driver.dictionary import translations
        from api.models import User

        # Get bot token
        bot_token = os.getenv('TG_BOT_TOKEN_DRIVER')
        if not bot_token:
            logger.error("Driver bot token not found")
            return False

        bot = Bot(token=bot_token)

        # Get driver language
        try:
            driver_user = User.objects.get(telegram_id=str(driver_telegram_id))
            language = driver_user.language
        except:
            language = 'kaz'

        # Create boosted ride notification message
        pickup_address = ride.pickup_address[:50] + "..." if len(ride.pickup_address) > 50 else ride.pickup_address
        destination_address = ride.destination_address[:50] + "..." if len(ride.destination_address) > 50 else ride.destination_address

        message = translations['boosted_ride_request'][language].format(
            pickup=pickup_address,
            destination=destination_address,
            cost=int(ride.display_cost),
            boosts=ride.fare_boosts,
            distance=round(distance_km, 1) if distance_km > 0 else "N/A"
        )

        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    translations['buttons']['accept'][language],
                    callback_data=f"accept_ride_{ride.id}"
                ),
                InlineKeyboardButton(
                    translations['buttons']['reject'][language],
                    callback_data=f"reject_ride_{ride.id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send notification and get message object
        sent_message = bot.send_message(
            chat_id=driver_telegram_id,
            text=message,
            reply_markup=reply_markup
        )

        # Schedule auto-reject task with message ID for deletion (60 seconds)
        auto_reject_ride.apply_async(
            args=[ride.id, driver_telegram_id, sent_message.message_id],
            countdown=60
        )

        return True

    except Exception as e:
        logger.error(f"Error sending boosted ride notification to driver {driver_telegram_id}: {str(e)}")
        return False


@shared_task
def handle_no_drivers_available(ride_id):
    """Handle case when no online drivers are available for a ride"""
    try:
        from api.models import Ride, Driver
        from api.services import PassengerService
        from .utils import send_passenger_notification
        
        ride = Ride.objects.get(id=ride_id, status='requested')
        
        # 1. Notify passenger that no drivers are currently available
        send_passenger_notification(
            ride.passenger.user.telegram_id, 
            'no_drivers_available', 
            {}
        )
        
        # 2. Find nearby offline drivers and notify them
        pickup_location = (float(ride.pickup_lat), float(ride.pickup_lng))
        
        # Get all verified drivers (both online and offline) within radius
        from geopy.distance import geodesic
        radius_km = 10  # Increased radius for offline drivers
        
        offline_drivers = []
        for driver in Driver.objects.filter(is_verified=True, is_online=False):
            if driver.current_lat and driver.current_lng:
                driver_location = (float(driver.current_lat), float(driver.current_lng))
                distance = geodesic(driver_location, pickup_location).kilometers
                
                if distance <= radius_km:
                    offline_drivers.append(driver)
        
        # Send notifications to offline drivers
        notifications_sent = 0
        for driver in offline_drivers:
            success = send_offline_driver_notification(
                driver.user.telegram_id,
                ride
            )
            if success:
                notifications_sent += 1
        
        logger.info(f"Notified passenger about no drivers and sent {notifications_sent} notifications to offline drivers for ride {ride_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error handling no drivers available for ride {ride_id}: {str(e)}")
        return False


def send_offline_driver_notification(driver_telegram_id, ride):
    """Send notification to offline driver about waiting passenger"""
    try:
        from telegram import Bot
        from bot_service.driver.dictionary import translations
        from api.models import User
        
        # Get bot token
        bot_token = os.getenv('TG_BOT_TOKEN_DRIVER')
        if not bot_token:
            logger.error("Driver bot token not found")
            return False

        bot = Bot(token=bot_token)

        # Get driver language
        try:
            driver_user = User.objects.get(telegram_id=str(driver_telegram_id))
            language = driver_user.language
        except:
            language = 'kaz'

        # Create notification message
        pickup_address = ride.pickup_address[:50] + "..." if len(ride.pickup_address) > 50 else ride.pickup_address
        destination_address = ride.destination_address[:50] + "..." if len(ride.destination_address) > 50 else ride.destination_address

        message = translations['passenger_waiting_offline_driver'][language].format(
            pickup=pickup_address,
            destination=destination_address,
            cost=int(ride.estimated_cost)
        )

        # Send notification
        bot.send_message(
            chat_id=driver_telegram_id,
            text=message
        )

        return True

    except Exception as e:
        logger.error(f"Error sending offline driver notification to {driver_telegram_id}: {str(e)}")
        return False
