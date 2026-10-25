from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, text
from sqlalchemy.dialects.mysql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.patient_id"))
    lab_id: Mapped[int | None] = mapped_column(ForeignKey("laboratories.lab_id"))
    prescription_id: Mapped[int | None] = mapped_column(
        ForeignKey("prescriptions.prescription_id")
    )
    booking_date: Mapped[datetime] = mapped_column(DateTime)
    collection_type: Mapped[str] = mapped_column(ENUM("HOME", "LAB"))
    booking_status: Mapped[str | None] = mapped_column(
        ENUM("PENDING", "CONFIRMED", "SAMPLE_COLLECTED", "COMPLETED", "CANCELLED"),
        server_default=text("'PENDING'"),
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
