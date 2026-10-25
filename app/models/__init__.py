"""Import every ORM mapping so migrations and verification see all tables."""

from app.models.booking import Booking
from app.models.booking_test import BookingTest
from app.models.diagnostic_report import DiagnosticReport
from app.models.diagnostic_test import DiagnosticTest
from app.models.lab_test_price import LabTestPrice
from app.models.laboratory import Laboratory
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.prescription import Prescription
from app.models.sample_collection import SampleCollection
from app.models.auth import AuthRateLimit, AuthSession, PatientCredential

__all__ = [
    "Booking", "BookingTest", "DiagnosticReport", "DiagnosticTest",
    "LabTestPrice", "Laboratory", "Patient", "Payment", "Prescription",
    "SampleCollection",
    "PatientCredential", "AuthSession", "AuthRateLimit",
]
