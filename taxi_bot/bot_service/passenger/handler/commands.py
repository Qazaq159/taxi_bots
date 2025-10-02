from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler

from bot_service.passenger.dictionary import translations, help_text_rus, help_text_kaz
from bot_service.passenger.states import LANGUAGE
from bot_service.passenger.menu import language_menu


def start(update: Update, context: CallbackContext) -> int:
    """Start the bot conversation - always restart fresh"""
    # Clear any previous conversation data
    context.user_data.clear()
    
    context.user_data['current_question'] = 0
    language = context.user_data.get('language', 'kaz')
    
    update.message.reply_text(
        translations['start_prompt'][language],
        reply_markup=ReplyKeyboardRemove()
    )

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
    """Cancel current operation and end conversation"""
    context.user_data['timer_stop'] = True
    language = context.user_data.get('language', 'kaz')
    
    update.message.reply_text(
        translations['cancel_message'][language], 
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Inform user how to restart
    update.message.reply_text(
        translations['restart_info'][language]
    )
    
    # Clear conversation data
    context.user_data.clear()
    return ConversationHandler.END
