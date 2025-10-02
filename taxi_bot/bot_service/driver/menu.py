from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CallbackContext

from .dictionary import translations


def language_menu(update: Update, context: CallbackContext):
    """Display language selection menu"""
    keyboard = [
        [KeyboardButton('🇰🇿 Қазақша')],
        [KeyboardButton('🇷🇺 Русский')]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text('🌍 Выберите язык / Тіл таңдаңыз:', reply_markup=reply_markup)


def main_menu(update: Update, context: CallbackContext):
    """Display main menu for drivers"""
    language = context.user_data.get('language', 'kaz')

    # Check driver status to show appropriate buttons
    from api.services import DriverService
    telegram_id = str(update.effective_user.id)
    driver, _ = DriverService.get_or_create_driver(telegram_id)

    if driver and driver.is_online:
        online_button = translations['buttons']['go_offline'][language]
    else:
        online_button = translations['buttons']['go_online'][language]

    keyboard = [
        [KeyboardButton(online_button)],
        [KeyboardButton(translations['buttons']['active_rides'][language])],
        [KeyboardButton(translations['buttons']['statistics'][language]),
         KeyboardButton(translations['buttons']['history'][language])],
        [KeyboardButton(translations['buttons']['update_location'][language])],
        [KeyboardButton(translations['buttons']['settings'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(translations['main_menu'][language], reply_markup=reply_markup)


def contact_request_menu(update: Update, context: CallbackContext):
    """Request user contact"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton(translations['buttons']['share_contact'][language], request_contact=True)]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return reply_markup


def location_request_menu(update: Update, context: CallbackContext):
    """Request user location"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton(translations['buttons']['send_location'][language], request_location=True)]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return reply_markup


def rating_menu(update: Update, context: CallbackContext):
    """Display rating selection menu"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [InlineKeyboardButton(translations['buttons']['rate_5'][language], callback_data='rate_5')],
        [InlineKeyboardButton(translations['buttons']['rate_4'][language], callback_data='rate_4')],
        [InlineKeyboardButton(translations['buttons']['rate_3'][language], callback_data='rate_3')],
        [InlineKeyboardButton(translations['buttons']['rate_2'][language], callback_data='rate_2')],
        [InlineKeyboardButton(translations['buttons']['rate_1'][language], callback_data='rate_1')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def document_type_menu(update: Update, context: CallbackContext):
    """Display document type selection menu"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton(translations['buttons']['license'][language])],
        [KeyboardButton(translations['buttons']['passport'][language])],
        [KeyboardButton(translations['buttons']['registration'][language])],
        [KeyboardButton(translations['buttons']['insurance'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return reply_markup


def ride_response_menu(update: Update, context: CallbackContext, ride_id: str):
    """Display ride acceptance/rejection buttons"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [
            InlineKeyboardButton(
                translations['buttons']['accept'][language],
                callback_data=f"accept_ride_{ride_id}"
            ),
            InlineKeyboardButton(
                translations['buttons']['reject'][language],
                callback_data=f"reject_ride_{ride_id}"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def ride_management_menu(update: Update, context: CallbackContext, ride_status: str):
    """Display ride management buttons based on current status"""
    language = context.user_data.get('language', 'kaz')

    if ride_status == 'assigned':
        keyboard = [
            [KeyboardButton(translations['buttons']['arrived'][language])],
            [KeyboardButton(translations['buttons']['cancel_ride'][language])]
        ]
    elif ride_status == 'driver_arrived':
        keyboard = [
            [KeyboardButton(translations['buttons']['start_ride'][language])],
            [KeyboardButton(translations['buttons']['cancel_ride'][language])]
        ]
    elif ride_status == 'in_progress':
        keyboard = [
            [KeyboardButton(translations['buttons']['complete_ride'][language])],
            [KeyboardButton(translations['buttons']['sos'][language])]
        ]
    else:
        keyboard = [
            [KeyboardButton(translations['buttons']['back_to_menu'][language])]
        ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    return reply_markup


def passenger_rating_menu(update: Update, context: CallbackContext, ride_id: str):
    """Display passenger rating buttons"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [InlineKeyboardButton(translations['buttons']['rate_5'][language], callback_data=f'rate_passenger_5_{ride_id}')],
        [InlineKeyboardButton(translations['buttons']['rate_4'][language], callback_data=f'rate_passenger_4_{ride_id}')],
        [InlineKeyboardButton(translations['buttons']['rate_3'][language], callback_data=f'rate_passenger_3_{ride_id}')],
        [InlineKeyboardButton(translations['buttons']['rate_2'][language], callback_data=f'rate_passenger_2_{ride_id}')],
        [InlineKeyboardButton(translations['buttons']['rate_1'][language], callback_data=f'rate_passenger_1_{ride_id}')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def remove_keyboard():
    """Remove custom keyboard"""
    return ReplyKeyboardRemove()
