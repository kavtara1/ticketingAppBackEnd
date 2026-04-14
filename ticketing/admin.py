from django.contrib import admin

from .models import Ticket, TicketHistory


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


@admin.register(TicketHistory)
class TicketHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "event_type",
        "from_status",
        "to_status",
        "acted_by",
        "created_at",
    )
    list_filter = ("event_type", "from_status", "to_status")
    search_fields = ("ticket__title", "ticket__id", "comment", "acted_by__username")
    readonly_fields = ("created_at",)
