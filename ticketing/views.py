from django.http import JsonResponse
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
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
    TicketCommentSerializer,
    TicketSerializer,
    TokenValidateSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from .models import Department, Telephonegram, Ticket, TicketStatus


STATUS_QUERY_PARAMETER = OpenApiParameter(
    name="status",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    enum=[value for value, _ in TicketStatus.choices],
    description="Optional ticket status filter.",
)


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
        serializer = self.get_serializer(telephonegram, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
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
        response_serializer = self.get_serializer(comment_entry)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TicketAssignmentUpdateAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketAssignmentSerializer
    lookup_url_kwarg = "ticket_id"

    def patch(self, request, ticket_id):
        ticket = get_object_or_404(Ticket.objects.all(), pk=ticket_id)
        serializer = self.get_serializer(ticket, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        serializer = self.get_serializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketCloseAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TicketSerializer
    lookup_url_kwarg = "ticket_id"

    @extend_schema(
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
        ticket.status = TicketStatus.CLOSED
        ticket.save(update_fields=["status", "updated_at"])
        response_serializer = self.get_serializer(ticket)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
