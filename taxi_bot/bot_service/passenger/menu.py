from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import CallbackContext

from bot_service.passenger.dictionary import translations


def language_menu(update: Update, context: CallbackContext):
    """Display language selection menu"""
    keyboard = [
        [KeyboardButton('🇰🇿 Қазақша')],
        [KeyboardButton('🇷🇺 Русский')]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text('🌍 Выберите язык / Тіл таңдаңыз:', reply_markup=reply_markup)


def main_menu(update: Update, context: CallbackContext):
    """Display main menu"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton(translations['buttons']['new_order'][language])],
        [KeyboardButton(translations['buttons']['history'][language])],
        [KeyboardButton(translations['buttons']['settings'][language]),
         KeyboardButton(translations['buttons']['support'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(translations['main_menu'][language], reply_markup=reply_markup)


def confirmation_menu(update: Update, context: CallbackContext, pickup, destination, cost, duration):
    """Display ride confirmation menu"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton(translations['buttons']['confirm'][language])],
        [KeyboardButton(translations['buttons']['cancel'][language])]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    message_text = translations['ride_confirmation'][language].format(
        pickup=pickup,
        destination=destination,
        cost=cost,
        duration=duration
    )

    update.message.reply_text(message_text, reply_markup=reply_markup)


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


def location_request_menu(update: Update, context: CallbackContext):
    """Request user location"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton('📍 Отправить мое местоположение' if language == 'rus' else '📍 Менің орналасқан жерімді жіберу',
                        request_location=True)]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return reply_markup


def contact_request_menu(update: Update, context: CallbackContext):
    """Request user contact"""
    language = context.user_data.get('language', 'kaz')

    keyboard = [
        [KeyboardButton('📞 Поделиться контактом' if language == 'rus' else '📞 Контактымен бөлісу',
                        request_contact=True)]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return reply_markup


def remove_keyboard():
    """Remove custom keyboard"""
    return ReplyKeyboardRemove()
