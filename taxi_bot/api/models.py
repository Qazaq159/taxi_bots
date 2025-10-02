from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


class User(AbstractUser):
    """Extended user model with Telegram integration"""
    telegram_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    language = models.CharField(
        max_length=10,
        choices=[('kaz', 'Kazakh'), ('rus', 'Russian')],
        default='kaz'
    )
    is_phone_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Override the ManyToMany fields to avoid reverse accessor clashes
    groups = models.ManyToManyField(
        Group,
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='api_user_set',
        related_query_name='api_user',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='api_user_set',
        related_query_name='api_user',
    )

    def __str__(self):
        return f"{self.full_name or self.username} ({self.telegram_id})"

    class Meta:
        db_table = 'users'


class Passenger(models.Model):
    """Passenger profile for ride requests"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='passenger_profile')
    current_address = models.TextField(blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_rides = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Passenger: {self.user.full_name}"

    class Meta:
        db_table = 'passengers'


class Driver(models.Model):
    """Driver profile for accepting rides"""
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_verified = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    current_lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    current_lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_rides = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0.00), MaxValueValidator(5.00)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Driver: {self.user.full_name} ({self.status})"

    class Meta:
        db_table = 'drivers'


class Vehicle(models.Model):
    """Vehicle information for drivers"""
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name='vehicle')
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2030)]
    )
    color = models.CharField(max_length=50)
    license_plate = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.make} {self.model} ({self.license_plate})"

    class Meta:
        db_table = 'vehicles'


class DriverDocument(models.Model):
    """Driver verification documents"""
    DOCUMENT_TYPES = [
        ('license', 'Driver License'),
        ('passport', 'Passport'),
        ('vehicle_registration', 'Vehicle Registration'),
        ('insurance', 'Insurance'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_number = models.CharField(max_length=100)
    document_image = models.ImageField(upload_to='driver_documents/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.driver.user.full_name} - {self.get_document_type_display()}"

    class Meta:
        db_table = 'driver_documents'
        unique_together = ['driver', 'document_type']


class Ride(models.Model):
    """Central ride booking entity"""
    STATUS_CHOICES = [
        ('requested', 'Ride Requested'),
        ('assigned', 'Driver Assigned'),
        ('driver_enroute', 'Driver En Route'),
        ('driver_arrived', 'Driver Arrived'),
        ('in_progress', 'Ride In Progress'),
        ('completed', 'Completed'),
        ('cancelled_by_passenger', 'Cancelled by Passenger'),
        ('cancelled_by_driver', 'Cancelled by Driver'),
        ('cancelled_by_system', 'Cancelled by System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    passenger = models.ForeignKey(Passenger, on_delete=models.CASCADE, related_name='rides')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='rides')

    # Pickup information
    pickup_address = models.TextField()
    pickup_lat = models.DecimalField(max_digits=10, decimal_places=8)
    pickup_lng = models.DecimalField(max_digits=11, decimal_places=8)

    # Destination information
    destination_address = models.TextField()
    destination_lat = models.DecimalField(max_digits=10, decimal_places=8)
    destination_lng = models.DecimalField(max_digits=11, decimal_places=8)

    # Cost information
    estimated_cost = models.DecimalField(max_digits=8, decimal_places=2)
    final_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fare_boosts = models.PositiveIntegerField(default=0)  # Number of times fare was boosted
    current_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # Current cost after boosts

    # Status and timing
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Additional information
    cancellation_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Ride {self.id} - {self.passenger.user.full_name} ({self.status})"

    @property
    def duration_minutes(self):
        """Calculate ride duration in minutes"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() / 60)
        return None

    def update_status(self, new_status, notes=''):
        """Update ride status with automatic timestamp setting"""
        self.status = new_status
        now = timezone.now()

        if new_status == 'assigned' and not self.accepted_at:
            self.accepted_at = now
        elif new_status == 'in_progress' and not self.started_at:
            self.started_at = now
        elif new_status == 'completed' and not self.completed_at:
            self.completed_at = now
        elif 'cancelled' in new_status and not self.cancelled_at:
            self.cancelled_at = now
            self.cancellation_reason = notes

        self.save()

        # Create status history record
        RideStatus.objects.create(
            ride=self,
            status=new_status,
            notes=notes
        )

    def boost_fare(self):
        """Boost the fare by the configured amount"""
        from api.models import AppSettings
        
        max_boosts = AppSettings.get_max_fare_boosts()
        boost_amount = AppSettings.get_fare_boost_amount()
        
        if self.fare_boosts >= max_boosts:
            return False, f"Maximum {max_boosts} fare boosts already applied"
        
        if self.status != 'requested':
            return False, "Can only boost fare for pending rides"
        
        # Calculate new cost
        current_cost = self.current_cost or self.estimated_cost
        new_cost = current_cost + boost_amount
        
        # Update ride
        self.fare_boosts += 1
        self.current_cost = new_cost
        self.save()
        
        return True, f"Fare boosted by {boost_amount} tenge. New cost: {new_cost} tenge"

    @property
    def display_cost(self):
        """Get the cost to display to users (current cost or estimated cost)"""
        return self.current_cost or self.estimated_cost

    class Meta:
        db_table = 'rides'
        ordering = ['-created_at']


class RideStatus(models.Model):
    """Historical tracking of ride status changes"""
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=30)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ride {self.ride.id} - {self.status}"

    class Meta:
        db_table = 'ride_statuses'
        ordering = ['-created_at']


