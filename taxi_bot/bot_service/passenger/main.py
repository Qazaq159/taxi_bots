import os

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackQueryHandler, CallbackContext

from bot_service.passenger.handler.commands import cancel, help_bot, start
from bot_service.passenger.handler.language import language_handler
from bot_service.passenger.handler.registration import (
    start_phone_verification, handle_full_name, handle_contact, handle_text_phone
)
from bot_service.passenger.handler.menu_handler import (
    handle_main_menu, handle_pickup_address, handle_location_update
)
from bot_service.passenger.handler.ride import handle_destination_location, handle_ride_confirmation, handle_waiting_driver

from bot_service.passenger.states import *


load_dotenv()

updater = Updater(os.getenv('TG_BOT_TOKEN_PASSENGER'), use_context=True)


def main() -> None:
    dispatcher = updater.dispatcher

    # Add command handlers first
    dispatcher.add_handler(CommandHandler("help", help_bot))
    # Note: cancel handler is handled by conversation handler fallbacks

    # Add logging for all messages
    def log_all_messages(update: Update, context: CallbackContext):
        if update.message:
            telegram_id = str(update.effective_user.id) if update.effective_user else "unknown"
            message_text = update.message.text or "non-text message"
            print(f"[PASSENGER_LOG] {telegram_id} received message: '{message_text}'")

    dispatcher.add_handler(MessageHandler(Filters.all, log_all_messages), group=-1)

    # Add callback query handler for rating buttons
    from telegram.ext import CallbackQueryHandler
    from bot_service.passenger.handler.ride import handle_rating
    dispatcher.add_handler(CallbackQueryHandler(handle_rating, pattern=r'^rate_driver_\d+_.*$'))

    # Add conversation handler last
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [
                MessageHandler(Filters.text & ~Filters.command, language_handler)
            ],
            REGISTRATION: [
                MessageHandler(Filters.text & ~Filters.command, handle_full_name)
            ],
            PHONE_VERIFICATION: [
                MessageHandler(Filters.contact, handle_contact),
                MessageHandler(Filters.text & ~Filters.command, handle_text_phone)
            ],
            MAIN_MENU: [
                MessageHandler(Filters.text & ~Filters.command, handle_main_menu)
            ],
            PICKUP_ADDRESS: [
                MessageHandler(Filters.text & ~Filters.command, handle_pickup_address)
            ],
            LOCATION_UPDATE: [
                MessageHandler(Filters.location, handle_location_update),
                MessageHandler(Filters.text & ~Filters.command, handle_location_update)
            ],
            DESTINATION_ADDRESS: [
                MessageHandler(Filters.location, handle_destination_location),
                MessageHandler(Filters.text & ~Filters.command, handle_destination_location)
            ],
            CONFIRM_RIDE: [
                MessageHandler(Filters.text & ~Filters.command, handle_ride_confirmation)
            ],
            WAITING_DRIVER: [
                MessageHandler(Filters.text & ~Filters.command, handle_waiting_driver)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start)  # Allow /start from any state to restart
        ]
    )

    commands = [
        BotCommand("start", "/start"),
        BotCommand("help", "/help"),
        BotCommand("cancel", "/cancel")
    ]
    updater.bot.set_my_commands(commands)

    dispatcher.add_handler(conv_handler)
    updater.start_polling()


def notify_passenger_driver_assigned(passenger_telegram_id, driver):
    """Send notification to passenger when driver is assigned"""
    try:
        # Get bot instance and passenger language
        from bot_service.passenger.dictionary import translations
        from telegram import ReplyKeyboardMarkup, KeyboardButton

        # Find the passenger's language preference
        passenger_user = None
        try:
            from api.models import User
            passenger_user = User.objects.get(telegram_id=str(passenger_telegram_id))
        except:
            pass

        language = passenger_user.language if passenger_user else 'kaz'

        # Create driver assignment message
        message = translations['driver_assigned'][language].format(
            driver_name=driver.user.full_name,
            rating=driver.average_rating,
            car=f"{driver.vehicle.make} {driver.vehicle.model}" if driver.vehicle else "N/A",
            phone=driver.user.phone_number
        )

        # Send notification
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=message
        )

        # Update buttons - remove "increase cost" and show only "cancel" and "SOS"
        keyboard = [
            [KeyboardButton(translations['buttons']['cancel_ride'][language])],
            [KeyboardButton(translations['buttons']['sos'][language])]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Send button update message
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=translations['driver_enroute'][language],
            reply_markup=reply_markup
        )

        print(f"Sent driver assignment notification to passenger {passenger_telegram_id}")

    except Exception as e:
        print(f"Error sending driver assignment notification to passenger {passenger_telegram_id}: {str(e)}")


def notify_passenger(passenger_telegram_id, message):
    """Send general notification to passenger"""
    try:
        # Send notification
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=message
        )

        print(f"Sent notification to passenger {passenger_telegram_id}: {message[:50]}...")

    except Exception as e:
        print(f"Error sending notification to passenger {passenger_telegram_id}: {str(e)}")


def notify_passenger_ride_started(passenger_telegram_id, driver_name, driver_phone, destination):
    """Send notification to passenger when driver starts the ride and update buttons to SOS only"""
    try:
        # Get bot instance and passenger language
        from bot_service.passenger.dictionary import translations
        from telegram import ReplyKeyboardMarkup, KeyboardButton

        # Find the passenger's language preference
        passenger_user = None
        try:
            from api.models import User
            passenger_user = User.objects.get(telegram_id=str(passenger_telegram_id))
        except:
            pass

        language = passenger_user.language if passenger_user else 'kaz'

        # Create ride started message
        message = translations['ride_started_passenger'][language].format(
            driver_name=driver_name,
            phone=driver_phone,
            destination=destination
        )

        # Create SOS button only
        keyboard = [
            [KeyboardButton(translations['buttons']['sos'][language])]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Send notification with SOS button
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=message,
            reply_markup=reply_markup
        )

        print(f"Sent ride started notification to passenger {passenger_telegram_id}")

    except Exception as e:
        print(f"Error sending ride started notification to passenger {passenger_telegram_id}: {str(e)}")


def notify_passenger_with_rating(passenger_telegram_id, message, ride_id, language='kaz'):
    """Send ride completion notification with rating buttons to passenger"""
    try:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from bot_service.passenger.dictionary import translations

        # Send completion message first
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=message
        )

        # Create rating buttons
        keyboard = [
            [InlineKeyboardButton(translations['buttons']['rate_5'][language], callback_data=f'rate_driver_5_{ride_id}')],
            [InlineKeyboardButton(translations['buttons']['rate_4'][language], callback_data=f'rate_driver_4_{ride_id}')],
            [InlineKeyboardButton(translations['buttons']['rate_3'][language], callback_data=f'rate_driver_3_{ride_id}')],
            [InlineKeyboardButton(translations['buttons']['rate_2'][language], callback_data=f'rate_driver_2_{ride_id}')],
            [InlineKeyboardButton(translations['buttons']['rate_1'][language], callback_data=f'rate_driver_1_{ride_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send rating request with buttons
        updater.bot.send_message(
            chat_id=passenger_telegram_id,
            text=translations['rate_driver'][language],
            reply_markup=reply_markup
        )

        print(f"Sent rating notification to passenger {passenger_telegram_id} for ride {ride_id}")

    except Exception as e:
        print(f"Error sending rating notification to passenger {passenger_telegram_id}: {str(e)}")


if __name__ == '__main__':
    main()
