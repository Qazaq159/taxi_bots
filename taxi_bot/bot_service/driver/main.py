import os
import logging

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackQueryHandler

from bot_service.driver.dictionary import translations
from bot_service.driver.handler.command import cancel, help_bot, start
from bot_service.driver.handler.language import language_handler
from bot_service.driver.handler.menu import handle_language_selection
from bot_service.driver.handler.registration import (
    start_phone_verification, handle_full_name, handle_contact, handle_text_phone,
    handle_vehicle_info, handle_document_upload, handle_verification_pending
)
from bot_service.driver.handler.menu_handler import (
    handle_main_menu, handle_go_online, handle_go_offline, handle_statistics,
    handle_history, handle_update_location, handle_location_update, handle_settings,
    handle_active_rides
)
from bot_service.driver.handler.ride_management import handle_ride_response, handle_ride_management
from bot_service.driver.states import *


load_dotenv()

# Get logger configured from Django settings
logger = logging.getLogger('taxi_bot.bot_service.driver')

updater = Updater(os.getenv('TG_BOT_TOKEN_DRIVER'), use_context=True)


def main() -> None:
    logger.info("Initializing driver bot...")
    dispatcher = updater.dispatcher

    # Add command handlers first
    dispatcher.add_handler(CommandHandler("help", help_bot))
    dispatcher.add_handler(CommandHandler("cancel", cancel))

    # Add callback query handler for inline buttons
    from bot_service.driver.handler.ride_management import handle_ride_response
    # Handle ride response callbacks (accept, reject, cancel)
    dispatcher.add_handler(CallbackQueryHandler(handle_ride_response, pattern=r'^(accept|reject|cancel)_ride_.*$'))

    # Add conversation handler last
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [
                MessageHandler(Filters.text & ~Filters.command, language_handler),
                MessageHandler(Filters.regex('^(🇰🇿|🇷🇺)'), handle_language_selection)
            ],
            REGISTRATION: [
                MessageHandler(Filters.text & ~Filters.command, handle_full_name)
            ],
            PHONE_VERIFICATION: [
                MessageHandler(Filters.contact, handle_contact),
                MessageHandler(Filters.text & ~Filters.command, handle_text_phone)
            ],
            VEHICLE_INFO: [
                MessageHandler(Filters.text & ~Filters.command, handle_vehicle_info)
            ],
            DOCUMENT_UPLOAD: [
                MessageHandler(Filters.photo, handle_document_upload)
            ],
            VERIFICATION_PENDING: [
                MessageHandler(Filters.text & ~Filters.command, handle_verification_pending)
            ],
            MAIN_MENU: [
                MessageHandler(Filters.text & ~Filters.command, handle_main_menu)
            ],
            LOCATION_UPDATE: [
                MessageHandler(Filters.location, handle_location_update),
                MessageHandler(Filters.text & ~Filters.command, handle_location_update)
            ],
            RIDE_MANAGEMENT: [
                MessageHandler(Filters.text & ~Filters.command, handle_ride_management)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    commands = [
        BotCommand("start", "/start"),
        BotCommand("help", "/help"),
        BotCommand("cancel", "/cancel")
    ]
    updater.bot.set_my_commands(commands)

    dispatcher.add_handler(conv_handler)
    logger.info("Driver bot started successfully and is now polling for messages...")
    updater.start_polling()


def notify_driver_about_ride(driver_telegram_id, ride, distance_km):
    """Send notification to driver about new ride request"""
    try:
        # Get bot instance and user language
        from bot_service.driver.dictionary import translations

        # Find the driver's language preference
        driver_user = None
        try:
            from api.models import User
            driver_user = User.objects.get(telegram_id=str(driver_telegram_id))
        except:
            pass

        language = driver_user.language if driver_user else 'kaz'

        # Create ride notification message
        pickup_address = ride.pickup_address[:50] + "..." if len(ride.pickup_address) > 50 else ride.pickup_address
        destination_address = ride.destination_address[:50] + "..." if len(ride.destination_address) > 50 else ride.destination_address

        message = translations['new_ride_request'][language].format(
            pickup=pickup_address,
            destination=destination_address,
            cost=int(ride.estimated_cost),
            distance=round(distance_km, 1)
        )

        # Create inline keyboard for accept/reject
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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
        sent_message = updater.bot.send_message(
            chat_id=driver_telegram_id,
            text=message,
            reply_markup=reply_markup
        )

        # Set auto-reject timer (60 seconds)
        updater.job_queue.run_once(
            auto_reject_ride,
            60,
            context={
                'chat_id': driver_telegram_id,
                'ride_id': str(ride.id),
                'telegram_id': str(driver_telegram_id),
                'language': language,
                'message_id': sent_message.message_id
            }
        )

        logger.info(f"Sent ride notification to driver {driver_telegram_id} for ride {ride.id}")

    except Exception as e:
        logger.error(f"Error sending notification to driver {driver_telegram_id}: {str(e)}")


def auto_reject_ride(context):
    """Auto-reject ride after timeout - delete original message and reassign to another driver"""
    job_context = context.job.context
    chat_id = job_context['chat_id']
    ride_id = job_context['ride_id']
    language = job_context['language']
    message_id = job_context.get('message_id')

    try:
        # Delete original message if message_id is provided
        if message_id:
            try:
                updater.bot.delete_message(
                    chat_id=chat_id,
                    message_id=message_id
                )
                logger.info(f"Deleted original ride notification message {message_id} for driver {chat_id}")
            except Exception as e:
                logger.warning(f"Could not delete original message {message_id}: {str(e)}")

        # Send timeout message
        updater.bot.send_message(
            chat_id=chat_id,
            text=translations['ride_timeout'][language]
        )

        # Reassign ride to another driver
        try:
            reassign_ride_to_next_driver(ride_id, chat_id)
        except Exception as e:
            logger.error(f"Error reassigning ride {ride_id}: {str(e)}")

        logger.info(f"Auto-rejected ride {ride_id} for driver {chat_id}, reassigned to another driver")

    except Exception as e:
        logger.error(f"Error sending timeout message to {chat_id}: {str(e)}")


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
            logger.warning(f"No other drivers available for ride {ride_id}")
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
            return False

        driver = next_driver['driver']
        distance = next_driver['distance_km']

        logger.info(f"Reassigning ride {ride_id} to driver {driver.user.telegram_id} (excluding {exclude_driver_telegram_id})")

        # Send notification to the next driver
        notify_driver_about_ride(driver.user.telegram_id, ride, distance)

        logger.info(f"Successfully reassigned ride {ride_id} to driver {driver.user.telegram_id}")
        return True

    except Exception as e:
        logger.error(f"Error reassigning ride {ride_id}: {str(e)}")
        return False


if __name__ == '__main__':
    main()
