from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Passenger, Driver, Vehicle, DriverDocument,
    Ride, RideStatus, Rating, Admin, AppSettings
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'telegram_id', 'full_name', 'phone_number', 'language', 'is_active', 'created_at')
    list_filter = ('is_active', 'language', 'is_staff', 'is_superuser')
    search_fields = ('username', 'telegram_id', 'phone_number', 'full_name')
    ordering = ('-created_at',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Telegram Info', {'fields': ('telegram_id', 'phone_number', 'full_name', 'language')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_rides', 'balance', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__full_name', 'user__telegram_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'is_verified', 'is_online', 'total_rides', 'average_rating', 'balance')
    list_filter = ('status', 'is_verified', 'is_online', 'created_at')
    search_fields = ('user__full_name', 'user__telegram_id')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['verify_drivers', 'suspend_drivers']

    def verify_drivers(self, request, queryset):
        from .tasks import notify_driver_verified
        
        for driver in queryset:
            driver.status = 'verified'
            driver.is_verified = True
            driver.save()
            
            # Send notification to driver
            try:
                notify_driver_verified.delay(driver.user.telegram_id)
            except Exception as e:
                # Fallback if Celery is not available
                from .utils import send_driver_notification
                send_driver_notification(driver.user.telegram_id, 'driver_verified', {})
        
        self.message_user(request, f'{queryset.count()} drivers verified successfully.')

    verify_drivers.short_description = 'Verify selected drivers'

    def suspend_drivers(self, request, queryset):
        queryset.update(status='suspended', is_online=False)
        self.message_user(request, f'{queryset.count()} drivers suspended successfully.')

    suspend_drivers.short_description = 'Suspend selected drivers'


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('driver', 'make', 'model', 'year', 'color', 'license_plate')
    list_filter = ('make', 'year')
    search_fields = ('license_plate', 'driver__user__full_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ('driver', 'document_type', 'status', 'verified_at', 'created_at', 'image_preview')
    list_filter = ('document_type', 'status', 'created_at')
    search_fields = ('driver__user__full_name', 'document_number')
    readonly_fields = ('created_at', 'updated_at', 'image_preview')
    actions = ['approve_documents', 'reject_documents']
    
    fieldsets = (
        ('Document Info', {
            'fields': ('driver', 'document_type', 'document_number', 'status')
        }),
        ('Document Image', {
            'fields': ('document_image', 'image_preview')
        }),
        ('Verification', {
            'fields': ('verified_at', 'rejection_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def image_preview(self, obj):
        if obj.document_image:
            from django.utils.html import format_html
            return format_html(
                '<img src="{}" style="width: 100px; height: auto;" />',
                obj.document_image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'

    def approve_documents(self, request, queryset):
        from django.utils import timezone
        from .tasks import notify_driver_document_approved
        
        for document in queryset:
            document.status = 'approved'
            document.verified_at = timezone.now()
            document.save()
            
            # Send notification to driver
            try:
                notify_driver_document_approved.delay(document.driver.user.telegram_id, document.document_type)
            except Exception as e:
                # Fallback if Celery is not available
                from .utils import send_driver_notification
                send_driver_notification(document.driver.user.telegram_id, 'document_approved', {
                    'document_type': document.get_document_type_display()
                })
        
        self.message_user(request, f'{queryset.count()} documents approved successfully.')

    approve_documents.short_description = 'Approve selected documents'

    def reject_documents(self, request, queryset):
        from .tasks import notify_driver_document_rejected
        
        for document in queryset:
            document.status = 'rejected'
            document.save()
            
            # Send notification to driver
            try:
                notify_driver_document_rejected.delay(document.driver.user.telegram_id, document.document_type)
            except Exception as e:
                # Fallback if Celery is not available
                from .utils import send_driver_notification
                send_driver_notification(document.driver.user.telegram_id, 'document_rejected', {
                    'document_type': document.get_document_type_display()
                })
        
        self.message_user(request, f'{queryset.count()} documents rejected successfully.')

    reject_documents.short_description = 'Reject selected documents'


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger', 'driver', 'status', 'estimated_cost', 'final_cost', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('passenger__user__full_name', 'driver__user__full_name', 'pickup_address', 'destination_address')
    readonly_fields = ('id', 'created_at', 'accepted_at', 'started_at', 'completed_at', 'cancelled_at')

    fieldsets = (
        ('Ride Info', {
            'fields': ('id', 'passenger', 'driver', 'status')
        }),
        ('Pickup', {
            'fields': ('pickup_address', 'pickup_lat', 'pickup_lng')
        }),
        ('Destination', {
            'fields': ('destination_address', 'destination_lat', 'destination_lng')
        }),
        ('Cost', {
            'fields': ('estimated_cost', 'final_cost')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'accepted_at', 'started_at', 'completed_at', 'cancelled_at')
        }),
        ('Additional Info', {
            'fields': ('cancellation_reason', 'notes')
        }),
    )


@admin.register(RideStatus)
class RideStatusAdmin(admin.ModelAdmin):
    list_display = ('ride', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('ride__id',)
    readonly_fields = ('created_at',)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('ride', 'rated_by', 'rated_user', 'stars', 'created_at')
    list_filter = ('stars', 'created_at')
    search_fields = ('rated_by__full_name', 'rated_user__full_name')
    readonly_fields = ('created_at',)


@admin.register(Admin)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__full_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description', 'updated_at')
    list_filter = ('key', 'updated_at')
    search_fields = ('key', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Setting Info', {
            'fields': ('key', 'value', 'description')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of critical settings
        return False
