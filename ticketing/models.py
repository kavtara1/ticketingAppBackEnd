from django.conf import settings
from django.db import models


class Department(models.TextChoices):
    A = "A", "ccsupportfix"
    B = "B", "Telephonegram"
    C = "C", "Servicenet"


class TicketStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    RETURNED = "RETURNED", "Returned"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class TicketEventType(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    REVIEWED = "REVIEWED", "Reviewed"
    RETURNED = "RETURNED", "Returned"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    COMMENTED = "COMMENTED", "Commented"
    STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"


class Ticket(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tickets",
    )
    origin_department = models.CharField(max_length=1, choices=Department.choices)
    assigned_department = models.CharField(
        max_length=1,
        choices=Department.choices,
        default=Department.C,
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.title} ({self.status})"


class TicketHistory(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    event_type = models.CharField(max_length=20, choices=TicketEventType.choices)
    from_status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        null=True,
        blank=True,
    )
    to_status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        null=True,
        blank=True,
    )
    comment = models.TextField(blank=True)
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_history_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Ticket #{self.ticket_id} {self.event_type} at {self.created_at:%Y-%m-%d %H:%M:%S}"
