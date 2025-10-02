"""
Passenger Registration Handlers
Handles user registration and phone verification
"""
import os
import sys

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CallbackContext

from bot_service.passenger.dictionary import translations
from bot_service.passenger.menu import main_menu, contact_request_menu
from bot_service.passenger.states import MAIN_MENU, PHONE_VERIFICATION
from bot_service.passenger.states import REGISTRATION

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.services import UserService, PassengerService
import logging

logger = logging.getLogger(__name__)


def start_phone_verification(update: Update, context: CallbackContext) -> int:
    """Start with phone verification after language selection - ALWAYS ask for phone number"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get or create user
    user, created = UserService.get_or_create_user(
        telegram_id=telegram_id,
        username=update.effective_user.username,
        full_name=f"{update.effective_user.first_name or ''} {update.effective_user.last_name or ''}".strip(),
        language=language
    )

    # Update language if changed
    if user.language != language:
        UserService.update_user_language(telegram_id, language)

    # ALWAYS ask for phone number first - don't check existing verification status
    keyboard = [[KeyboardButton(
        translations['buttons']['share_contact'][language],
        request_contact=True
    )]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )

    update.message.reply_text(
        translations['request_contact'][language],
        reply_markup=reply_markup
    )
    return PHONE_VERIFICATION


def start_registration(update: Update, context: CallbackContext) -> int:
    """Legacy function - kept for backward compatibility"""
    return start_phone_verification(update, context)


def handle_full_name(update: Update, context: CallbackContext) -> int:
    """Handle full name input"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    full_name = update.message.text.strip()

    if len(full_name) < 2:
        update.message.reply_text(translations['invalid_name'][language])
        return REGISTRATION

    # Update user's full name
    try:
        user, _ = UserService.get_or_create_user(telegram_id)
        user.full_name = full_name
        user.save()

        context.user_data['full_name'] = full_name

        # Create passenger profile and go to main menu
        passenger, created = PassengerService.get_or_create_passenger(telegram_id)
        
        update.message.reply_text(
            translations['registration_complete'][language].format(name=full_name),
            reply_markup=ReplyKeyboardRemove()
        )
        
        main_menu(update, context)
        return MAIN_MENU

    except Exception as e:
        logger.error(f"Error updating full name for {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])
        return REGISTRATION


def handle_contact(update: Update, context: CallbackContext) -> int:
    """Handle contact sharing for phone verification"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    if not update.message.contact:
        update.message.reply_text(
            translations['please_share_contact'][language],
            reply_markup=contact_request_menu(update, context)
        )
        return PHONE_VERIFICATION

    # Verify it's the user's own contact
    if str(update.message.contact.user_id) != telegram_id:
        update.message.reply_text(translations['share_own_contact'][language])
        return PHONE_VERIFICATION

    phone_number = update.message.contact.phone_number

    # Clean phone number first
    cleaned_phone = ''.join(filter(str.isdigit, phone_number))
    if not cleaned_phone.startswith('7') and cleaned_phone.startswith('8'):
        cleaned_phone = '7' + cleaned_phone[1:]
    if not cleaned_phone.startswith('+'):
        cleaned_phone = '+' + cleaned_phone

    # Check if user with this phone already exists BEFORE verifying current user
    existing_user = UserService.get_user_by_phone(cleaned_phone)

    if existing_user and existing_user.telegram_id != telegram_id:
        # Different user already has this phone number
        update.message.reply_text(translations['phone_already_registered'][language])
        return PHONE_VERIFICATION
    elif existing_user and existing_user.telegram_id == telegram_id and existing_user.is_phone_verified:
        # Current user already verified with this phone - go to main menu
        passenger, _ = PassengerService.get_or_create_passenger(telegram_id)
        update.message.reply_text(
            translations['already_registered'][language].format(name=existing_user.full_name),
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU
    else:
        # New phone number - verify it for current user
        success, cleaned_phone = UserService.verify_phone_number(telegram_id, phone_number)
        
        if success:
            # New user - ask for full name
            update.message.reply_text(
                translations['enter_full_name'][language],
                reply_markup=ReplyKeyboardRemove()
            )
            return REGISTRATION
        else:
            update.message.reply_text(translations['phone_verification_failed'][language])
            return PHONE_VERIFICATION


def handle_text_phone(update: Update, context: CallbackContext) -> int:
    """Handle phone number entered as text (fallback)"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    phone_text = update.message.text.strip()

    # Basic phone validation
    if not phone_text.startswith('+7') and not phone_text.startswith('8'):
        update.message.reply_text(translations['invalid_phone'][language])
        return PHONE_VERIFICATION

    # Try to verify
    success, cleaned_phone = UserService.verify_phone_number(telegram_id, phone_text)

    if success:
        # Check if user exists in database with this phone
        user = UserService.get_user_by_phone(cleaned_phone)

        if user and user.is_phone_verified:
            # User exists and is verified - check passenger status
            passenger, _ = PassengerService.get_or_create_passenger(telegram_id)

            # User exists and is verified - go to main menu
            update.message.reply_text(
                translations['already_registered'][language].format(name=user.full_name),
                reply_markup=ReplyKeyboardRemove()
            )
            main_menu(update, context)
            return MAIN_MENU
        else:
            # New user - ask for full name
            update.message.reply_text(
                translations['enter_full_name'][language],
                reply_markup=ReplyKeyboardRemove()
            )
            return REGISTRATION
    else:
        update.message.reply_text(translations['phone_verification_failed'][language])
        return PHONE_VERIFICATION
