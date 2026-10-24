from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from labs.models import Equipment
from skillpass.models import UserCertification

from . import services
from .models import EquipmentLoan

INVENTORY = "/api/v1/inventory/"
LOANS = "/api/v1/inventory/loans/"


class InventoryTestCase(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.alice = User.objects.create_user("alice", first_name="Alice", last_name="Rao", password="unused-test-pw")
        self.bob = User.objects.create_user("bob", password="unused-test-pw")
        self.prof = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        self.client = self.api(self.alice)

    @staticmethod
    def api(user=None):
        client = APIClient()
        if user:
            client.force_authenticate(user)
        return client

    def item(self, equipment_id):
        return next(i for i in self.api().get(INVENTORY).json() if i["id"] == equipment_id)

    def borrow(self, equipment_id="EQ008", quantity=1, days=1, client=None):
        return (client or self.client).post(LOANS, {"equipmentId": equipment_id, "quantity": quantity,
                                                    "days": days}, format="json")

    def give_cert(self, user, cert_id, expires_at=None):
        UserCertification.objects.create(user=user, certification_id=cert_id, status="approved",
                                         approved_by=self.prof, expires_at=expires_at)


class InventoryListTests(InventoryTestCase):
    def test_public_list_with_stock(self):
        response = self.api().get(INVENTORY)
        self.assertEqual(response.status_code, 200)
        arduino = self.item("EQ008")
        self.assertEqual(
            {k: arduino[k] for k in ["name", "labId", "labName", "totalQuantity", "availableQuantity",
                                     "isLowStock", "isLoanable", "underMaintenance"]},
            {"name": "Arduino Uno Boards", "labId": "LAB001", "labName": "Robotics Lab", "totalQuantity": 25,
             "availableQuantity": 25, "isLowStock": False, "isLoanable": True, "underMaintenance": False},
        )
        self.assertEqual(self.item("EQ004")["requiredCertifications"], ["CERT-ELEC-BASIC"])

    def test_lab_only_and_maintenance_items(self):
        self.assertFalse(self.item("EQ002")["isLoanable"])          # Robotic Arm stays in the lab
        printer = self.item("EQ006")                                  # 3D printer seeded unavailable
        self.assertTrue(printer["underMaintenance"])
        self.assertEqual(printer["availableQuantity"], 0)
        self.assertFalse(printer["isLowStock"])

    def test_low_stock_flag(self):
        self.borrow("EQ001", quantity=10)
        self.borrow("EQ001", quantity=6, client=self.api(self.bob))
        kits = self.item("EQ001")                                     # 20 total, threshold 4
        self.assertEqual((kits["availableQuantity"], kits["isLowStock"]), (4, True))


class CheckoutTests(InventoryTestCase):
    def test_borrow_reduces_stock(self):
        response = self.borrow(quantity=3, days=7)
        self.assertEqual(response.status_code, 201)
        loan = response.json()
        self.assertEqual((loan["equipmentName"], loan["quantity"], loan["status"], loan["borrower"]),
                         ("Arduino Uno Boards", 3, "active", "Alice Rao"))
        due = timezone.datetime.fromisoformat(loan["dueAt"]) - timezone.datetime.fromisoformat(loan["checkedOutAt"])
        self.assertEqual(due, timedelta(days=7))
        self.assertEqual(self.item("EQ008")["availableQuantity"], 22)

    def test_cannot_borrow_more_than_available(self):
        self.borrow("EQ005", quantity=10)
        response = self.borrow("EQ005", quantity=6, client=self.api(self.bob))   # 15 total, 5 left
        self.assertEqual(response.status_code, 409)
        self.assertIn("Only 5", response.json()["detail"])
        self.assertEqual(self.borrow("EQ005", quantity=5, client=self.api(self.bob)).status_code, 201)
        self.assertEqual(self.item("EQ005")["availableQuantity"], 0)

    def test_lab_only_maintenance_and_unknown(self):
        self.assertEqual(self.borrow("EQ002").status_code, 400)
        self.assertIn("used in the lab", self.borrow("EQ002").json()["equipmentId"])
        Equipment.objects.filter(pk="EQ005").update(is_available=False)    # multimeters out for repair
        self.assertIn("maintenance", self.borrow("EQ005").json()["equipmentId"])
        self.assertEqual(self.borrow("NOPE").status_code, 404)

    def test_quantity_and_days_validation(self):
        for quantity, days in [(0, 1), (11, 1), ("2", 1), (True, 1), (1, 0), (1, 15), (1, "x")]:
            self.assertEqual(self.borrow(quantity=quantity, days=days).status_code, 400, (quantity, days))
        self.assertFalse(EquipmentLoan.objects.exists())

    def test_restricted_equipment_needs_certification_until_due(self):
        response = self.borrow("EQ004", days=3)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["missingCertifications"], ["CERT-ELEC-BASIC"])
        self.assertIn("Oscilloscope requires certification", response.json()["detail"])

        self.give_cert(self.alice, "CERT-ELEC-BASIC", expires_at=timezone.now() + timedelta(days=2))
        self.assertEqual(self.borrow("EQ004", days=3).status_code, 403)    # expires before it's due back
        self.assertEqual(self.borrow("EQ004", days=1).status_code, 201)

    def test_requires_sign_in(self):
        self.assertEqual(self.api().get(LOANS).status_code, 401)
        self.assertEqual(self.borrow(client=self.api()).status_code, 401)


