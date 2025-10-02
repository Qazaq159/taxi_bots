"""
Driver Main Menu Handlers
Handles main menu navigation and actions
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
import sys
import os

from bot_service.driver.dictionary import translations
from bot_service.driver.handler.ride_management import toggle_online_status, show_driver_statistics, show_ride_history
from bot_service.driver.menu import main_menu
from bot_service.driver.states import MAIN_MENU, LOCATION_UPDATE

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.services import DriverService, UserService
import logging

logger = logging.getLogger(__name__)


def handle_main_menu(update: Update, context: CallbackContext) -> int:
    """Handle main menu button presses"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text

    # Check if driver is verified
    driver, _ = DriverService.get_or_create_driver(telegram_id)
    if not driver or not driver.is_verified:
        update.message.reply_text(translations['not_verified'][language])
        return ConversationHandler.END

    if user_input == translations['buttons']['go_online'][language]:
        # Go online
        return toggle_online_status(update, context)

    elif user_input == translations['buttons']['go_offline'][language]:
        # Go offline
        return toggle_online_status(update, context)

    elif user_input == translations['buttons']['statistics'][language]:
        # Show statistics
        show_driver_statistics(update, context)
        return MAIN_MENU

    elif user_input == translations['buttons']['history'][language]:
        # Show ride history
        show_ride_history(update, context)
        return MAIN_MENU

    elif user_input == translations['buttons']['settings'][language]:
        # Show settings menu
        show_settings_menu(update, context)
        return MAIN_MENU

    elif user_input == translations['buttons']['update_location'][language]:
        # Update location
        keyboard = [[KeyboardButton(
            translations['buttons']['send_location'][language],
            request_location=True
        )]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        update.message.reply_text(
            translations['share_location'][language],
            reply_markup=reply_markup
        )
        return LOCATION_UPDATE
    else:
        # Unknown input, show main menu again
        print(f"Unknown command from driver {telegram_id}: {user_input}")
        update.message.reply_text(translations['unknown_command'][language])
        main_menu(update, context)
        return MAIN_MENU


def show_settings_menu(update: Update, context: CallbackContext) -> None:
    """Show settings menu"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        driver, _ = DriverService.get_or_create_driver(telegram_id)
        user = driver.user
        vehicle = driver.vehicle if hasattr(driver, 'vehicle') else None

        settings_text = translations['driver_settings_menu'][language].format(
            name=user.full_name,
            phone=user.phone_number,
            language=dict(user._meta.get_field('language').choices).get(user.language, user.language),
            status=dict(driver._meta.get_field('status').choices).get(driver.status, driver.status),
            total_rides=driver.total_rides,
            rating=driver.average_rating,
            balance=driver.balance,
            vehicle_info=f"{vehicle.make} {vehicle.model} ({vehicle.license_plate})" if vehicle else "Не указано"
        )

        keyboard = [
            [KeyboardButton(translations['buttons']['change_language'][language])],
            [KeyboardButton(translations['buttons']['update_vehicle'][language])],
            [KeyboardButton(translations['buttons']['back_to_menu'][language])]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        update.message.reply_text(settings_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error showing settings for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def show_support_info(update: Update, context: CallbackContext) -> None:
    """Show support information"""
    language = context.user_data.get('language', 'kaz')

    support_text = translations['driver_support_info'][language]

    keyboard = [
        [KeyboardButton(translations['buttons']['back_to_menu'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(support_text, reply_markup=reply_markup)


def handle_back_to_menu(update: Update, context: CallbackContext) -> int:
    """Handle back to main menu"""
    main_menu(update, context)
    return MAIN_MENU


def show_driver_profile(update: Update, context: CallbackContext) -> None:
    """Show driver profile information"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        driver, _ = DriverService.get_or_create_driver(telegram_id)
        user = driver.user
        vehicle = driver.vehicle if hasattr(driver, 'vehicle') else None

        profile_text = translations['driver_profile'][language].format(
            name=user.full_name,
            phone=user.phone_number,
            status=dict(driver._meta.get_field('status').choices).get(driver.status, driver.status),
            online_status="В сети" if driver.is_online else "Не в сети",
            total_rides=driver.total_rides,
            rating=driver.average_rating,
            balance=driver.balance,
            vehicle_make=vehicle.make if vehicle else "Не указано",
            vehicle_model=vehicle.model if vehicle else "",
            vehicle_year=vehicle.year if vehicle else "",
            vehicle_color=vehicle.color if vehicle else "",
            license_plate=vehicle.license_plate if vehicle else "Не указано",
            registration_date=driver.created_at.strftime('%d.%m.%Y')
        )

        update.message.reply_text(profile_text)

    except Exception as e:
        logger.error(f"Error showing profile for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def handle_verification_status_check(update: Update, context: CallbackContext) -> None:
    """Check and display verification status"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        driver, _ = DriverService.get_or_create_driver(telegram_id)

        if driver.status == 'verified':
            status_text = translations['verification_approved'][language]
        elif driver.status == 'pending':
            status_text = translations['verification_pending'][language]
        elif driver.status == 'rejected':
            # Get rejection reasons from documents
            rejection_reasons = []
            for doc in driver.documents.filter(status='rejected'):
                if doc.rejection_reason:
                    rejection_reasons.append(f"• {doc.get_document_type_display()}: {doc.rejection_reason}")

            reasons_text = "\n".join(rejection_reasons) if rejection_reasons else translations['no_rejection_reason'][language]
            status_text = translations['verification_rejected'][language].format(reason=reasons_text)
        else:
            status_text = translations['verification_unknown'][language]

        update.message.reply_text(status_text)

    except Exception as e:
        logger.error(f"Error checking verification status for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def show_earnings_details(update: Update, context: CallbackContext) -> None:
    """Show detailed earnings breakdown"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        stats = DriverService.get_driver_earnings(telegram_id)

        if stats:
            # Get additional statistics
            from api.models import Driver
            from django.utils import timezone
            from datetime import timedelta

            user, _ = UserService.get_or_create_user(telegram_id)
            driver = user.driver_profile

            # Calculate weekly and monthly stats
            today = timezone.now().date()
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)

            completed_rides = driver.rides.filter(status='completed')
            week_rides = completed_rides.filter(completed_at__date__gte=week_ago)
            month_rides = completed_rides.filter(completed_at__date__gte=month_ago)

            week_earnings = sum(ride.final_cost or 0 for ride in week_rides)
            month_earnings = sum(ride.final_cost or 0 for ride in month_rides)

            earnings_text = translations['detailed_earnings'][language].format(
                balance=stats['balance'],
                total_rides=stats['total_rides'],
                total_earnings=stats['total_earnings'],
                today_rides=stats.get('today_rides_count', 0),
                today_earnings=stats['today_earnings'],
                week_rides=week_rides.count(),
                week_earnings=week_earnings,
                month_rides=month_rides.count(),
                month_earnings=month_earnings,
                average_rating=stats['average_rating'],
                avg_ride_cost=stats['total_earnings'] / max(stats['total_rides'], 1)
            )
        else:
            earnings_text = translations['no_earnings_data'][language]

        update.message.reply_text(earnings_text)

    except Exception as e:
        logger.error(f"Error showing earnings details for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def handle_language_change(update: Update, context: CallbackContext) -> int:
    """Handle language change request"""
    language = context.user_data.get('language', 'kaz')

    # Show language selection
    keyboard = [
        [KeyboardButton('🇰🇿 Қазақша')],
        [KeyboardButton('🇷🇺 Русский')]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(translations['select_language'][language], reply_markup=reply_markup)

    return MAIN_MENU


def handle_language_selection(update: Update, context: CallbackContext) -> int:
    """Handle new language selection"""
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text

    if user_input == '🇰🇿 Қазақша':
        new_language = 'kaz'
    elif user_input == '🇷🇺 Русский':
        new_language = 'rus'
    else:
        # Invalid selection, stay in current language
        language = context.user_data.get('language', 'kaz')
        update.message.reply_text(translations['invalid_language_selection'][language])
        main_menu(update, context)
        return MAIN_MENU

    # Update language
    context.user_data['language'] = new_language
    UserService.update_user_language(telegram_id, new_language)

    update.message.reply_text(
        translations['language_changed'][new_language],
        reply_markup=ReplyKeyboardRemove()
    )

    main_menu(update, context)
    return MAIN_MENU
