from django.conf import settings
from django.db import models


class Department(models.TextChoices):
    CCSUPPORTFIX = "ccsupportfix", "ccsupportfix"
    TELEPHONEGRAM = "Telephonegram", "Telephonegram"
    SERVICENET = "Servicenet", "Servicenet"


class Region(models.TextChoices):
    TBILISI = "თბილისი", "თბილისი"
    ADJARA = "აჭარა", "აჭარა"
    GURIA = "გურია", "გურია"
    IMERETI = "იმერეთი", "იმერეთი"
    KAKHETI = "კახეთი", "კახეთი"
    MTSKHETA_MTIANETI = "მცხეთა-მთიანეთი", "მცხეთა-მთიანეთი"
    RACHA_LECHKHUMI = "რაჭა-ლეჩხუმი", "რაჭა-ლეჩხუმი"
    SAMEGRELO_ZEMO_SVANETI = "სამეგრელო-ზემო სვანეთი", "სამეგრელო-ზემო სვანეთი"
    SAMTSKHE_JAVAKHETI = "სამცხე-ჯავახეთი", "სამცხე-ჯავახეთი"
    KVEMO_KARTLI = "ქვემო ქართლი", "ქვემო ქართლი"
    SHIDA_KARTLI = "შიდა ქართლი", "შიდა ქართლი"


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"


class UserDepartment(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="department_profile",
    )
    department = models.CharField(max_length=20, choices=Department.choices)
    must_change_password = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user.email or self.user.username} - {self.get_department_display()}"


class Ticket(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tickets",
    )
    origin_department = models.CharField(max_length=20, choices=Department.choices)
    assigned_department = models.CharField(
        max_length=20,
        choices=Department.choices,
        default=Department.SERVICENET,
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
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


class Telephonegram(models.Model):
    telephonegram_id = models.PositiveIntegerField()
    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.CASCADE,
        related_name="telephonegram",
    )
    region = models.CharField(max_length=50, choices=Region.choices)
    address = models.CharField(max_length=255)
    road_surface = models.CharField(max_length=255)
    responsible_person = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=50)
    time = models.CharField(max_length=100)
    sender = models.CharField(max_length=255)
    send_to = models.CharField(max_length=255)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-ticket__created_at"]

    def __str__(self) -> str:
        return f"Telephonegram #{self.telephonegram_id} for ticket #{self.ticket_id}"


class TicketComment(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment on ticket #{self.ticket_id} at {self.created_at:%Y-%m-%d %H:%M:%S}"
