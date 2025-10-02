"""
Driver Ride Management Handlers
Handles ride notifications, acceptance, and status updates
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler
import sys
import os

from bot_service.driver.dictionary import translations
from bot_service.driver.menu import main_menu
from bot_service.driver.states import MAIN_MENU, LOCATION_UPDATE, RIDE_MANAGEMENT

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.services import DriverService, RideService, UserService
import logging

# Get logger configured from Django settings
logger = logging.getLogger('taxi_bot.bot_service.driver.ride_management')


def toggle_online_status(update: Update, context: CallbackContext) -> int:
    """Toggle driver online/offline status"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text

    # Determine desired status
    if user_input == translations['buttons']['go_online'][language]:
        desired_status = True
    elif user_input == translations['buttons']['go_offline'][language]:
        desired_status = False
    else:
        logger.warning(f"Unknown command from driver {telegram_id}: {user_input}")
        update.message.reply_text(translations['unknown_command'][language])
        return MAIN_MENU

    # Update status
    success, message = DriverService.set_driver_online_status(telegram_id, desired_status)

    if success:
        if desired_status:
            update.message.reply_text(translations['went_online'][language])
            # Ask for location update
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
            update.message.reply_text(translations['went_offline'][language])
    else:
        update.message.reply_text(f"{translations['status_change_failed'][language]}: {message}")

    main_menu(update, context)
    return MAIN_MENU


