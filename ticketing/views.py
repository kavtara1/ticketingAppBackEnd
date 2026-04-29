from datetime import datetime, time
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    ChangePasswordSerializer,
    RegisterUserSerializer,
    TelephonegramSerializer,
    TicketAssignmentSerializer,
    TicketAuditLogSerializer,
    TicketCommentSerializer,
    TicketSerializer,
    TokenValidateSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from .models import AuditAction, Department, Telephonegram, Ticket, TicketAuditLog, TicketStatus
from .reporting import build_xlsx


STATUS_QUERY_PARAMETER = OpenApiParameter(
    name="status",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    enum=[value for value, _ in TicketStatus.choices],
    description="Optional ticket status filter.",
)
DATE_FROM_QUERY_PARAMETER = OpenApiParameter(
    name="dateFrom",
    type=OpenApiTypes.DATE,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional start date filter in YYYY-MM-DD format.",
)
DATE_TO_QUERY_PARAMETER = OpenApiParameter(
    name="dateTo",
    type=OpenApiTypes.DATE,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional end date filter in YYYY-MM-DD format.",
)
TICKET_ID_QUERY_PARAMETER = OpenApiParameter(
    name="ticketId",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional ticket ID filter.",
)

TELEPHONEGRAM_AUDIT_FIELDS = {
    "telephonegram_id": "telephonegramId",
    "region": "region",
    "address": "address",
    "road_surface": "roadSurface",
    "responsible_person": "responsiblePerson",
    "contact_phone": "contactPhone",
    "time": "time",
    "sender": "sender",
    "send_to": "sendTo",
    "comment": "comment",
}


def _create_audit_log(ticket, action, performed_by, old_value="", new_value="", details=""):
    TicketAuditLog.objects.create(
        ticket=ticket,
        action=action,
        performed_by=performed_by,
        old_value=old_value,
        new_value=new_value,
        details=details,
    )


def _telephonegram_snapshot(telephonegram):
    return {field: getattr(telephonegram, field) for field in TELEPHONEGRAM_AUDIT_FIELDS}