class LoanListTests(InventoryTestCase):
    def test_users_see_only_their_loans(self):
        self.borrow()
        self.borrow("EQ009", client=self.api(self.bob))
        self.assertEqual([l["equipmentId"] for l in self.client.get(LOANS).json()], ["EQ008"])
        self.assertEqual([l["equipmentId"] for l in self.client.get(LOANS + "?scope=all").json()], ["EQ008"])

    def test_staff_see_everything_out_or_reported(self):
        self.borrow()
        bob_loan = self.borrow("EQ009", client=self.api(self.bob)).json()
        self.api(self.bob).post(f"{LOANS}{bob_loan['id']}/return/", {"condition": "ok"}, format="json")
        listed = self.api(self.prof).get(LOANS + "?scope=all").json()
        self.assertEqual([(l["username"], l["equipmentId"]) for l in listed], [("alice", "EQ008")])

    def test_overdue_flag(self):
        loan = EquipmentLoan.objects.create(equipment_id="EQ008", user=self.alice,
                                            checked_out_at=timezone.now() - timedelta(days=3),
                                            due_at=timezone.now() - timedelta(days=1))
        self.assertTrue(self.client.get(LOANS).json()[0]["isOverdue"])
        loan.due_at = timezone.now() + timedelta(days=1)
        loan.save()
        self.assertFalse(self.client.get(LOANS).json()[0]["isOverdue"])


class ReturnTests(InventoryTestCase):
    def return_loan(self, loan_id, client=None, **body):
        return (client or self.client).post(f"{LOANS}{loan_id}/return/", body or {"condition": "ok"}, format="json")

    def test_return_puts_units_back(self):
        loan = self.borrow(quantity=4).json()
        response = self.return_loan(loan["id"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["status"], response.json()["condition"]), ("returned", "ok"))
        self.assertEqual(self.item("EQ008")["availableQuantity"], 25)
        self.assertEqual(self.return_loan(loan["id"]).status_code, 400)  # already returned

    def test_damaged_report_keeps_units_out_until_resolved(self):
        loan = self.borrow(quantity=2).json()
        self.assertEqual(self.return_loan(loan["id"], condition="damaged").status_code, 400)  # note required
        response = self.return_loan(loan["id"], condition="damaged", note="Two pins bent")
        self.assertEqual(response.json()["status"], "reported")
        self.assertEqual(self.item("EQ008")["availableQuantity"], 23)

        services.resolve_report(EquipmentLoan.objects.get(pk=loan["id"]), self.prof)
        self.assertEqual(self.item("EQ008")["availableQuantity"], 25)

    def test_invalid_condition(self):
        loan = self.borrow().json()
        self.assertEqual(self.return_loan(loan["id"], condition="lost-in-space").status_code, 400)

    def test_only_borrower_or_staff_can_return(self):
        loan = self.borrow().json()
        self.assertEqual(self.return_loan(loan["id"], client=self.api(self.bob)).status_code, 404)
        self.assertEqual(self.return_loan(loan["id"], client=self.api(self.prof)).status_code, 200)
        self.assertEqual(EquipmentLoan.objects.get(pk=loan["id"]).returned_by, self.prof)

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError):
            EquipmentLoan.objects.create(equipment_id="EQ008", user=self.alice, quantity=0,
                                         due_at=timezone.now() + timedelta(days=1))
