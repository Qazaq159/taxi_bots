"""
Passenger Main Menu Handlers
Handles main menu navigation and actions
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
import sys
import os

from bot_service.passenger.dictionary import translations
from bot_service.passenger.handler.ride import start_ride_order, show_ride_history
from bot_service.passenger.menu import main_menu
from bot_service.passenger.states import MAIN_MENU

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.services import PassengerService
import logging

logger = logging.getLogger(__name__)


def handle_main_menu(update: Update, context: CallbackContext) -> int:
    """Handle main menu button presses"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text

    # Check if user is registered
    passenger, _ = PassengerService.get_or_create_passenger(telegram_id)
    if not passenger or not passenger.user.is_phone_verified:
        update.message.reply_text(translations['please_register_first'][language])
        return ConversationHandler.END

    if user_input == translations['buttons']['new_order'][language]:
        # Start new ride order
        return start_ride_order(update, context)

    elif user_input == translations['buttons']['history'][language]:
        # Show ride history
        show_ride_history(update, context)
        return MAIN_MENU

    elif user_input == translations['buttons']['settings'][language]:
        # Show settings menu
        show_settings_menu(update, context)
        return MAIN_MENU

    elif user_input == translations['buttons']['support'][language]:
        # Show support information
        show_support_info(update, context)
        return MAIN_MENU
    else:
        # Unknown input, show main menu again
        update.message.reply_text(translations['unknown_command'][language])
        main_menu(update, context)
        return MAIN_MENU


def show_settings_menu(update: Update, context: CallbackContext) -> None:
    """Show settings menu"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        passenger, _ = PassengerService.get_or_create_passenger(telegram_id)
        user = passenger.user

        settings_text = translations['settings_menu'][language].format(
            name=user.full_name,
            phone=user.phone_number,
            language=dict(user.LANGUAGE_CHOICES).get(user.language, user.language),
            total_rides=passenger.total_rides,
            balance=passenger.balance
        )

        keyboard = [
            [KeyboardButton(translations['buttons']['change_language'][language])],
            [KeyboardButton(translations['buttons']['change_phone'][language])],
            [KeyboardButton(translations['buttons']['back_to_menu'][language])]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        update.message.reply_text(settings_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error showing settings for {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def show_support_info(update: Update, context: CallbackContext) -> None:
    """Show support information"""
    language = context.user_data.get('language', 'kaz')

    support_text = translations['support_info'][language]

    keyboard = [
        [KeyboardButton(translations['buttons']['back_to_menu'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(support_text, reply_markup=reply_markup)


def handle_back_to_menu(update: Update, context: CallbackContext) -> int:
    """Handle back to main menu"""
    main_menu(update, context)
    return MAIN_MENU
