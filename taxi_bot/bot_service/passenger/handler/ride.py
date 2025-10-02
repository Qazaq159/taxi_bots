"""
Passenger Ride Handlers
Handles ride ordering process
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.services import PassengerService, RideService, geocode_address
from ..dictionary import translations
from ..states import PICKUP_ADDRESS, DESTINATION_ADDRESS, CONFIRM_RIDE, WAITING_DRIVER, RATING, MAIN_MENU
from ..menu import main_menu, confirmation_menu, rating_menu, location_request_menu
import logging

logger = logging.getLogger(__name__)


def start_ride_order(update: Update, context: CallbackContext) -> int:
    """Start ride ordering process"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    # Check if user is registered
    passenger, _ = PassengerService.get_or_create_passenger(telegram_id)
    if not passenger or not passenger.user.is_phone_verified:
        update.message.reply_text(translations['please_register_first'][language])
        return ConversationHandler.END

    # Ask for pickup location
    keyboard = [[KeyboardButton(
        translations['buttons']['send_location'][language],
        request_location=True
    )]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    update.message.reply_text(
        translations['enter_pickup'][language],
        reply_markup=reply_markup
    )

    # Clear any previous ride data
    context.user_data['ride_data'] = {}
    return PICKUP_ADDRESS


def handle_pickup_location(update: Update, context: CallbackContext) -> int:
    """Handle pickup location (text or location)"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    print(f"[PASSENGER_LOG] {telegram_id} entering handle_pickup_location")
    print(f"[PASSENGER_LOG] {telegram_id} context.user_data keys: {list(context.user_data.keys())}")

    # Initialize ride_data if it doesn't exist
    if 'ride_data' not in context.user_data:
        context.user_data['ride_data'] = {}
        print(f"[PASSENGER_LOG] {telegram_id} initialized ride_data")

    if update.message.location:
        # User sent location
        lat = update.message.location.latitude
        lng = update.message.location.longitude

        # TODO: Reverse geocode to get address
        address = f"📍 Координаты: {lat:.6f}, {lng:.6f}"
        print(f"[PASSENGER_LOG] {telegram_id} processing location: {lat}, {lng}")

        context.user_data['ride_data']['pickup_address'] = address
        context.user_data['ride_data']['pickup_lat'] = lat
        context.user_data['ride_data']['pickup_lng'] = lng
        print(f"[PASSENGER_LOG] {telegram_id} stored pickup location data")

    elif update.message.text:
        # User sent address as text
        address = update.message.text.strip()
        print(f"[PASSENGER_LOG] {telegram_id} processing text address: '{address}'")

        if len(address) < 5:
            update.message.reply_text(translations['invalid_address'][language])
            return PICKUP_ADDRESS

        # TODO: Geocode address to coordinates
        lat, lng = geocode_address(address)
        print(f"[PASSENGER_LOG] {telegram_id} geocoded to: {lat}, {lng}")

        context.user_data['ride_data']['pickup_address'] = address
        context.user_data['ride_data']['pickup_lat'] = lat
        context.user_data['ride_data']['pickup_lng'] = lng
        print(f"[PASSENGER_LOG] {telegram_id} stored pickup address data")
    else:
        update.message.reply_text(translations['invalid_pickup'][language])
        return PICKUP_ADDRESS

    # Ask for destination
    keyboard = [[KeyboardButton(
        translations['buttons']['send_location'][language],
        request_location=True
    )]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    print(f"[PASSENGER_LOG] {telegram_id} asking for destination, returning DESTINATION_ADDRESS")
    update.message.reply_text(
        translations['enter_destination'][language],
        reply_markup=reply_markup
    )

    return DESTINATION_ADDRESS


def handle_destination_location(update: Update, context: CallbackContext) -> int:
    """Handle destination location (text or location)"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    print(f"[PASSENGER_LOG] {telegram_id} entering handle_destination_location")
    print(f"[PASSENGER_LOG] {telegram_id} context.user_data keys: {list(context.user_data.keys())}")

    # Initialize ride_data if it doesn't exist, or migrate from old format
    if 'ride_data' not in context.user_data:
        context.user_data['ride_data'] = {}
        print(f"[PASSENGER_LOG] {telegram_id} initialized ride_data in destination handler")
        
        # Check if pickup data exists in old format and migrate it
        if 'pickup_address' in context.user_data:
            context.user_data['ride_data']['pickup_address'] = context.user_data['pickup_address']
            context.user_data['ride_data']['pickup_lat'] = context.user_data.get('pickup_lat')
            context.user_data['ride_data']['pickup_lng'] = context.user_data.get('pickup_lng')
            print(f"[PASSENGER_LOG] {telegram_id} migrated pickup data from old format")

    if update.message.location:
        # User sent location
        lat = update.message.location.latitude
        lng = update.message.location.longitude

        # TODO: Reverse geocode to get address
        address = f"📍 Координаты: {lat:.6f}, {lng:.6f}"
        print(f"[PASSENGER_LOG] {telegram_id} processing destination location: {lat}, {lng}")

        context.user_data['ride_data']['destination_address'] = address
        context.user_data['ride_data']['destination_lat'] = lat
        context.user_data['ride_data']['destination_lng'] = lng
        print(f"[PASSENGER_LOG] {telegram_id} stored destination location data")

    elif update.message.text:
        # User sent address as text
        address = update.message.text.strip()
        print(f"[PASSENGER_LOG] {telegram_id} processing destination text address: '{address}'")

        if len(address) < 5:
            update.message.reply_text(translations['invalid_address'][language])
            return DESTINATION_ADDRESS

        # TODO: Geocode address to coordinates
        lat, lng = geocode_address(address)
        print(f"[PASSENGER_LOG] {telegram_id} geocoded destination to: {lat}, {lng}")

        context.user_data['ride_data']['destination_address'] = address
        context.user_data['ride_data']['destination_lat'] = lat
        context.user_data['ride_data']['destination_lng'] = lng
        print(f"[PASSENGER_LOG] {telegram_id} stored destination address data")
    else:
        update.message.reply_text(translations['invalid_destination'][language])
        return DESTINATION_ADDRESS

    # Show cost calculation
    update.message.reply_text(translations['calculating_cost'][language])

    # Create ride request to get cost estimate
    telegram_id = str(update.effective_user.id)
    ride_data = context.user_data['ride_data']

    print(f"[PASSENGER_LOG] {telegram_id} creating ride request")
    print(f"[PASSENGER_LOG] {telegram_id} ride_data: {ride_data}")

    ride, distance_km, duration_min = PassengerService.create_ride_request(
        telegram_id=telegram_id,
        pickup_address=ride_data['pickup_address'],
        pickup_lat=ride_data['pickup_lat'],
        pickup_lng=ride_data['pickup_lng'],
        destination_address=ride_data['destination_address'],
        destination_lat=ride_data['destination_lat'],
        destination_lng=ride_data['destination_lng']
    )

    print(f"[PASSENGER_LOG] {telegram_id} ride creation result: ride={ride}, distance={distance_km}, duration={duration_min}")

    if not ride:
        print(f"[PASSENGER_LOG] {telegram_id} ERROR: Ride creation failed")
        update.message.reply_text(translations['error_occurred'][language])
        return ConversationHandler.END

    # Store ride ID
    ride_id_str = str(ride.id)
    context.user_data['ride_id'] = ride_id_str
    print(f"[PASSENGER_LOG] {telegram_id} stored ride_id: {ride_id_str}")
    print(f"[PASSENGER_LOG] {telegram_id} context.user_data after storing: {context.user_data}")

    # Show confirmation
    confirmation_menu(
        update,
        context,
        ride_data['pickup_address'],
        ride_data['destination_address'],
        int(ride.display_cost),
        duration_min
    )

    return CONFIRM_RIDE


def handle_ride_confirmation(update: Update, context: CallbackContext) -> int:
    """Handle ride confirmation"""
    language = context.user_data.get('language', 'kaz')
    user_response = update.message.text
    telegram_id = str(update.effective_user.id)

    print(f"[PASSENGER_LOG] {telegram_id} in CONFIRM_RIDE state, input: '{user_response}'")
    print(f"[PASSENGER_LOG] {telegram_id} context.user_data keys: {list(context.user_data.keys())}")

    confirm_button_text = translations['buttons']['confirm'][language]
    cancel_button_text = translations['buttons']['cancel'][language]
    print(f"[PASSENGER_LOG] {telegram_id} expected confirm button: '{confirm_button_text}'")
    print(f"[PASSENGER_LOG] {telegram_id} expected cancel button: '{cancel_button_text}'")
    print(f"[PASSENGER_LOG] {telegram_id} user_response == confirm_button: {user_response == confirm_button_text}")

    if user_response == translations['buttons']['confirm'][language]:
        print(f"[PASSENGER_LOG] {telegram_id} confirming ride")

        # Confirm the ride
        ride_id = context.user_data.get('ride_id')
        print(f"[PASSENGER_LOG] {telegram_id} ride_id from context: {ride_id}")

        if not ride_id:
            print(f"[PASSENGER_LOG] {telegram_id} ERROR: No ride_id found in context.user_data")
            update.message.reply_text(translations['error_occurred'][language])
            return ConversationHandler.END

        print(f"[PASSENGER_LOG] {telegram_id} ride confirmed successfully, showing waiting buttons")

        update.message.reply_text(
            translations['ride_confirmed'][language],
            reply_markup=ReplyKeyboardRemove()
        )

        # Show waiting for driver with cancel and increase cost options
        keyboard = [
            [KeyboardButton(translations['buttons']['cancel_ride'][language])],
            [KeyboardButton(translations['buttons']['increase_cost'][language])]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        print(f"[PASSENGER_LOG] {telegram_id} showing waiting buttons, returning WAITING_DRIVER")
        update.message.reply_text(
            translations['searching_driver'][language],
            reply_markup=reply_markup
        )

        # TODO: Notify drivers about new ride request

        return WAITING_DRIVER

    elif user_response == translations['buttons']['cancel'][language]:
        print(f"[PASSENGER_LOG] {telegram_id} cancelling ride in confirmation")
        # Cancel the ride
        ride_id = context.user_data.get('ride_id')
        telegram_id = str(update.effective_user.id)

        if ride_id:
            RideService.cancel_ride(ride_id, telegram_id, "Cancelled before confirmation")

        update.message.reply_text(
            translations['ride_cancelled'][language],
            reply_markup=ReplyKeyboardRemove()
        )

        main_menu(update, context)
        return ConversationHandler.END
    else:
        print(f"[PASSENGER_LOG] {telegram_id} invalid input in CONFIRM_RIDE, showing error message")
        update.message.reply_text(translations['choose_confirm_cancel'][language])
        return CONFIRM_RIDE


def handle_waiting_driver(update: Update, context: CallbackContext) -> int:
    """Handle actions while waiting for driver"""
    language = context.user_data.get('language', 'kaz')
    user_response = update.message.text
    ride_id = context.user_data.get('ride_id')
    telegram_id = str(update.effective_user.id)

    print(f"[PASSENGER_LOG] {telegram_id} in WAITING_DRIVER state, input: '{user_response}', ride_id: {ride_id}")

    if user_response == translations['buttons']['cancel_ride'][language]:
        # Cancel the ride
        if ride_id:
            success, ride = RideService.cancel_ride(ride_id, telegram_id, "Cancelled by passenger")
            if success:
                update.message.reply_text(
                    translations['ride_cancelled'][language],
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                update.message.reply_text(translations['cancel_failed'][language])

        main_menu(update, context)
        return ConversationHandler.END

    elif user_response == translations['buttons']['increase_cost'][language]:
        # Increase ride cost (only if driver not yet assigned)
        if ride_id:
            success, ride = RideService.increase_ride_cost(ride_id, telegram_id)
            if success:
                update.message.reply_text(
                    translations['cost_increased'][language],
                    reply_markup=ReplyKeyboardRemove()
                )
                # Keep the same buttons after cost increase
                keyboard = [
                    [KeyboardButton(translations['buttons']['cancel_ride'][language])],
                    [KeyboardButton(translations['buttons']['increase_cost'][language])]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                update.message.reply_text(
                    translations['searching_driver'][language],
                    reply_markup=reply_markup
                )
            else:
                # Driver might have been assigned - show appropriate error
                update.message.reply_text(translations['cost_increase_not_available'][language])
        else:
            update.message.reply_text(translations['error_occurred'][language])

        return WAITING_DRIVER

    elif user_response == translations['buttons']['sos'][language]:
        # SOS - help on the road
        update.message.reply_text(
            translations['help_on_road'][language],
            reply_markup=ReplyKeyboardRemove()
        )

        # TODO: Send emergency notification to admin
        logger.warning(f"SOS activated by passenger {telegram_id} - help on the road")

        main_menu(update, context)
        return ConversationHandler.END

    # Check if driver was assigned (this would be called by webhook/callback)
    return WAITING_DRIVER


def driver_assigned_notification(update: Update, context: CallbackContext, driver_info: dict) -> None:
    """Notify passenger that driver was assigned"""
    language = context.user_data.get('language', 'kaz')

    message = translations['driver_found'][language].format(
        driver_name=driver_info.get('name', 'N/A'),
        rating=driver_info.get('rating', 'N/A'),
        car=driver_info.get('car', 'N/A'),
        phone=driver_info.get('phone', 'N/A')
    )

    # Remove waiting buttons
    update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

    # Show ride status buttons
    keyboard = [
        [KeyboardButton(translations['buttons']['cancel_ride'][language])],
        [KeyboardButton(translations['buttons']['sos'][language])]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=translations['driver_enroute'][language],
        reply_markup=reply_markup
    )


def ride_completed_notification(update: Update, context: CallbackContext, ride_info: dict) -> int:
    """Notify passenger that ride is completed and ask for rating"""
    language = context.user_data.get('language', 'kaz')

    message = translations['ride_completed'][language].format(
        cost=ride_info.get('final_cost', 'N/A'),
        duration=ride_info.get('duration', 'N/A')
    )

    update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

    # Show rating menu
    reply_markup = rating_menu(update, context)
    update.message.reply_text(
        translations['rate_driver'][language],
        reply_markup=reply_markup
    )

    return RATING


def handle_rating(update: Update, context: CallbackContext) -> int:
    """Handle driver rating"""
    language = context.user_data.get('language', 'kaz')
    query = update.callback_query
    telegram_id = str(update.effective_user.id)

    if not query:
        return MAIN_MENU

    query.answer()

    # Extract rating from callback data: rate_driver_X_ride_id
    rating_data = query.data.split('_')

    if len(rating_data) >= 4 and rating_data[0] == 'rate' and rating_data[1] == 'driver':
        try:
            stars = int(rating_data[2])
            ride_id = rating_data[3]

            # Submit rating
            from api.services import RideService
            success, rating = RideService.rate_ride(ride_id, telegram_id, stars)

            if success:
                query.edit_message_text(translations['rating_submitted'][language])
                # Show main menu after successful rating
                from telegram import ReplyKeyboardMarkup, KeyboardButton
                
                # Send thank you message
                context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=translations['thank_you_rating'][language]
                )
                
                # Create main menu buttons
                keyboard = [
                    [KeyboardButton(translations['buttons']['new_order'][language])],
                    [KeyboardButton(translations['buttons']['history'][language])],
                    [KeyboardButton(translations['buttons']['settings'][language]),
                     KeyboardButton(translations['buttons']['support'][language])]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                # Send main menu
                context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=translations['main_menu'][language],
                    reply_markup=reply_markup
                )
            else:
                query.edit_message_text(translations['rating_failed'][language])

        except (ValueError, IndexError) as e:
            query.edit_message_text(translations['rating_failed'][language])
    else:
        # Handle old format: rate_X (for backward compatibility)
        if len(rating_data) == 2 and rating_data[0] == 'rate':
            try:
                stars = int(rating_data[1])
                ride_id = context.user_data.get('ride_id')

                if ride_id:
                    from api.services import RideService
                    success, rating = RideService.rate_ride(ride_id, telegram_id, stars)

                    if success:
                        query.edit_message_text(translations['rating_submitted'][language])
                        # Show main menu after successful rating
                        from telegram import ReplyKeyboardMarkup, KeyboardButton
                        
                        # Send thank you message
                        context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=translations['thank_you_rating'][language]
                        )
                        
                        # Create main menu buttons
                        keyboard = [
                            [KeyboardButton(translations['buttons']['new_order'][language])],
                            [KeyboardButton(translations['buttons']['history'][language])],
                            [KeyboardButton(translations['buttons']['settings'][language]),
                             KeyboardButton(translations['buttons']['support'][language])]
                        ]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        
                        # Send main menu
                        context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=translations['main_menu'][language],
                            reply_markup=reply_markup
                        )
                    else:
                        query.edit_message_text(translations['rating_failed'][language])
                else:
                    query.edit_message_text(translations['rating_failed'][language])

            except (ValueError, IndexError) as e:
                query.edit_message_text(translations['rating_failed'][language])
        else:
            query.edit_message_text(translations['rating_failed'][language])

    return MAIN_MENU


def show_ride_history(update: Update, context: CallbackContext) -> None:
    """Show passenger's ride history"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    rides = PassengerService.get_passenger_rides(telegram_id)

    if not rides:
        update.message.reply_text(translations['no_ride_history'][language])
        return

    history_text = translations['ride_history_header'][language] + "\n\n"

    for ride in rides[:10]:  # Show last 10 rides
        status_text = dict(ride.STATUS_CHOICES).get(ride.status, ride.status)
        history_text += f"🚗 {ride.pickup_address[:30]}... → {ride.destination_address[:30]}...\n"
        history_text += f"💰 {ride.final_cost or ride.estimated_cost} тенге\n"
        history_text += f"📅 {ride.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        history_text += f"📊 {status_text}\n\n"

    update.message.reply_text(history_text)


# Add missing translations
def add_missing_translations():
    """Add missing translations to dictionary"""
    missing_translations = {
        'please_register_first': {
            'kaz': '❌ Алдымен тіркелуіңіз керек. /start командасын пайдаланыңыз.',
            'rus': '❌ Сначала нужно зарегистрироваться. Используйте команду /start.'
        },
        'invalid_pickup': {
            'kaz': '❌ Дұрыс емес орналасу. Мекенжайды немесе геолокация жіберіңіз:',
            'rus': '❌ Неверное местоположение. Отправьте адрес или геолокацию:'
        },
        'invalid_destination': {
            'kaz': '❌ Дұрыс емес мекенжай. Мекенжайды немесе геолокация жіберіңіз:',
            'rus': '❌ Неверный адрес назначения. Отправьте адрес или геолокацию:'
        },
        'choose_confirm_cancel': {
            'kaz': '❌ "Растау" немесе "Болдырмау" батырмасын басыңыз:',
            'rus': '❌ Нажмите кнопку "Подтвердить" или "Отменить":'
        },
        'searching_driver': {
            'kaz': '🔍 Жүргізуші іздеуде... Күтіңіз...',
            'rus': '🔍 Ищем водителя... Ожидайте...'
        },
        'cancel_failed': {
            'kaz': '❌ Болдыру сәтсіз. Қайталап көріңіз.',
            'rus': '❌ Не удалось отменить. Попробуйте еще раз.'
        },
        'sos_activated': {
            'kaz': '🆘 SOS белсендірілді! Әкімшілік хабардар етілді.',
            'rus': '🆘 SOS активирован! Администрация уведомлена.'
        },
        'driver_enroute': {
            'kaz': '🚗 Жүргізуші жолда. Күтіңіз...',
            'rus': '🚗 Водитель в пути. Ожидайте...'
        },
        'rate_driver': {
            'kaz': '⭐ Жүргізушіні бағалаңыз:',
            'rus': '⭐ Оцените водителя:'
        },
        'rating_failed': {
            'kaz': '❌ Бағалау сәтсіз. Қайталап көріңіз.',
            'rus': '❌ Не удалось оценить. Попробуйте еще раз.'
        },
        'no_ride_history': {
            'kaz': '📋 Сапар тарихы жоқ.',
            'rus': '📋 История поездок пуста.'
        },
        'ride_history_header': {
            'kaz': '📋 Сапар тарихы:',
            'rus': '📋 История поездок:'
        },
        'send_location': {
            'kaz': '📍 Орналасуды жіберу',
            'rus': '📍 Отправить местоположение'
        },
        'cost_increased': {
            'kaz': '💰 Тапсырыс құны арттырылды! Жаңа жүргізушілер ізделуде...',
            'rus': '💰 Стоимость заказа увеличена! Ищем новых водителей...'
        },
        'cost_increase_failed': {
            'kaz': '❌ Құнды арттыру сәтсіз. Қайталап көріңіз.',
            'rus': '❌ Не удалось увеличить стоимость. Попробуйте еще раз.'
        },
        'cost_increase_not_available': {
            'kaz': '❌ Жүргізуші тағайындалғаннан кейін құнды арттыру мүмкін емес.',
            'rus': '❌ Нельзя увеличить стоимость после назначения водителя.'
        },
        'help_on_road': {
            'kaz': '🚨 Жолда көмек! Жүргізушіңізге хабар жіберілді. Көмек жолда!',
            'rus': '🚨 Помощь в пути! Ваше сообщение отправлено водителю. Помощь в пути!'
        }
    }

    # This would be added to the main dictionary file
    return missing_translations
