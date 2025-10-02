"""
Passenger Main Menu Handlers
Handles main menu button interactions for passengers
"""
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import CallbackContext

from api.services import PassengerService
from bot_service.passenger.dictionary import translations
from bot_service.passenger.menu import main_menu, location_request_menu, confirmation_menu
from bot_service.passenger.states import (MAIN_MENU, PICKUP_ADDRESS, LOCATION_UPDATE,
    DESTINATION_ADDRESS, CONFIRM_RIDE)


def handle_main_menu(update: Update, context: CallbackContext) -> int:
    """Handle main menu button clicks"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text.strip()

    # Handle different button clicks
    if user_input == translations['buttons']['new_order'][language]:
        return handle_new_order(update, context)
    elif user_input == translations['buttons']['history'][language]:
        return handle_history(update, context)
    elif user_input == translations['buttons']['settings'][language]:
        return handle_settings(update, context)
    elif user_input == translations['buttons']['support'][language]:
        return handle_support(update, context)
    else:
        # Unknown command
        update.message.reply_text(
            translations['unknown_command'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        main_menu(update, context)
        return MAIN_MENU


def handle_new_order(update: Update, context: CallbackContext) -> int:
    """Handle new order button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    print(f"[PASSENGER_LOG] {telegram_id} starting new order")

    update.message.reply_text(
        translations['enter_pickup_address'][language],
        reply_markup=ReplyKeyboardRemove()
    )

    print(f"[PASSENGER_LOG] {telegram_id} returning PICKUP_ADDRESS state")
    return PICKUP_ADDRESS


def handle_history(update: Update, context: CallbackContext) -> int:
    """Handle history button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get passenger rides
    rides = PassengerService.get_passenger_rides(telegram_id, limit=10)

    if rides:
        history_message = f"📋 {translations['ride_history'][language]}\n\n"
        for i, ride in enumerate(rides, 1):
            status_text = {
                'requested': '📝 Запрошено' if language == 'rus' else '📝 Сұралған',
                'assigned': '👨‍🚗 Водитель назначен' if language == 'rus' else '👨‍🚗 Жүргізуші тағайындалды',
                'completed': '✅ Завершено' if language == 'rus' else '✅ Аяқталды',
                'cancelled': '❌ Отменено' if language == 'rus' else '❌ Болдырылды'
            }.get(ride.status, ride.status)

            history_message += f"{i}. {ride.created_at.strftime('%d.%m.%Y %H:%M')} - {status_text}\n"

        update.message.reply_text(history_message, reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text(
            translations['no_rides'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_settings(update: Update, context: CallbackContext) -> int:
    """Handle settings button"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Get passenger info
    passenger = PassengerService.get_passenger_by_telegram_id(telegram_id)
    user = PassengerService.get_user_by_telegram_id(telegram_id)

    if passenger and user:
        settings_message = translations['passenger_settings'][language].format(
            name=user.full_name,
            phone=user.phone_number or 'Не указан',
            language=language.upper(),
            total_rides=passenger.total_rides,
            balance=passenger.balance,
            registration_date=passenger.created_at.strftime('%d.%m.%Y')
        )

        update.message.reply_text(settings_message, reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text(
            translations['settings_error'][language],
            reply_markup=ReplyKeyboardRemove()
        )

    main_menu(update, context)
    return MAIN_MENU


def handle_support(update: Update, context: CallbackContext) -> int:
    """Handle support button"""
    language = context.user_data.get('language', 'kaz')

    support_message = translations['support_info'][language]

    update.message.reply_text(support_message, reply_markup=ReplyKeyboardRemove())

    main_menu(update, context)
    return MAIN_MENU


def handle_pickup_address(update: Update, context: CallbackContext) -> int:
    """Handle pickup address input"""
    language = context.user_data.get('language', 'kaz')
    pickup_address = update.message.text.strip()

    if len(pickup_address) < 5:
        update.message.reply_text(
            translations['invalid_address'][language],
            reply_markup=ReplyKeyboardRemove()
        )
        return PICKUP_ADDRESS

    # Store pickup address
    context.user_data['pickup_address'] = pickup_address

    # Ask for location confirmation
    update.message.reply_text(
        translations['confirm_pickup_location'][language],
        reply_markup=location_request_menu(update, context)
    )

    return LOCATION_UPDATE


def handle_location_update(update: Update, context: CallbackContext) -> int:
    """Handle location update from user"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    if not update.message.location:
        # User didn't send location, show error and ask again
        update.message.reply_text(
            translations['location_update_failed'][language],
            reply_markup=location_request_menu(update, context)
        )
        return LOCATION_UPDATE

    # Get location coordinates
    lat = update.message.location.latitude
    lng = update.message.location.longitude

    # Store location
    context.user_data['pickup_lat'] = lat
    context.user_data['pickup_lng'] = lng

    # Ask for destination address
    update.message.reply_text(
        translations['enter_destination'][language],
        reply_markup=ReplyKeyboardRemove()
    )

    return DESTINATION_ADDRESS


