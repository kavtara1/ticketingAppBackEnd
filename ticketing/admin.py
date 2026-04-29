from django.contrib import admin

from .models import Telephonegram, Ticket, TicketComment, UserDepartment


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "department", "created_at")
    list_filter = ("department",)
    search_fields = ("user__username", "user__email", "user__last_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "origin_department",
        "assigned_department",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "origin_department", "assigned_department")
    search_fields = ("title", "description", "created_by__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "created_by",
        "created_at",
    )
    search_fields = ("ticket__title", "ticket__id", "comment", "created_by__username")
    readonly_fields = ("created_at",)


@admin.register(Telephonegram)
class TelephonegramAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "region",
        "address",
        "responsible_person",
        "contact_phone",
    )
    list_filter = ("region",)
    search_fields = ("address", "sender", "send_to", "responsible_person", "contact_phone")
