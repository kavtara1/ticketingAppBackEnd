from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Department, Telephonegram, Ticket, TicketComment, TicketStatus, UserDepartment


TBILISI = "\u10d7\u10d1\u10d8\u10da\u10d8\u10e1\u10d8"
ADJARA = "\u10d0\u10ed\u10d0\u10e0\u10d0"


class TokenValidateAPITests(APITestCase):
    def test_validate_returns_payload_details_for_valid_access_token(self):
        user = User.objects.create_user(
            username="test123@gmail.com",
            email="test123@gmail.com",
            password="StrongPass123!",
        )
        token = str(AccessToken.for_user(user))

        response = self.client.post(
            reverse("auth-token-validate"),
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["userId"], str(user.id))
        self.assertEqual(response.data["tokenType"], "access")
        self.assertIn("expiresAt", response.data)


class CurrentUserAPITests(APITestCase):
    def test_auth_me_returns_current_user_and_department(self):
        user = User.objects.create_user(
            username="current@example.com",
            email="current@example.com",
            password="StrongPass123!",
            first_name="Current",
            last_name="User",
        )
        UserDepartment.objects.create(user=user, department=Department.TELEPHONEGRAM)
        self.client.force_authenticate(user)

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], user.id)
        self.assertEqual(response.data["firstName"], "Current")
        self.assertEqual(response.data["lastName"], "User")
        self.assertEqual(response.data["email"], "current@example.com")
        self.assertEqual(response.data["department"], Department.TELEPHONEGRAM)
        self.assertEqual(response.data["departmentName"], Department.TELEPHONEGRAM)


class TelephonegramAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="telephonegram@example.com",
            email="telephonegram@example.com",
            password="StrongPass123!",
        )
        UserDepartment.objects.create(user=self.user, department=Department.TELEPHONEGRAM)
        self.client.force_authenticate(self.user)

    def test_create_telephonegram_creates_base_ticket_and_routes_to_servicenet(self):
        response = self.client.post(
            reverse("telephonegrams-list"),
            {
                "telephonegramId": 1001,
                "region": TBILISI,
                "address": "Rustaveli Avenue 1",
                "roadSurface": "Asphalt",
                "responsiblePerson": "Nino Example",
                "contactPhone": "+995555000111",
                "time": "10:30",
                "sender": "City Hall",
                "sendTo": "Operations Team",
                "comment": "Urgent follow-up required",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["author"], "telephonegram@example.com")
        self.assertEqual(response.data["telephonegramId"], 1001)
        self.assertEqual(response.data["region"], TBILISI)
        self.assertEqual(response.data["originDepartment"], Department.TELEPHONEGRAM)
        self.assertEqual(response.data["assignedDepartment"], Department.SERVICENET)
        self.assertIn("telephonegramId", response.data)
        self.assertIn("ticketId", response.data)
        self.assertIn("createdDate", response.data)
        self.assertIn("lastUpdate", response.data)

        telephonegram = Telephonegram.objects.get(telephonegram_id=response.data["telephonegramId"])
        self.assertEqual(telephonegram.ticket.origin_department, Department.TELEPHONEGRAM)
        self.assertEqual(telephonegram.ticket.assigned_department, Department.SERVICENET)
        self.assertEqual(telephonegram.ticket.status, TicketStatus.OPEN)
        self.assertEqual(telephonegram.ticket.created_by, self.user)
        self.assertEqual(telephonegram.ticket.description, "Urgent follow-up required")

    def test_patch_telephonegram_updates_comment_and_ticket_timestamp_source(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: Old Address",
            description="Old comment",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        telephonegram = Telephonegram.objects.create(
            telephonegram_id=1002,
            ticket=ticket,
            region=TBILISI,
            address="Old Address",
            road_surface="Gravel",
            responsible_person="Old Person",
            contact_phone="+995555222333",
            time="09:00",
            sender="Sender",
            send_to="Receiver",
            comment="Old comment",
        )

        response = self.client.patch(
            reverse("telephonegrams-detail", kwargs={"ticket_id": ticket.id}),
            {
                "address": "Updated Address",
                "comment": "Updated comment",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        telephonegram.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(telephonegram.address, "Updated Address")
        self.assertEqual(telephonegram.comment, "Updated comment")
        self.assertEqual(ticket.title, "Telephonegram: Updated Address")
        self.assertEqual(ticket.description, "Updated comment")

    def test_get_telephonegram_by_ticket_id_includes_ticket_comments(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: Detail Target",
            description="Detail comment",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        telephonegram = Telephonegram.objects.create(
            telephonegram_id=1008,
            ticket=ticket,
            region=TBILISI,
            address="Detail Address",
            road_surface="Asphalt",
            responsible_person="Detail Person",
            contact_phone="+995555666666",
            time="13:00",
            sender="Detail Sender",
            send_to="Detail Receiver",
            comment="Telephonegram comment",
        )
        TicketComment.objects.create(
            ticket=ticket,
            comment="First ticket comment",
            created_by=self.user,
        )
        TicketComment.objects.create(
            ticket=ticket,
            comment="Second ticket comment",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("telephonegrams-detail", kwargs={"ticket_id": ticket.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["telephonegramId"], telephonegram.telephonegram_id)
        self.assertEqual(response.data["ticketId"], ticket.id)
        self.assertEqual(len(response.data["comments"]), 2)
        self.assertEqual(response.data["comments"][0]["comment"], "First ticket comment")
        self.assertEqual(response.data["comments"][1]["comment"], "Second ticket comment")

    def test_list_telephonegrams_can_be_filtered_by_department_and_region(self):
        first_ticket = Ticket.objects.create(
            title="Telephonegram: Tbilisi",
            description="First",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        second_ticket = Ticket.objects.create(
            title="Telephonegram: Adjara",
            description="Second",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        Telephonegram.objects.create(
            telephonegram_id=1003,
            ticket=first_ticket,
            region=TBILISI,
            address="Tbilisi Address",
            road_surface="Asphalt",
            responsible_person="Person One",
            contact_phone="+995555111111",
            time="08:00",
            sender="Sender One",
            send_to="Receiver One",
            comment="First comment",
        )
        Telephonegram.objects.create(
            telephonegram_id=1004,
            ticket=second_ticket,
            region=ADJARA,
            address="Adjara Address",
            road_surface="Concrete",
            responsible_person="Person Two",
            contact_phone="+995555222222",
            time="09:00",
            sender="Sender Two",
            send_to="Receiver Two",
            comment="Second comment",
        )

        response = self.client.get(
            reverse("telephonegrams-list"),
            {"department": Department.SERVICENET, "region": TBILISI},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["address"], "Tbilisi Address")
        self.assertEqual(response.data[0]["assignedDepartment"], Department.SERVICENET)

    def test_ticket_comments_can_be_added_without_updating_ticket_fields(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: Comment Target",
            description="Ticket description",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        Telephonegram.objects.create(
            telephonegram_id=1005,
            ticket=ticket,
            region=TBILISI,
            address="Comment Address",
            road_surface="Asphalt",
            responsible_person="Comment Person",
            contact_phone="+995555333333",
            time="11:00",
            sender="Sender",
            send_to="Receiver",
            comment="Original form comment",
        )

        response = self.client.post(
            reverse("ticket-comments", kwargs={"ticket_id": ticket.id}),
            {"comment": "New workflow comment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["ticketId"], ticket.id)
        self.assertEqual(response.data["comment"], "New workflow comment")
        self.assertEqual(response.data["author"], "telephonegram@example.com")

        ticket.refresh_from_db()
        self.assertEqual(ticket.title, "Telephonegram: Comment Target")
        self.assertEqual(ticket.description, "Ticket description")

        comment_entry = TicketComment.objects.get(ticket=ticket)
        self.assertEqual(comment_entry.comment, "New workflow comment")
        self.assertEqual(comment_entry.created_by, self.user)

    def test_ticket_comments_can_be_listed(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: History Target",
            description="History description",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
        )
        TicketComment.objects.create(
            ticket=ticket,
            comment="First comment",
            created_by=self.user,
        )
        TicketComment.objects.create(
            ticket=ticket,
            comment="Second comment",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("ticket-comments", kwargs={"ticket_id": ticket.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["comment"], "First comment")
        self.assertEqual(response.data[1]["comment"], "Second comment")

    def test_ticket_assignment_endpoint_can_send_ticket_back_to_origin_department(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: Return Target",
            description="Return description",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )

        response = self.client.patch(
            reverse("ticket-assignment-update", kwargs={"ticket_id": ticket.id}),
            {"assignedDepartment": Department.TELEPHONEGRAM},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_department, Department.TELEPHONEGRAM)
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(response.data["assignedDepartment"], Department.TELEPHONEGRAM)
        self.assertEqual(response.data["status"], TicketStatus.OPEN)

    def test_ticket_assignment_endpoint_can_send_ticket_to_servicenet(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: ServiceNet Target",
            description="Assignment description",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.TELEPHONEGRAM,
            status=TicketStatus.CLOSED,
        )

        response = self.client.patch(
            reverse("ticket-assignment-update", kwargs={"ticket_id": ticket.id}),
            {"assignedDepartment": Department.SERVICENET},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_department, Department.SERVICENET)
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(response.data["assignedDepartment"], Department.SERVICENET)
        self.assertEqual(response.data["status"], TicketStatus.OPEN)

    def test_ticket_can_be_closed_by_close_endpoint(self):
        ticket = Ticket.objects.create(
            title="Telephonegram: Close Target",
            description="Close description",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.TELEPHONEGRAM,
            status=TicketStatus.OPEN,
        )

        response = self.client.patch(
            reverse("ticket-close", kwargs={"ticket_id": ticket.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.CLOSED)
        self.assertEqual(response.data["status"], TicketStatus.CLOSED)

    def test_all_tickets_endpoint_filters_by_department(self):
        first_ticket = Ticket.objects.create(
            title="Department Match",
            description="Match",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        second_ticket = Ticket.objects.create(
            title="Department Miss",
            description="Miss",
            created_by=self.user,
            origin_department=Department.CCSUPPORTFIX,
            assigned_department=Department.CCSUPPORTFIX,
            status=TicketStatus.OPEN,
        )
        Telephonegram.objects.create(
            telephonegram_id=1006,
            ticket=first_ticket,
            region=TBILISI,
            address="Ticket Address",
            road_surface="Asphalt",
            responsible_person="Person One",
            contact_phone="+995555111111",
            time="08:00",
            sender="Sender One",
            send_to="Receiver One",
            comment="First comment",
        )
        response = self.client.get(
            reverse("tickets-list"),
            {"department": Department.SERVICENET},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], first_ticket.id)
        self.assertEqual(response.data[0]["region"], TBILISI)
        self.assertNotEqual(first_ticket.id, second_ticket.id)

    def test_all_tickets_endpoint_filters_by_status_for_department(self):
        open_ticket = Ticket.objects.create(
            title="Open Ticket",
            description="Open",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        Ticket.objects.create(
            title="Closed Ticket",
            description="Closed",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.CLOSED,
        )

        response = self.client.get(
            reverse("tickets-list"),
            {"department": Department.SERVICENET, "status": TicketStatus.OPEN},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], open_ticket.id)
        self.assertEqual(response.data[0]["status"], TicketStatus.OPEN)

    def test_assigned_tickets_endpoint_filters_by_status(self):
        open_ticket = Ticket.objects.create(
            title="Assigned Open Ticket",
            description="Open",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        closed_ticket = Ticket.objects.create(
            title="Assigned Closed Ticket",
            description="Closed",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.CLOSED,
        )
        Telephonegram.objects.create(
            telephonegram_id=1010,
            ticket=open_ticket,
            region=TBILISI,
            address="Assigned Open Address",
            road_surface="Asphalt",
            responsible_person="Open Responsible",
            contact_phone="+995555010010",
            time="10:00",
            sender="Open Sender",
            send_to="Open Receiver",
            comment="Open comment",
        )
        Telephonegram.objects.create(
            telephonegram_id=1011,
            ticket=closed_ticket,
            region=TBILISI,
            address="Assigned Closed Address",
            road_surface="Asphalt",
            responsible_person="Closed Responsible",
            contact_phone="+995555011011",
            time="11:00",
            sender="Closed Sender",
            send_to="Closed Receiver",
            comment="Closed comment",
        )

        response = self.client.get(
            reverse("tickets-assigned-list"),
            {"assignedDepartment": Department.SERVICENET, "status": TicketStatus.OPEN},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], open_ticket.id)
        self.assertEqual(response.data[0]["assignedDepartment"], Department.SERVICENET)

    def test_assigned_tickets_endpoint_returns_only_assigned_department_matches(self):
        assigned_ticket = Ticket.objects.create(
            title="Assigned Match",
            description="Assigned",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        Telephonegram.objects.create(
            telephonegram_id=1007,
            ticket=assigned_ticket,
            region=TBILISI,
            address="Assigned Address",
            road_surface="Asphalt",
            responsible_person="Assigned Person",
            contact_phone="+995555444444",
            time="12:00",
            sender="Assigned Sender",
            send_to="Assigned Receiver",
            comment="Assigned comment",
        )
        Ticket.objects.create(
            title="Origin Only Match",
            description="Origin",
            created_by=self.user,
            origin_department=Department.SERVICENET,
            assigned_department=Department.TELEPHONEGRAM,
            status=TicketStatus.OPEN,
        )

        response = self.client.get(
            reverse("tickets-assigned-list"),
            {"assignedDepartment": Department.SERVICENET},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], assigned_ticket.id)
        self.assertEqual(response.data[0]["telephonegramId"], 1007)
        self.assertEqual(response.data[0]["address"], "Assigned Address")
        self.assertEqual(response.data[0]["roadSurface"], "Asphalt")
        self.assertEqual(response.data[0]["responsiblePerson"], "Assigned Person")
        self.assertEqual(response.data[0]["contactPhone"], "+995555444444")
        self.assertEqual(response.data[0]["time"], "12:00")
        self.assertEqual(response.data[0]["sender"], "Assigned Sender")
        self.assertEqual(response.data[0]["sendTo"], "Assigned Receiver")
        self.assertEqual(response.data[0]["comment"], "Assigned comment")
        self.assertEqual(response.data[0]["assignedDepartment"], Department.SERVICENET)

    def test_region_tickets_endpoint_returns_only_matching_region(self):
        tbilisi_ticket = Ticket.objects.create(
            title="Region Match",
            description="Tbilisi",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        same_region_other_department_ticket = Ticket.objects.create(
            title="Region Same But Wrong Department",
            description="Tbilisi but not Servicenet",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.TELEPHONEGRAM,
            status=TicketStatus.OPEN,
        )
        other_ticket = Ticket.objects.create(
            title="Region Miss",
            description="Adjara",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        Telephonegram.objects.create(
            telephonegram_id=1009,
            ticket=tbilisi_ticket,
            region=TBILISI,
            address="Tbilisi Region Address",
            road_surface="Asphalt",
            responsible_person="Region Person",
            contact_phone="+995555777777",
            time="14:00",
            sender="Region Sender",
            send_to="Region Receiver",
            comment="Tbilisi comment",
        )
        Telephonegram.objects.create(
            telephonegram_id=1011,
            ticket=same_region_other_department_ticket,
            region=TBILISI,
            address="Same Region Other Department Address",
            road_surface="Paved",
            responsible_person="Other Department Person",
            contact_phone="+995555999999",
            time="14:30",
            sender="Other Department Sender",
            send_to="Other Department Receiver",
            comment="Should be filtered out",
        )
        Telephonegram.objects.create(
            telephonegram_id=1010,
            ticket=other_ticket,
            region=ADJARA,
            address="Adjara Region Address",
            road_surface="Concrete",
            responsible_person="Other Person",
            contact_phone="+995555888888",
            time="15:00",
            sender="Other Sender",
            send_to="Other Receiver",
            comment="Adjara comment",
        )

        response = self.client.get(
            reverse("tickets-region-list"),
            {"region": TBILISI},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], tbilisi_ticket.id)
        self.assertEqual(response.data[0]["region"], TBILISI)

    def test_region_tickets_endpoint_filters_by_status(self):
        open_ticket = Ticket.objects.create(
            title="Region Open Ticket",
            description="Open",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.OPEN,
        )
        closed_ticket = Ticket.objects.create(
            title="Region Closed Ticket",
            description="Closed",
            created_by=self.user,
            origin_department=Department.TELEPHONEGRAM,
            assigned_department=Department.SERVICENET,
            status=TicketStatus.CLOSED,
        )
        Telephonegram.objects.create(
            telephonegram_id=1012,
            ticket=open_ticket,
            region=TBILISI,
            address="Region Open Address",
            road_surface="Asphalt",
            responsible_person="Open Region Responsible",
            contact_phone="+995555012012",
            time="12:00",
            sender="Open Region Sender",
            send_to="Open Region Receiver",
            comment="Open region comment",
        )
        Telephonegram.objects.create(
            telephonegram_id=1013,
            ticket=closed_ticket,
            region=TBILISI,
            address="Region Closed Address",
            road_surface="Asphalt",
            responsible_person="Closed Region Responsible",
            contact_phone="+995555013013",
            time="13:00",
            sender="Closed Region Sender",
            send_to="Closed Region Receiver",
            comment="Closed region comment",
        )

        response = self.client.get(
            reverse("tickets-region-list"),
            {"region": TBILISI, "status": TicketStatus.OPEN},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticketId"], open_ticket.id)