class Rating(models.Model):
    """Bidirectional rating system"""
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='ratings')
    rated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    rated_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_received')
    stars = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rated_by.full_name} rated {self.rated_user.full_name}: {self.stars} stars"

    class Meta:
        db_table = 'ratings'
        unique_together = ['ride', 'rated_by', 'rated_user']
        ordering = ['-created_at']


class Admin(models.Model):
    """Admin user profile for dashboard access"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    permissions = models.JSONField(default=list)  # Store admin permissions
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Admin: {self.user.full_name}"

    class Meta:
        db_table = 'admins'


class AppSettings(models.Model):
    """Application settings for configurable values"""
    SETTING_CHOICES = [
        ('default_ride_cost', 'Default Ride Cost (Tenge)'),
        ('fare_boost_amount', 'Fare Boost Amount (Tenge)'),
        ('max_fare_boosts', 'Maximum Fare Boosts Allowed'),
    ]
    
    key = models.CharField(max_length=50, choices=SETTING_CHOICES, unique=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_key_display()}: {self.value}"

    @classmethod
    def get_default_ride_cost(cls):
        """Get the default ride cost"""
        try:
            setting = cls.objects.get(key='default_ride_cost')
            return setting.value
        except cls.DoesNotExist:
            # Create default setting if it doesn't exist
            setting = cls.objects.create(
                key='default_ride_cost',
                value=400.00,
                description='Default cost for all rides in tenge'
            )
            return setting.value

    @classmethod
    def get_fare_boost_amount(cls):
        """Get the fare boost amount"""
        try:
            setting = cls.objects.get(key='fare_boost_amount')
            return setting.value
        except cls.DoesNotExist:
            setting = cls.objects.create(
                key='fare_boost_amount',
                value=100.00,
                description='Amount to add when passenger boosts fare'
            )
            return setting.value

    @classmethod
    def get_max_fare_boosts(cls):
        """Get the maximum number of fare boosts allowed"""
        try:
            setting = cls.objects.get(key='max_fare_boosts')
            return int(setting.value)
        except cls.DoesNotExist:
            setting = cls.objects.create(
                key='max_fare_boosts',
                value=3,
                description='Maximum number of times passenger can boost fare'
            )
            return int(setting.value)

    class Meta:
        db_table = 'app_settings'
        verbose_name = 'App Setting'
        verbose_name_plural = 'App Settings'


# Signal handlers for real-time notifications
@receiver(post_save, sender=Ride)
def notify_drivers_on_ride_creation(sender, instance, created, **kwargs):
    """Send notifications to nearby drivers when a new ride is created"""
    if created and instance.status == 'requested':
        import logging
        logger = logging.getLogger(__name__)
        
        # Import here to avoid circular imports
        from api.services import DriverService, PassengerService

        # Find available online drivers (now ignores location/radius)
        available_drivers = PassengerService.get_nearby_rides_for_new_ride(instance)
        
        # Debug logging
        online_verified_count = Driver.objects.filter(is_online=True, is_verified=True).count()
        logger.info(f"Ride {instance.id} created - Found {len(available_drivers)} available drivers out of {online_verified_count} online verified drivers")

        if available_drivers:
            # Found online drivers - send normal notifications
            try:
                # Use Celery task for async notification
                from api.tasks import notify_drivers_about_new_ride
                notify_drivers_about_new_ride.delay(instance.id)
                logger.info(f"Scheduled notifications for {len(available_drivers)} drivers for ride {instance.id}")

            except ImportError:
                # Fallback: log the notification need
                logger.warning(f"Celery not available - ride {instance.id} needs driver notification")
                print(f"New ride {instance.id} needs driver notification")
        else:
            # No online drivers available - notify passenger and offline drivers
            logger.info(f"No online drivers available for ride {instance.id} - triggering no drivers flow")
            try:
                from api.tasks import handle_no_drivers_available
                handle_no_drivers_available.delay(instance.id)
            except ImportError:
                logger.warning(f"Celery not available - no drivers available for ride {instance.id}")
                print(f"No drivers available for ride {instance.id}")


@receiver(post_save, sender=Ride)
def notify_passenger_on_driver_assignment(sender, instance, **kwargs):
    """Notify passenger when driver is assigned"""
    if instance.status == 'assigned' and instance.driver:
        try:
            # Use Celery task for async notification
            from api.tasks import notify_passenger_driver_assigned
            notify_passenger_driver_assigned.delay(instance.id)

        except ImportError:
            print(f"Could not notify passenger {instance.passenger.user.telegram_id} about driver assignment")


@receiver(post_save, sender=DriverDocument)
def check_driver_verification_status(sender, instance, **kwargs):
    """Check if driver should be automatically verified when documents are approved"""
    if instance.status == 'approved':
        driver = instance.driver
        
        # Check if all required documents are approved
        required_docs = ['license', 'vehicle_registration']
        approved_docs = driver.documents.filter(
            document_type__in=required_docs,
            status='approved'
        ).values_list('document_type', flat=True)
        
        # If all required documents are approved, verify the driver
        if set(approved_docs) == set(required_docs):
            if driver.status == 'pending':
                driver.status = 'verified'
                driver.is_verified = True
                driver.save()
                
                # Send verification notification
                try:
                    from api.tasks import notify_driver_verified
                    notify_driver_verified.delay(driver.user.telegram_id)
                except ImportError:
                    from api.utils import send_driver_notification
                    send_driver_notification(driver.user.telegram_id, 'driver_verified', {})
