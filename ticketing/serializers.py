from typing import Optional

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import (
    Department,
    Region,
    Telephonegram,
    Ticket,
    TicketComment,
    TicketStatus,
    UserDepartment,
)


class RegisterUserSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=150, required=True)
    lastName = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    department = serializers.ChoiceField(choices=[code for code, _ in Department.choices], required=True)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data["email"]
        user = User(
            username=email,
            email=email,
            first_name=validated_data["firstName"].strip(),
            last_name=validated_data["lastName"].strip(),
        )
        user.set_password(validated_data["password"])
        user.save()

        UserDepartment.objects.create(
            user=user,
            department=validated_data["department"],
        )
        return user


class UserListSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(source="first_name")
    lastName = serializers.CharField(source="last_name")
    department = serializers.SerializerMethodField()
    departmentName = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "firstName", "lastName", "email", "department", "departmentName")

    def get_department(self, obj) -> Optional[str]:
        profile = getattr(obj, "department_profile", None)
        return profile.department if profile else None

    def get_departmentName(self, obj) -> Optional[str]:
        profile = getattr(obj, "department_profile", None)
        return profile.get_department_display() if profile else None


class UserUpdateSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=150, required=False)
    lastName = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    department = serializers.ChoiceField(choices=[code for code, _ in Department.choices], required=False)

    def validate_email(self, value):
        email = value.strip().lower()
        user = self.instance
        qs = User.objects.filter(email__iexact=email)
        if user is not None:
            qs = qs.exclude(pk=user.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        if "firstName" in validated_data:
            instance.first_name = validated_data["firstName"].strip()
        if "lastName" in validated_data:
            instance.last_name = validated_data["lastName"].strip()
        if "email" in validated_data:
            email = validated_data["email"]
            instance.email = email
            instance.username = email
        if "password" in validated_data:
            instance.set_password(validated_data["password"])
        instance.save()

        if "department" in validated_data:
            UserDepartment.objects.update_or_create(
                user=instance,
                defaults={"department": validated_data["department"]},
            )
        return instance


class TokenValidateSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=False)


class ChangePasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField(required=True, write_only=True, trim_whitespace=False)
    newPassword = serializers.CharField(required=True, write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["oldPassword"]):
            raise serializers.ValidationError({"oldPassword": "Old password is incorrect."})
        validate_password(attrs["newPassword"], user=user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["newPassword"])
        user.save(update_fields=["password"])
        return user


class TicketCommentSerializer(serializers.ModelSerializer):
    commentId = serializers.IntegerField(source="id", read_only=True)
    ticketId = serializers.IntegerField(source="ticket.id", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    author = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = ("commentId", "ticketId", "comment", "author", "createdAt")

    def get_author(self, obj) -> Optional[str]:
        user = obj.created_by
        if user is None:
            return None
        return user.email or user.username

    def create(self, validated_data):
        return TicketComment.objects.create(
            ticket=self.context["ticket"],
            created_by=self.context["request"].user,
            comment=validated_data["comment"],
        )


class TelephonegramSerializer(serializers.ModelSerializer):
    telephonegramId = serializers.IntegerField(source="telephonegram_id")
    ticketId = serializers.IntegerField(source="ticket.id", read_only=True)
    roadSurface = serializers.CharField(source="road_surface")
    responsiblePerson = serializers.CharField(source="responsible_person")
    contactPhone = serializers.CharField(source="contact_phone")
    sendTo = serializers.CharField(source="send_to")
    createdDate = serializers.DateTimeField(source="ticket.created_at", read_only=True)
    lastUpdate = serializers.DateTimeField(source="ticket.updated_at", read_only=True)
    originDepartment = serializers.CharField(source="ticket.origin_department", read_only=True)
    assignedDepartment = serializers.CharField(source="ticket.assigned_department", read_only=True)
    author = serializers.SerializerMethodField()
    comments = TicketCommentSerializer(source="ticket.comments", many=True, read_only=True)
    region = serializers.ChoiceField(choices=Region.choices)

    class Meta:
        model = Telephonegram
        fields = (
            "telephonegramId",
            "ticketId",
            "region",
            "address",
            "roadSurface",
            "responsiblePerson",
            "contactPhone",
            "time",
            "sender",
            "sendTo",
            "comment",
            "author",
            "comments",
            "originDepartment",
            "assignedDepartment",
            "createdDate",
            "lastUpdate",
        )

    def get_author(self, obj) -> str:
        user = obj.ticket.created_by
        return user.email or user.username

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        ticket = Ticket.objects.create(
            title=f"Telephonegram: {validated_data['address']}",
            description=validated_data.get("comment", ""),
            created_by=request.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        return Telephonegram.objects.create(ticket=ticket, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        ticket = instance.ticket
        ticket.title = f"Telephonegram: {instance.address}"
        ticket.description = instance.comment
        ticket.save(update_fields=["title", "description", "updated_at"])
        return instance



class TicketSerializer(serializers.ModelSerializer):
    ticketId = serializers.IntegerField(source="id", read_only=True)
    originDepartment = serializers.CharField(source="origin_department", read_only=True)
    assignedDepartment = serializers.CharField(source="assigned_department", read_only=True)
    createdDate = serializers.DateTimeField(source="created_at", read_only=True)
    lastUpdate = serializers.DateTimeField(source="updated_at", read_only=True)
    author = serializers.SerializerMethodField()
    telephonegramId = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = (
            "ticketId",
            "title",
            "description",
            "status",
            "originDepartment",
            "assignedDepartment",
            "author",
            "telephonegramId",
            "region",
            "createdDate",
            "lastUpdate",
        )

    def get_author(self, obj) -> str:
        return obj.created_by.email or obj.created_by.username

    def get_telephonegramId(self, obj) -> Optional[int]:
        telephonegram = getattr(obj, "telephonegram", None)
        return telephonegram.telephonegram_id if telephonegram else None

    def get_region(self, obj) -> Optional[str]:
        telephonegram = getattr(obj, "telephonegram", None)
        return telephonegram.region if telephonegram else None


class TicketAssignmentSerializer(serializers.ModelSerializer):
    ticketId = serializers.IntegerField(source="id", read_only=True)
    originDepartment = serializers.CharField(source="origin_department", read_only=True)
    assignedDepartment = serializers.ChoiceField(
        source="assigned_department",
        choices=Department.choices,
    )

    class Meta:
        model = Ticket
        fields = ("ticketId", "originDepartment", "assignedDepartment", "status")

    def update(self, instance, validated_data):
        instance.assigned_department = validated_data["assigned_department"]
        instance.status = TicketStatus.OPEN
        instance.save(update_fields=["assigned_department", "status", "updated_at"])
        return instance
