import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler

from bot_service.driver.dictionary import translations, help_text_rus, help_text_kaz
from bot_service.driver.menu import language_menu
from bot_service.driver.states import LANGUAGE

logger = logging.getLogger(__name__)


def start(update: Update, context: CallbackContext) -> int:
    context.user_data['current_question'] = 0
    language = context.user_data.get('language', 'kaz')
    update.message.reply_text(translations['start_prompt'][language])  # Default to Kazakh

    if context.user_data.get('started', False):
        update.message.reply_text(translations['already_started'][language])
        return

    language_menu(update, context)
    context.user_data['started'] = True
    return LANGUAGE


def help_bot(update: Update, context: CallbackContext) -> int:
    language = context.user_data.get('language', 'kaz')

    if language == 'rus':
        update.message.reply_text(help_text_rus)
    else:
        update.message.reply_text(help_text_kaz)


def cancel(update: Update, context: CallbackContext) -> int:
    logger.info(f"Session ended, chat_id = {update.message.chat_id}")
    context.user_data['timer_stop'] = True
    language = context.user_data.get('language', 'kaz')
    update.message.reply_text(translations['cancel_message'][language], reply_markup=ReplyKeyboardRemove())
    context.user_data['started'] = False
    return ConversationHandler.END