def _parse_date_range(request):
    date_from_param = request.query_params.get("dateFrom")
    date_to_param = request.query_params.get("dateTo")

    start = None
    end = None

    if date_from_param:
        parsed = parse_datetime(date_from_param)
        if parsed is not None:
            start = parsed
        else:
            parsed_date = parse_date(date_from_param)
            if parsed_date is None:
                return None, None, Response(
                    {"detail": "dateFrom must be a valid ISO date or datetime."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            start = datetime.combine(parsed_date, time.min)

    if date_to_param:
        parsed = parse_datetime(date_to_param)
        if parsed is not None:
            end = parsed
        else:
            parsed_date = parse_date(date_to_param)
            if parsed_date is None:
                return None, None, Response(
                    {"detail": "dateTo must be a valid ISO date or datetime."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            end = datetime.combine(parsed_date, time.max)

    if start is not None and timezone.is_naive(start):
        start = timezone.make_aware(start, timezone.get_current_timezone())
    if end is not None and timezone.is_naive(end):
        end = timezone.make_aware(end, timezone.get_current_timezone())
    if start is not None and end is not None and start > end:
        return None, None, Response(
            {"detail": "dateFrom must be less than or equal to dateTo."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return start, end, None


def health(request):
    return JsonResponse({"app": "ticketing", "status": "ok"})


class LoginAPIView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]


class TokenRefreshAPIView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


class RegisterUserAPIView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterUserSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile = user.department_profile
        return Response(
            {
                "id": user.id,
                "firstName": user.first_name,
                "lastName": user.last_name,
                "email": user.email,
                "department": profile.department,
                "departmentName": profile.get_department_display(),
            },
            status=status.HTTP_201_CREATED,
        )


class CurrentUserAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserListSerializer

    def get(self, request):
        serializer = UserListSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserListAPIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserListSerializer
    queryset = User.objects.all().select_related("department_profile").order_by("id")


class UserDetailAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserUpdateSerializer
    queryset = User.objects.all().select_related("department_profile")
    lookup_url_kwarg = "user_id"

    def get(self, request, user_id):
        user = get_object_or_404(self.get_queryset(), pk=user_id)
        serializer = UserListSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, user_id):
        return self._update(request, user_id, partial=True)

    def put(self, request, user_id):
        return self._update(request, user_id, partial=False)

    def delete(self, request, user_id):
        user = get_object_or_404(self.get_queryset(), pk=user_id)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _update(self, request, user_id, partial):
        user = get_object_or_404(self.get_queryset(), pk=user_id)
        serializer = self.get_serializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated_user = serializer.save()
        response_serializer = UserListSerializer(updated_user)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class TokenValidateAPIView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = TokenValidateSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data.get("token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            return Response(
                {"valid": False, "detail": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validated_token = UntypedToken(token)
            payload = validated_token.payload
        except (InvalidToken, TokenError):
            return Response(
                {"valid": False, "detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "valid": True,
                "userId": payload.get("user_id"),
                "tokenType": payload.get("token_type"),
                "expiresAt": payload.get("exp"),
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(parameters=[STATUS_QUERY_PARAMETER])
)
class TelephonegramListCreateAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TelephonegramSerializer
    queryset = Telephonegram.objects.select_related("ticket__created_by").all()

    def get_queryset(self):
        queryset = self.queryset
        department = self.request.query_params.get("department")
        region = self.request.query_params.get("region")
        status_param = self.request.query_params.get("status")

        if department:
            valid_departments = {value for value, _ in Department.choices}
            if department not in valid_departments:
                return queryset.none()
            queryset = queryset.filter(
                ticket__assigned_department=department,
            ) | queryset.filter(
                ticket__origin_department=department,
            )

        if region:
            queryset = queryset.filter(region=region)

        if status_param:
            valid_statuses = {value for value, _ in TicketStatus.choices}
            if status_param not in valid_statuses:
                return queryset.none()
            queryset = queryset.filter(ticket__status=status_param)

        return queryset.distinct()

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        telephonegram = serializer.save()
        TicketAuditLog.objects.create(
            ticket=telephonegram.ticket,
            action=AuditAction.CREATED,
            performed_by=request.user,
            details="Telephonegram ticket created.",
        )
        response_serializer = self.get_serializer(telephonegram)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TelephonegramDetailAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TelephonegramSerializer
    queryset = Telephonegram.objects.select_related("ticket__created_by").all()
    lookup_url_kwarg = "ticket_id"

    def get_object(self):
        return get_object_or_404(self.get_queryset(), ticket_id=self.kwargs["ticket_id"])

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="ticket_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="Ticket ID linked to the Telephonegram record.",
            )
        ]
    )
    def get(self, request, ticket_id):
        telephonegram = self.get_object()
        serializer = self.get_serializer(telephonegram)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="ticket_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="Ticket ID linked to the Telephonegram record.",
            )
        ]
    )
    def patch(self, request, ticket_id):
        telephonegram = self.get_object()
        before = _telephonegram_snapshot(telephonegram)
        serializer = self.get_serializer(telephonegram, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        after = _telephonegram_snapshot(updated)
        for field_name, label in TELEPHONEGRAM_AUDIT_FIELDS.items():
            if before[field_name] != after[field_name]:
                _create_audit_log(
                    ticket=updated.ticket,
                    action=AuditAction.FIELD_UPDATED,
                    performed_by=request.user,
                    old_value=before[field_name],
                    new_value=after[field_name],
                    details=f"{label} updated.",
                )
        response_serializer = self.get_serializer(updated)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="ticket_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="Ticket ID linked to the Telephonegram record.",
            )
        ]
    )
    def delete(self, request, ticket_id):
        telephonegram = self.get_object()
        telephonegram.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(parameters=[STATUS_QUERY_PARAMETER])
)
class TicketListAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketSerializer
    queryset = Ticket.objects.select_related("created_by", "telephonegram").all()

    def get_queryset(self):
        queryset = self.queryset
        department = self.request.query_params.get("department")
        status_param = self.request.query_params.get("status")

        if department:
            valid_departments = {value for value, _ in Department.choices}
            if department not in valid_departments:
                return queryset.none()
            queryset = queryset.filter(assigned_department=department) | queryset.filter(origin_department=department)

        if status_param:
            valid_statuses = {value for value, _ in TicketStatus.choices}
            if status_param not in valid_statuses:
                return queryset.none()
            queryset = queryset.filter(status=status_param)

        return queryset.distinct()

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                name="assignedDepartment",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=[value for value, _ in Department.choices],
                description="Return only tickets assigned to this department.",
            ),
            STATUS_QUERY_PARAMETER,
        ]
    )
)
class AssignedDepartmentTicketListAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TelephonegramSerializer
    queryset = Telephonegram.objects.select_related("ticket__created_by").all()

    def get_queryset(self):
        department = self.request.query_params.get("assignedDepartment")
        status_param = self.request.query_params.get("status")
        if not department:
            return self.queryset.none()

        valid_departments = {value for value, _ in Department.choices}
        if department not in valid_departments:
            return self.queryset.none()

        queryset = self.queryset.filter(ticket__assigned_department=department)
        if status_param:
            valid_statuses = {value for value, _ in TicketStatus.choices}
            if status_param not in valid_statuses:
                return self.queryset.none()
            queryset = queryset.filter(ticket__status=status_param)
        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                name="region",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=[value for value, _ in Telephonegram._meta.get_field("region").choices],
                description="Return only tickets in this region.",
            ),
            STATUS_QUERY_PARAMETER,
        ]
    )
)
class RegionTicketListAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TelephonegramSerializer
    queryset = Telephonegram.objects.select_related("ticket__created_by").all()

    def get_queryset(self):
        region = self.request.query_params.get("region")
        status_param = self.request.query_params.get("status")
        if not region:
            return self.queryset.none()

        valid_regions = {value for value, _ in Telephonegram._meta.get_field("region").choices}
        if region not in valid_regions:
            return self.queryset.none()

        queryset = self.queryset.filter(
            region=region,
            ticket__assigned_department=Department.SERVICENET,
        )
        if status_param:
            valid_statuses = {value for value, _ in TicketStatus.choices}
            if status_param not in valid_statuses:
                return self.queryset.none()
            queryset = queryset.filter(ticket__status=status_param)
        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketCommentListCreateAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketCommentSerializer
    lookup_url_kwarg = "ticket_id"

    def get_ticket(self):
        return get_object_or_404(Ticket.objects.all(), pk=self.kwargs["ticket_id"])

    def get(self, request, ticket_id):
        ticket = self.get_ticket()
        comments = ticket.comments.select_related("created_by")
        serializer = self.get_serializer(comments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, ticket_id):
        ticket = self.get_ticket()
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "ticket": ticket},
        )
        serializer.is_valid(raise_exception=True)
        comment_entry = serializer.save()
        _create_audit_log(
            ticket=ticket,
            action=AuditAction.COMMENT_ADDED,
            performed_by=request.user,
            new_value=comment_entry.comment,
            details="Comment added.",
        )
        response_serializer = self.get_serializer(comment_entry)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TicketAssignmentUpdateAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketAssignmentSerializer
    lookup_url_kwarg = "ticket_id"

    def patch(self, request, ticket_id):
        ticket = get_object_or_404(Ticket.objects.all(), pk=ticket_id)
        previous_department = ticket.assigned_department
        previous_status = ticket.status
        serializer = self.get_serializer(ticket, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        if previous_department != ticket.assigned_department:
            _create_audit_log(
                ticket=ticket,
                action=AuditAction.DEPARTMENT_CHANGED,
                performed_by=request.user,
                old_value=previous_department,
                new_value=ticket.assigned_department,
                details="Assigned department changed.",
            )
        if previous_status != ticket.status:
            _create_audit_log(
                ticket=ticket,
                action=AuditAction.STATUS_CHANGED,
                performed_by=request.user,
                old_value=previous_status,
                new_value=ticket.status,
                details="Status changed during reassignment.",
            )
        serializer = self.get_serializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketCloseAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketSerializer
    lookup_url_kwarg = "ticket_id"

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                name="ticket_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="Ticket ID to close.",
            )
        ]
    )
    def patch(self, request, ticket_id):
        ticket = get_object_or_404(Ticket.objects.all(), pk=ticket_id)
        previous_status = ticket.status
        ticket.status = TicketStatus.CLOSED
        ticket.finalized_at = timezone.now()
        ticket.save(update_fields=["status", "finalized_at", "updated_at"])
        if previous_status != ticket.status:
            _create_audit_log(
                ticket=ticket,
                action=AuditAction.CLOSED,
                performed_by=request.user,
                old_value=previous_status,
                new_value=ticket.status,
                details="Ticket closed.",
            )
        response_serializer = self.get_serializer(ticket)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            TICKET_ID_QUERY_PARAMETER,
            DATE_FROM_QUERY_PARAMETER,
            DATE_TO_QUERY_PARAMETER,
        ]
    )
)
class TicketAuditLogListAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketAuditLogSerializer
    queryset = TicketAuditLog.objects.select_related("ticket", "performed_by").all()

    def get_queryset(self):
        queryset = self.queryset
        ticket_id = self.request.query_params.get("ticketId")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)

        start, end, error_response = _parse_date_range(self.request)
        self._date_range_error = error_response
        if error_response is not None:
            return queryset.none()
        if start is not None:
            queryset = queryset.filter(timestamp__gte=start)
        if end is not None:
            queryset = queryset.filter(timestamp__lte=end)
        return queryset

    def get(self, request):
        self._date_range_error = None
        queryset = self.get_queryset()
        if self._date_range_error is not None:
            return self._date_range_error
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            TICKET_ID_QUERY_PARAMETER,
            DATE_FROM_QUERY_PARAMETER,
            DATE_TO_QUERY_PARAMETER,
        ]
    )
)
class TicketAuditLogExportAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketAuditLogSerializer
    queryset = TicketAuditLog.objects.select_related("ticket", "performed_by").all()

    def get_queryset(self):
        queryset = self.queryset
        ticket_id = self.request.query_params.get("ticketId")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)

        start, end, error_response = _parse_date_range(self.request)
        self._date_range_error = error_response
        if error_response is not None:
            return queryset.none()
        if start is not None:
            queryset = queryset.filter(timestamp__gte=start)
        if end is not None:
            queryset = queryset.filter(timestamp__lte=end)
        return queryset

    @extend_schema(request=None, responses={200: OpenApiTypes.BINARY})
    def get(self, request):
        self._date_range_error = None
        audit_logs = self.get_queryset()
        if self._date_range_error is not None:
            return self._date_range_error

        headers = [
            "Ticket ID",
            "Ticket Title",
            "Action",
            "Performed By",
            "Old Value",
            "New Value",
            "Details",
            "Timestamp",
        ]
        rows = [
            [
                entry.ticket_id,
                entry.ticket.title,
                entry.action,
                entry.performed_by.email if entry.performed_by else "",
                entry.old_value,
                entry.new_value,
                entry.details,
                timezone.localtime(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for entry in audit_logs
        ]

        workbook = build_xlsx(headers, rows)
        response = HttpResponse(
            workbook,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        filename = f"ticket-audit-report-{timezone.localdate().isoformat()}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
