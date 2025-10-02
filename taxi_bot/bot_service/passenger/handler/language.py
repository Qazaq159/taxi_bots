from telegram import ReplyKeyboardRemove
from telegram import Update
from telegram.ext import CallbackContext

from bot_service.passenger.dictionary import translations
from bot_service.passenger.states import LANGUAGE, REGISTRATION
from bot_service.passenger.handler.registration import start_phone_verification


def language_handler(update: Update, context: CallbackContext) -> int:
    language = context.user_data.get('language', 'kaz')
    user_language = update.message.text

    if user_language == '🇰🇿 Қазақша':
        context.user_data['language'] = 'kaz'
        language = 'kaz'
        update.message.reply_text(translations['language_selected'][language],
                                  reply_markup=ReplyKeyboardRemove())
        return start_phone_verification(update, context)

    elif user_language == '🇷🇺 Русский':
        context.user_data['language'] = 'rus'
        language = 'rus'
        update.message.reply_text(translations['language_selected'][language],
                                  reply_markup=ReplyKeyboardRemove())
        return start_phone_verification(update, context)

    else:
        update.message.reply_text(translations['choose_valid_language'][language])
        return LANGUAGE