def handle_location_update(update: Update, context: CallbackContext) -> int:
    """Handle driver location updates"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    if update.message.location:
        lat = update.message.location.latitude
        lng = update.message.location.longitude

        # Update driver location
        success = DriverService.update_driver_location(telegram_id, lat, lng)

        if success:
            update.message.reply_text(
                translations['location_updated'][language],
                reply_markup=ReplyKeyboardRemove()
            )

            # Start looking for rides
            check_for_nearby_rides(update, context)
        else:
            update.message.reply_text(translations['location_update_failed'][language])
    else:
        update.message.reply_text(translations['please_share_location'][language])
        return LOCATION_UPDATE

    main_menu(update, context)
    return MAIN_MENU


def check_for_nearby_rides(update: Update, context: CallbackContext):
    """Check for nearby ride requests"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        nearby_rides = DriverService.get_nearby_rides(telegram_id)

        if nearby_rides:
            # Show first available ride
            ride_info = nearby_rides[0]
            ride = ride_info['ride']
            distance = ride_info['distance_km']

            # Store ride info for later use
            context.user_data['current_ride_offer'] = {
                'ride_id': str(ride.id),
                'distance': distance
            }

            # Send ride notification
            message = translations['new_ride_request'][language].format(
                pickup=ride.pickup_address[:50] + "..." if len(ride.pickup_address) > 50 else ride.pickup_address,
                destination=ride.destination_address[:50] + "..." if len(ride.destination_address) > 50 else ride.destination_address,
                cost=int(ride.estimated_cost),
                distance=distance
            )

            # Create inline keyboard for quick response
            keyboard = [
                [
                    InlineKeyboardButton(
                        translations['buttons']['accept'][language],
                        callback_data=f"accept_ride_{ride.id}"
                    ),
                    InlineKeyboardButton(
                        translations['buttons']['reject'][language],
                        callback_data=f"reject_ride_{ride.id}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send notification and get message object
            sent_message = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message,
                reply_markup=reply_markup
            )

            # Store message ID for potential deletion
            context.user_data['current_ride_message_id'] = sent_message.message_id

            # Set timer for auto-reject after 60 seconds (1 minute)
            context.job_queue.run_once(
                auto_reject_ride,
                60,
                context={
                    'chat_id': update.effective_chat.id,
                    'ride_id': str(ride.id),
                    'telegram_id': telegram_id,
                    'language': language,
                    'message_id': sent_message.message_id
                }
            )
        else:
            update.message.reply_text(translations['no_rides_available'][language])

    except Exception as e:
        logger.error(f"Error checking nearby rides for {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def handle_ride_response(update: Update, context: CallbackContext) -> int:
    """Handle ride acceptance/rejection via inline keyboard"""
    query = update.callback_query
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    logger.info(f"Driver {telegram_id} responding to ride: {query.data if query else 'No query'}")

    if not query:
        return MAIN_MENU

    query.answer()

    # Skip rating callbacks - they are no longer handled by driver bot
    if query.data.startswith('rate_passenger_'):
        logger.info(f"Rating callback {query.data} is no longer handled by driver bot")
        return MAIN_MENU

    # Parse callback data
    try:
        action, ride_id = query.data.split('_', 2)[0], query.data.split('_', 2)[2]
    except (IndexError, ValueError) as e:
        logger.error(f"Error parsing callback data '{query.data}': {str(e)}")
        query.edit_message_text(translations['invalid_action'][language])
        return MAIN_MENU

    if action == 'accept':
        # Accept the ride
        success, result = DriverService.accept_ride(telegram_id, ride_id)

        if success:
            ride = result
            passenger = ride.passenger

            # Update message
            query.edit_message_text(translations['ride_accepted'][language].format(
                passenger_name=passenger.user.full_name,
                phone=passenger.user.phone_number,
                pickup=ride.pickup_address
            ))

            # Clear stored message ID since ride was accepted
            context.user_data.pop('current_ride_message_id', None)

            # Show ride management buttons
            keyboard = [
                [KeyboardButton(translations['buttons']['arrived'][language])],
                [KeyboardButton(translations['buttons']['start_ride'][language])],
                [KeyboardButton(translations['buttons']['cancel_ride'][language])]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations['ride_management_info'][language],
                reply_markup=reply_markup
            )

            # Store active ride info
            context.user_data['active_ride'] = {
                'ride_id': ride_id,
                'status': 'assigned'
            }

            logger.info(f"Set active ride for driver {telegram_id}: {context.user_data['active_ride']}")

            return RIDE_MANAGEMENT
        else:
            query.edit_message_text(f"{translations['ride_accept_failed'][language]}: {result}")

    elif action == 'reject':
        # Reject the ride
        query.edit_message_text(translations['ride_rejected'][language])

        # Clear stored message ID since ride was rejected
        context.user_data.pop('current_ride_message_id', None)

        # Look for more rides
        context.job_queue.run_once(
            delayed_ride_check,
            5,
            context={
                'update': update,
                'context': context
            }
        )

    elif action == 'cancel' and query.data.startswith('cancel_ride_'):
        # Handle ride cancellation from active rides view
        ride_id = query.data.split('_')[2]

        # Cancel the ride
        success, ride = RideService.cancel_ride(ride_id, telegram_id, "Cancelled by driver")

        if success:
            query.edit_message_text(translations['ride_cancelled_by_driver'][language])
        else:
            query.edit_message_text(translations['cancel_failed'][language])

    return MAIN_MENU


def handle_ride_management(update: Update, context: CallbackContext) -> int:
    """Handle ride status updates during active ride"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)
    user_input = update.message.text

    logger.info(f"Driver {telegram_id} in ride management, input: '{user_input}', language: {language}")

    # Debug logging for button comparison
    arrived_button_text = translations['buttons']['arrived'][language]
    logger.info(f"Expected 'arrived' button text: '{arrived_button_text}'")
    logger.info(f"User input matches arrived button: {user_input == arrived_button_text}")

    active_ride = context.user_data.get('active_ride')
    if not active_ride:
        update.message.reply_text(translations['no_active_ride'][language])
        main_menu(update, context)
        return MAIN_MENU

    ride_id = active_ride['ride_id']
    current_status = active_ride['status']
    logger.info(f"Active ride status: {current_status}")

    if user_input == translations['buttons']['arrived'][language] and current_status == 'assigned':
        # Driver arrived at pickup
        success, ride = RideService.update_ride_status(ride_id, 'driver_arrived', telegram_id=telegram_id)

        if success:
            update.message.reply_text(translations['marked_arrived'][language])
            active_ride['status'] = 'driver_arrived'

            # Notify passenger that driver has arrived
            try:
                passenger = ride.passenger
                driver = ride.driver

                # Get passenger's language preference
                passenger_language = passenger.user.language if hasattr(passenger.user, 'language') else 'kaz'

                # Create notification message
                vehicle_info = ""
                if hasattr(driver, 'vehicle') and driver.vehicle:
                    vehicle_info = f"{driver.vehicle.make} {driver.vehicle.model}"
                else:
                    vehicle_info = "Көлік мәліметтері жоқ"

                notification_message = translations['driver_arrived_notification'][passenger_language].format(
                    driver_name=driver.user.full_name,
                    phone=driver.user.phone_number,
                    vehicle_info=vehicle_info
                )

                # Send notification to passenger
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

                try:
                    from bot_service.passenger.main import notify_passenger
                    notify_passenger(passenger.user.telegram_id, notification_message)
                except ImportError:
                    # Fallback: try to send notification directly
                    try:
                        from bot_service.passenger.main import updater as passenger_updater
                        passenger_updater.bot.send_message(
                            chat_id=passenger.user.telegram_id,
                            text=notification_message
                        )
                        logger.info(f"Sent driver arrival notification to passenger {passenger.user.telegram_id} (fallback method)")
                    except Exception as e2:
                        logger.error(f"Failed to send notification via fallback method: {str(e2)}")

                logger.info(f"Sent driver arrival notification to passenger {passenger.user.telegram_id}")

            except Exception as e:
                logger.error(f"Failed to send driver arrival notification to passenger: {str(e)}")

            # Update buttons
            keyboard = [
                [KeyboardButton(translations['buttons']['start_ride'][language])],
                [KeyboardButton(translations['buttons']['cancel_ride'][language])]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            update.message.reply_text(
                translations['wait_for_passenger'][language],
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text(translations['status_update_failed'][language])

    elif user_input == translations['buttons']['start_ride'][language] and current_status == 'driver_arrived':
        # Start the ride
        success, ride = RideService.update_ride_status(ride_id, 'in_progress', telegram_id=telegram_id)

        if success:
            update.message.reply_text(translations['ride_started'][language])
            active_ride['status'] = 'in_progress'

            # Notify passenger that ride has started
            try:
                passenger = ride.passenger
                driver = ride.driver

                # Get passenger's language preference
                passenger_language = passenger.user.language if hasattr(passenger.user, 'language') else 'kaz'

                # Send notification to passenger with SOS button
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

                try:
                    from bot_service.passenger.main import notify_passenger_ride_started
                    notify_passenger_ride_started(
                        passenger.user.telegram_id,
                        driver.user.full_name,
                        driver.user.phone_number,
                        ride.destination_address
                    )
                except ImportError:
                    # Fallback: try to send notification directly
                    try:
                        from bot_service.passenger.main import updater as passenger_updater
                        passenger_updater.bot.send_message(
                            chat_id=passenger.user.telegram_id,
                            text=notification_message
                        )
                        logger.info(f"Sent ride started notification to passenger {passenger.user.telegram_id} (fallback method)")
                    except Exception as e2:
                        logger.error(f"Failed to send notification via fallback method: {str(e2)}")

                logger.info(f"Sent ride started notification to passenger {passenger.user.telegram_id}")

            except Exception as e:
                logger.error(f"Failed to send ride started notification to passenger: {str(e)}")

            # Update buttons
            keyboard = [
                [KeyboardButton(translations['buttons']['complete_ride'][language])],
                [KeyboardButton(translations['buttons']['sos'][language])]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            update.message.reply_text(
                translations['drive_safely'][language],
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text(translations['status_update_failed'][language])

    elif user_input == translations['buttons']['complete_ride'][language] and current_status == 'in_progress':
        # Complete the ride
        success, ride = RideService.update_ride_status(ride_id, 'completed', telegram_id=telegram_id)

        if success:
            # Set final cost (same as estimated for now)
            ride.final_cost = ride.estimated_cost
            ride.save()

            update.message.reply_text(
                translations['ride_completed'][language].format(
                    cost=int(ride.final_cost),
                    duration=ride.duration_minutes or 0
                ),
                reply_markup=ReplyKeyboardRemove()
            )

            # Notify passenger that ride has ended and they can rate the driver
            try:
                passenger = ride.passenger
                driver = ride.driver

                # Get passenger's language preference
                passenger_language = passenger.user.language if hasattr(passenger.user, 'language') else 'kaz'

                # Create rating notification message
                notification_message = translations['ride_completed_passenger_notification'][passenger_language].format(
                    driver_name=driver.user.full_name,
                    cost=int(ride.final_cost),
                    duration=ride.duration_minutes or 0
                )

                # Send notification with rating buttons to passenger
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

                try:
                    from bot_service.passenger.main import notify_passenger_with_rating
                    notify_passenger_with_rating(
                        passenger.user.telegram_id, 
                        notification_message,
                        ride_id,
                        passenger_language
                    )
                    logger.info(f"Sent ride completion notification with rating buttons to passenger {passenger.user.telegram_id}")
                except ImportError:
                    # Fallback: try to send notification without rating buttons
                    try:
                        from bot_service.passenger.main import notify_passenger
                        notify_passenger(passenger.user.telegram_id, notification_message)
                        logger.info(f"Sent ride completion notification to passenger {passenger.user.telegram_id} (fallback method)")
                    except Exception as e2:
                        logger.error(f"Failed to send notification via fallback method: {str(e2)}")

            except Exception as e:
                logger.error(f"Failed to send ride completion notification to passenger: {str(e)}")

            # Clear active ride
            context.user_data.pop('active_ride', None)

            # Return to main menu
            main_menu(update, context)
            return MAIN_MENU
        else:
            update.message.reply_text(translations['status_update_failed'][language])

    elif user_input == translations['buttons']['cancel_ride'][language]:
        # Cancel the ride
        success, ride = RideService.cancel_ride(ride_id, telegram_id, "Cancelled by driver")

        if success:
            update.message.reply_text(
                translations['ride_cancelled'][language],
                reply_markup=ReplyKeyboardRemove()
            )

            # Clear active ride
            context.user_data.pop('active_ride', None)

            # Return to main menu
            main_menu(update, context)
            return MAIN_MENU
        else:
            update.message.reply_text(translations['cancel_failed'][language])

    elif user_input == translations['buttons']['sos'][language]:
        # Emergency SOS - automatically cancel the ride
        update.message.reply_text(
            translations['sos_activated'][language],
            reply_markup=ReplyKeyboardRemove()
        )

        # Cancel the ride due to emergency
        cancel_success, cancelled_ride = RideService.cancel_ride(ride_id, telegram_id, "Emergency - Driver activated SOS")

        if cancel_success:
            logger.warning(f"SOS activated by driver {telegram_id} - ride {ride_id} cancelled automatically")

            # Notify passenger about ride cancellation due to emergency
            try:
                passenger = cancelled_ride.passenger
                driver = cancelled_ride.driver

                # Get passenger's language preference
                passenger_language = passenger.user.language if hasattr(passenger.user, 'language') else 'kaz'

                # Create emergency cancellation notification message
                notification_message = translations['ride_cancelled_emergency'][passenger_language].format(
                    driver_name=driver.user.full_name,
                    phone=driver.user.phone_number
                )

                # Send notification to passenger
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

                try:
                    from bot_service.passenger.main import notify_passenger
                    notify_passenger(passenger.user.telegram_id, notification_message)
                except ImportError:
                    # Fallback: try to send notification directly
                    try:
                        from bot_service.passenger.main import updater as passenger_updater
                        passenger_updater.bot.send_message(
                            chat_id=passenger.user.telegram_id,
                            text=notification_message
                        )
                        logger.info(f"Sent emergency ride cancellation notification to passenger {passenger.user.telegram_id} (fallback method)")
                    except Exception as e2:
                        logger.error(f"Failed to send notification via fallback method: {str(e2)}")

                logger.info(f"Sent emergency ride cancellation notification to passenger {passenger.user.telegram_id}")

            except Exception as e:
                logger.error(f"Failed to send emergency ride cancellation notification to passenger: {str(e)}")
        else:
            logger.error(f"Failed to cancel ride {ride_id} after SOS activation by driver {telegram_id}")

        # TODO: Send emergency notification to admin
        logger.warning(f"SOS activated by driver {telegram_id} during ride {ride_id}")

        # Clear active ride so driver can return to normal operations
        context.user_data.pop('active_ride', None)

        # Return to main menu
        main_menu(update, context)
        return MAIN_MENU
    else:
        update.message.reply_text(translations['invalid_action'][language])

    return RIDE_MANAGEMENT




def auto_reject_ride(context):
    """Auto-reject ride after timeout - delete original message and reassign to another driver"""
    job_context = context.job.context
    chat_id = job_context['chat_id']
    ride_id = job_context['ride_id']
    language = job_context['language']
    message_id = job_context.get('message_id')

    try:
        # Delete original message if message_id is provided
        if message_id:
            try:
                context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=message_id
                )
                logger.info(f"Deleted original ride notification message {message_id} for driver {chat_id}")
            except Exception as e:
                logger.warning(f"Could not delete original message {message_id}: {str(e)}")

        # Send timeout message
        context.bot.send_message(
            chat_id=chat_id,
            text=translations['ride_timeout'][language]
        )

        # Reassign ride to another driver
        try:
            # Import the updated function from driver main
            from bot_service.driver.main import reassign_ride_to_next_driver
            reassign_ride_to_next_driver(ride_id, chat_id)
        except Exception as e:
            logger.error(f"Error reassigning ride {ride_id}: {str(e)}")

        logger.info(f"Auto-rejected ride {ride_id} for driver {chat_id}, reassigned to another driver")

    except Exception as e:
        logger.error(f"Error sending timeout message to {chat_id}: {str(e)}")


def delayed_ride_check(context):
    """Check for rides after a delay"""
    job_context = context.job.context
    update = job_context['update']
    context_obj = job_context['context']

    check_for_nearby_rides(update, context_obj)


def show_driver_statistics(update: Update, context: CallbackContext) -> None:
    """Show driver earnings and statistics"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        stats = DriverService.get_driver_earnings(telegram_id)

        if stats:
            message = translations['earnings_summary'][language].format(
                balance=stats['balance'],
                total_rides=stats['total_rides'],
                rating=stats['average_rating'],
                today_earnings=stats['today_earnings'],
                week_earnings=stats.get('week_earnings', 0),
                month_earnings=stats.get('month_earnings', 0)
            )
        else:
            message = translations['no_statistics'][language]

        update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error getting statistics for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])


def show_ride_history(update: Update, context: CallbackContext) -> None:
    """Show driver's ride history"""
    language = context.user_data.get('language', 'kaz')
    telegram_id = str(update.effective_user.id)

    try:
        from api.models import Driver

        user, _ = UserService.get_or_create_user(telegram_id)
        driver = user.driver_profile

        rides = driver.rides.all().order_by('-created_at')[:10]  # Last 10 rides

        if not rides:
            update.message.reply_text(translations['no_ride_history'][language])
            return

        history_text = translations['ride_history_header'][language] + "\n\n"

        for ride in rides:
            status_text = dict(ride.STATUS_CHOICES).get(ride.status, ride.status)
            history_text += f"🚗 {ride.pickup_address[:30]}... → {ride.destination_address[:30]}...\n"
            history_text += f"💰 {ride.final_cost or ride.estimated_cost} тенге\n"
            history_text += f"📅 {ride.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            history_text += f"📊 {status_text}\n\n"

        update.message.reply_text(history_text)

    except Exception as e:
        logger.error(f"Error getting ride history for driver {telegram_id}: {str(e)}")
        update.message.reply_text(translations['error_occurred'][language])
