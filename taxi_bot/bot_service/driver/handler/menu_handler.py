"""
Main Menu Handlers
Handles main menu button interactions for drivers
"""
import logging

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

from api.services import DriverService
from api.models import Ride
from bot_service.driver.dictionary import translations
from bot_service.driver.menu import main_menu
from bot_service.driver.states import MAIN_MENU, LOCATION_UPDATE

# Get logger configured from Django settings
logger = logging.getLogger('taxi_bot.bot_service.driver.menu_handler')


def handle_main_menu(update: Update, context: CallbackContext) -> int:
    """Handle main menu button clicks"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text.strip()

    # Get driver info
    driver, _ = DriverService.get_or_create_driver(telegram_id)

    # Check if this is a ride management button (handle regardless of state)
    active_ride = context.user_data.get('active_ride')
    if active_ride:
        from bot_service.driver.handler.ride_management import handle_ride_management
        from bot_service.driver.states import RIDE_MANAGEMENT
        logging.info(f"Driver {telegram_id} has active ride, redirecting to ride management: {active_ride}")
        return handle_ride_management(update, context)

    # Handle different button clicks
    if user_input == translations['buttons']['go_online'][language]:
        return handle_go_online(update, context)
    elif user_input == translations['buttons']['go_offline'][language]:
        return handle_go_offline(update, context)
    elif user_input == translations['buttons']['statistics'][language]:
        return handle_statistics(update, context)
    elif user_input == translations['buttons']['history'][language]:
        return handle_history(update, context)
    elif user_input == translations['buttons']['update_location'][language]:
        return handle_update_location(update, context)
    elif user_input == translations['buttons']['active_rides'][language]:
        return handle_active_rides(update, context)
    elif user_input == translations['buttons']['settings'][language]:
        return handle_settings(update, context)
    else:
        logging.warning(f"Unknown command from driver {telegram_id}: '{user_input}' (language: {language})")
        # Unknown command
        update.message.reply_text(
            translations['unknown_command'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU


def handle_go_online(update: Update, context: CallbackContext) -> int:
    """Handle go online button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Update driver status to online
    driver = DriverService.update_driver_status(telegram_id, is_online=True)

    if driver:
        update.message.reply_text(
            translations['went_online'][language],
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        update.message.reply_text(
            translations['status_change_failed'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_go_offline(update: Update, context: CallbackContext) -> int:
    """Handle go offline button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Update driver status to offline
    driver = DriverService.update_driver_status(telegram_id, is_online=False)

    if driver:
        update.message.reply_text(
            translations['went_offline'][language],
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        update.message.reply_text(
            translations['status_change_failed'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_statistics(update: Update, context: CallbackContext) -> int:
    """Handle statistics button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get driver statistics
    driver = DriverService.get_driver_by_telegram_id(telegram_id)

    if driver:
        stats_message = f"""
📊 {translations['earnings_summary'][language].format(
    balance=driver.balance,
    total_rides=driver.total_rides,
    rating=driver.average_rating,
    today_earnings=0,  # TODO: Calculate today's earnings
    week_earnings=0,   # TODO: Calculate week's earnings
    month_earnings=0   # TODO: Calculate month's earnings
)}
        """.strip()

        update.message.reply_text(stats_message, reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text(
            translations['no_statistics'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_history(update: Update, context: CallbackContext) -> int:
    """Handle history button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get recent rides for this driver
    rides = DriverService.get_driver_rides(telegram_id, limit=10)

    if rides:
        history_message = f"📋 {translations['main_menu'][language]}\n\n"
        for i, ride in enumerate(rides, 1):
            history_message += f"{i}. {ride.created_at.strftime('%d.%m.%Y %H:%M')} - {ride.final_cost or ride.estimated_cost}₸\n"

        update.message.reply_text(history_message, reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text(
            translations['no_statistics'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_update_location(update: Update, context: CallbackContext) -> int:
    """Handle update location button - request location sharing"""
    language = context.user_data.get('language', 'kaz')

    # Request location sharing with a button
    keyboard = [[KeyboardButton(
        translations['buttons']['send_location'][language],
        request_location=True
    )]]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )

    update.message.reply_text(
        translations['please_share_location'][language],
        reply_markup=reply_markup
    )

    return LOCATION_UPDATE


def handle_location_update(update: Update, context: CallbackContext) -> int:
    """Handle location update from user"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    if not update.message.location:
        # User didn't send location, show error and return to main menu
        update.message.reply_text(
            translations['location_update_failed'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU

    # Get location coordinates
    lat = update.message.location.latitude
    lng = update.message.location.longitude

    # Update driver location
    success = DriverService.update_driver_location(telegram_id, lat, lng)

    if success:
        update.message.reply_text(
            translations['location_updated'][language],
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        update.message.reply_text(
            translations['location_update_failed'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_settings(update: Update, context: CallbackContext) -> int:
    """Handle settings button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get driver info for settings
    driver = DriverService.get_driver_by_telegram_id(telegram_id)
    user = DriverService.get_user_by_telegram_id(telegram_id)

    if driver and user:
        settings_message = translations['driver_settings_menu'][language].format(
            name=user.full_name,
            phone=user.phone_number or 'Не указан',
            language=language.upper(),
            status='В сети' if driver.is_online else 'Не в сети',
            total_rides=driver.total_rides,
            rating=driver.average_rating,
            balance=driver.balance,
            vehicle_info=f"{driver.vehicle.make} {driver.vehicle.model}" if driver.vehicle else 'Не указан'
        )

        update.message.reply_text(settings_message, reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text(
            translations['no_statistics'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_active_rides(update: Update, context: CallbackContext) -> int:
    """Handle active rides button - show current rides with management options"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get driver's active rides
    driver = DriverService.get_driver_by_telegram_id(telegram_id)
    if not driver:
        update.message.reply_text(
            translations['no_active_rides'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU

    # Get active rides for this driver
    active_rides = Ride.objects.filter(
        driver=driver,
        status__in=['assigned', 'driver_enroute', 'driver_arrived', 'in_progress']
    ).order_by('-created_at')

    if not active_rides:
        update.message.reply_text(
            translations['no_active_rides'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU

    # Show header
    update.message.reply_text(
        translations['active_rides_header'][language],
        reply_markup=ReplyKeyboardRemove()
    )

    # Show each active ride with cancel button
    for ride in active_rides:
        # Format ride status
        status_key = f'ride_status_{ride.status}'
        status_text = translations.get(status_key, {}).get(language, ride.status)

        # Format ride info
        ride_info = translations['ride_info_format'][language].format(
            id=ride.id,
            pickup=ride.pickup_address[:30] + "..." if len(ride.pickup_address) > 30 else ride.pickup_address,
            destination=ride.destination_address[:30] + "..." if len(ride.destination_address) > 30 else ride.destination_address,
            cost=int(ride.estimated_cost),
            status=status_text,
            time=ride.created_at.strftime('%H:%M')
        )

        # Create inline keyboard for ride management
        keyboard = []

        # Allow cancellation for active rides (assigned, en route, arrived, or in progress)
        if ride.status in ['assigned', 'driver_enroute', 'driver_arrived', 'in_progress']:
            keyboard.append([
                InlineKeyboardButton(
                    translations['buttons']['cancel_ride'][language],
                    callback_data=f"cancel_ride_{ride.id}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        update.message.reply_text(
            ride_info,
            reply_markup=reply_markup
        )

    main_menu(update, context)
    return MAIN_MENU
