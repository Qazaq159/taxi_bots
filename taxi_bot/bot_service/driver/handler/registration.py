"""
Driver Registration Handlers
Handles driver registration, vehicle info, and document upload
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
import sys
import os
from datetime import datetime

from api.services import UserService, DriverService
from bot_service.driver.dictionary import translations
from bot_service.driver.menu import contact_request_menu, main_menu
from bot_service.driver.states import MAIN_MENU, VEHICLE_INFO, VERIFICATION_PENDING, REGISTRATION, PHONE_VERIFICATION, \
    DOCUMENT_UPLOAD

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


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

        # Ask for phone number via contact sharing
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

    except Exception as e:
        logger.error(f"Error updating full name for driver {telegram_id}: {str(e)}")
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

    # Verify phone number
    success, cleaned_phone = UserService.verify_phone_number(telegram_id, phone_number)

    if success:
        update.message.reply_text(
            translations['phone_verified'][language].format(phone=cleaned_phone),
            reply_markup=ReplyKeyboardRemove()
        )

        # Check if user exists in database with this phone
        user = UserService.get_user_by_phone(cleaned_phone)

        if user and user.is_phone_verified:
            # User exists and is verified - check driver status
            driver, driver_created = DriverService.get_or_create_driver(telegram_id)

            if driver and driver.status == 'verified':
                # Driver already registered and verified - go to main menu
                update.message.reply_text(
                    translations['already_verified'][language].format(name=user.full_name),
                    reply_markup=ReplyKeyboardRemove()
                )
                main_menu(update, context)
                return MAIN_MENU
            elif driver and driver.status == 'pending':
                # Check if driver has vehicle and documents - if not, continue registration
                has_vehicle = hasattr(driver, 'vehicle') and driver.vehicle is not None
                has_documents = driver.documents.exists()
                
                if has_vehicle and has_documents:
                    # Driver registered with all info but pending verification
                    update.message.reply_text(
                        translations['verification_pending'][language],
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return VERIFICATION_PENDING
                elif has_vehicle:
                    # Has vehicle - check which documents are missing
                    has_license = driver.documents.filter(document_type='license').exists()
                    has_vehicle_reg = driver.documents.filter(document_type='vehicle_registration').exists()
                    
                    if not has_license:
                        # Start with driver license
                        context.user_data['current_document'] = 'driver_license'
                        update.message.reply_text(translations['upload_driver_license'][language])
                        return DOCUMENT_UPLOAD
                    elif not has_vehicle_reg:
                        # Start with vehicle registration
                        context.user_data['current_document'] = 'vehicle_registration'
                        update.message.reply_text(translations['upload_vehicle_registration'][language])
                        return DOCUMENT_UPLOAD
                    else:
                        # All documents exist but still pending
                        update.message.reply_text(
                            translations['verification_pending'][language],
                            reply_markup=ReplyKeyboardRemove()
                        )
                        return VERIFICATION_PENDING
                else:
                    # No vehicle info - start vehicle registration
                    update.message.reply_text(translations['enter_vehicle_make'][language])
                    return VEHICLE_INFO
            else:
                # User verified but needs vehicle info
                update.message.reply_text(translations['enter_vehicle_make'][language])
                return VEHICLE_INFO
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
        update.message.reply_text(
            translations['phone_verified'][language].format(phone=cleaned_phone),
            reply_markup=ReplyKeyboardRemove()
        )

        # Check if user exists in database with this phone
        user = UserService.get_user_by_phone(cleaned_phone)

        if user and user.is_phone_verified:
            # User exists and is verified - check driver status
            driver, driver_created = DriverService.get_or_create_driver(telegram_id)

            if driver and driver.status == 'verified':
                # Driver already registered and verified - go to main menu
                update.message.reply_text(
                    translations['already_verified'][language].format(name=user.full_name),
                    reply_markup=ReplyKeyboardRemove()
                )
                main_menu(update, context)
                return MAIN_MENU
            elif driver and driver.status == 'pending':
                # Check if driver has vehicle and documents - if not, continue registration
                has_vehicle = hasattr(driver, 'vehicle') and driver.vehicle is not None
                has_documents = driver.documents.exists()
                
                if has_vehicle and has_documents:
                    # Driver registered with all info but pending verification
                    update.message.reply_text(
                        translations['verification_pending'][language],
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return VERIFICATION_PENDING
                elif has_vehicle:
                    # Has vehicle - check which documents are missing
                    has_license = driver.documents.filter(document_type='license').exists()
                    has_vehicle_reg = driver.documents.filter(document_type='vehicle_registration').exists()
                    
                    if not has_license:
                        # Start with driver license
                        context.user_data['current_document'] = 'driver_license'
                        update.message.reply_text(translations['upload_driver_license'][language])
                        return DOCUMENT_UPLOAD
                    elif not has_vehicle_reg:
                        # Start with vehicle registration
                        context.user_data['current_document'] = 'vehicle_registration'
                        update.message.reply_text(translations['upload_vehicle_registration'][language])
                        return DOCUMENT_UPLOAD
                    else:
                        # All documents exist but still pending
                        update.message.reply_text(
                            translations['verification_pending'][language],
                            reply_markup=ReplyKeyboardRemove()
                        )
                        return VERIFICATION_PENDING
                else:
                    # No vehicle info - start vehicle registration
                    update.message.reply_text(translations['enter_vehicle_make'][language])
                    return VEHICLE_INFO
            else:
                # User verified but needs vehicle info
                update.message.reply_text(translations['enter_vehicle_make'][language])
                return VEHICLE_INFO
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


def handle_vehicle_info(update: Update, context: CallbackContext) -> int:
    """Handle vehicle information input"""
    language = context.user_data.get('language', 'kaz')
    user_input = update.message.text.strip()

    # Initialize vehicle data if not exists
    if 'vehicle_data' not in context.user_data:
        context.user_data['vehicle_data'] = {}

    vehicle_data = context.user_data['vehicle_data']

    # Determine which field we're collecting
    if 'make' not in vehicle_data:
        # Collecting make
        if len(user_input) < 2:
            update.message.reply_text(translations['invalid_vehicle_make'][language])
            return VEHICLE_INFO

        vehicle_data['make'] = user_input
        update.message.reply_text(translations['enter_vehicle_model'][language])
        return VEHICLE_INFO

    elif 'model' not in vehicle_data:
        # Collecting model
        if len(user_input) < 2:
            update.message.reply_text(translations['invalid_vehicle_model'][language])
            return VEHICLE_INFO

        vehicle_data['model'] = user_input
        update.message.reply_text(translations['enter_vehicle_year'][language])
        return VEHICLE_INFO

    elif 'year' not in vehicle_data:
        # Collecting year
        try:
            year = int(user_input)
            current_year = datetime.now().year
            if year < 1900 or year > current_year + 1:
                update.message.reply_text(translations['invalid_year'][language])
                return VEHICLE_INFO
        except ValueError:
            update.message.reply_text(translations['invalid_year'][language])
            return VEHICLE_INFO

        vehicle_data['year'] = year
        update.message.reply_text(translations['enter_vehicle_color'][language])
        return VEHICLE_INFO

    elif 'color' not in vehicle_data:
        # Collecting color
        if len(user_input) < 2:
            update.message.reply_text(translations['invalid_vehicle_color'][language])
            return VEHICLE_INFO

        vehicle_data['color'] = user_input
        update.message.reply_text(translations['enter_license_plate'][language])
        return VEHICLE_INFO

    elif 'license_plate' not in vehicle_data:
        # Collecting license plate
        if len(user_input) < 4:
            update.message.reply_text(translations['invalid_license_plate'][language])
            return VEHICLE_INFO

        vehicle_data['license_plate'] = user_input.upper()

        # Save vehicle information
        telegram_id = str(update.effective_user.id)
        vehicle = DriverService.create_vehicle(
            telegram_id=telegram_id,
            make=vehicle_data['make'],
            model=vehicle_data['model'],
            year=vehicle_data['year'],
            color=vehicle_data['color'],
            license_plate=vehicle_data['license_plate']
        )

        if vehicle:
            update.message.reply_text(translations['vehicle_info_saved'][language])
            
            # Clear vehicle data and start document upload sequence
            context.user_data.pop('vehicle_data', None)
            context.user_data['current_document'] = 'driver_license'
            
            # Ask for driver license first
            update.message.reply_text(translations['upload_driver_license'][language])

            return DOCUMENT_UPLOAD
        else:
            update.message.reply_text(translations['error_occurred'][language])
            return VEHICLE_INFO

    return VEHICLE_INFO


def handle_document_upload(update: Update, context: CallbackContext) -> int:
    """Handle document photo uploads in sequence"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    if not update.message.photo:
        update.message.reply_text(translations['please_send_photo'][language])
        return DOCUMENT_UPLOAD

    # Get the largest photo
    photo = update.message.photo[-1]
    
    # Get current document type from context
    current_document = context.user_data.get('current_document', 'driver_license')
    
    # Map current document to database document type
    document_type_map = {
        'driver_license': 'license',
        'vehicle_registration': 'vehicle_registration'
    }
    
    document_type = document_type_map.get(current_document)
    if not document_type:
        update.message.reply_text(translations['error_occurred'][language])
        return DOCUMENT_UPLOAD

    # Save document
    success = save_driver_document(telegram_id, document_type, photo)

    if success:
        update.message.reply_text(
            translations['document_received'][language],
            reply_markup=ReplyKeyboardRemove()
        )

        # Move to next document or complete registration
        if current_document == 'driver_license':
            # Ask for vehicle registration next
            context.user_data['current_document'] = 'vehicle_registration'
            update.message.reply_text(translations['upload_vehicle_registration'][language])
            return DOCUMENT_UPLOAD
        elif current_document == 'vehicle_registration':
            # All required documents uploaded, complete registration
            context.user_data.pop('current_document', None)
            update.message.reply_text(translations['registration_complete'][language])
            return VERIFICATION_PENDING
    else:
        update.message.reply_text(translations['document_upload_failed'][language])
        return DOCUMENT_UPLOAD




def handle_verification_pending(update: Update, context: CallbackContext) -> int:
    """Handle messages while verification is pending"""
    language = context.user_data.get('language', 'kaz')

    update.message.reply_text(translations['verification_pending'][language])
    return VERIFICATION_PENDING


def determine_document_type(caption: str, context: CallbackContext) -> str:
    """Determine document type from caption"""
    caption_lower = caption.lower()

    if any(word in caption_lower for word in ['license', 'права', 'куәлік']):
        return 'license'
    elif any(word in caption_lower for word in ['passport', 'паспорт']):
        return 'passport'
    elif any(word in caption_lower for word in ['registration', 'регистрация', 'тіркеу']):
        return 'vehicle_registration'
    elif any(word in caption_lower for word in ['insurance', 'страховка', 'сақтандыру']):
        return 'insurance'

    return None


def save_driver_document(telegram_id: str, document_type: str, photo) -> bool:
    """Save driver document to database with image download"""
    try:
        import requests
        import os
        from django.core.files.base import ContentFile
        from api.models import Driver, DriverDocument

        user, _ = UserService.get_or_create_user(telegram_id)
        driver = user.driver_profile

        # Get bot token for downloading image
        from telegram.ext import Updater
        from bot_service.driver.main import updater
        
        # Get file info from Telegram
        file_info = updater.bot.get_file(photo.file_id)
        
        # Download image from Telegram
        response = requests.get(file_info.file_path)
        if response.status_code == 200:
            # Create filename
            file_extension = file_info.file_path.split('.')[-1] if '.' in file_info.file_path else 'jpg'
            filename = f"{document_type}_{telegram_id}_{photo.file_id[:10]}.{file_extension}"
            
            # Create or update document
            document, created = DriverDocument.objects.update_or_create(
                driver=driver,
                document_type=document_type,
                defaults={
                    'document_number': f"{document_type}_{telegram_id}_{photo.file_id[:10]}",
                    'status': 'pending'
                }
            )
            
            # Save image to ImageField
            document.document_image.save(
                filename,
                ContentFile(response.content),
                save=True
            )

            logger.info(f"Document {document_type} saved for driver {telegram_id}")
            return True
        else:
            logger.error(f"Failed to download image from Telegram for driver {telegram_id}")
            return False

    except Exception as e:
        logger.error(f"Error saving document for driver {telegram_id}: {str(e)}")
        return False
