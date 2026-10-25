from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, text
from sqlalchemy.dialects.mysql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosticReport(Base):
    __tablename__ = "diagnostic_reports"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.booking_id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_tests.test_id"))
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.lab_id"))
    report_file_url: Mapped[str | None] = mapped_column(String(1000))
    report_status: Mapped[str | None] = mapped_column(
        ENUM("PENDING", "PROCESSING", "READY"), server_default=text("'PENDING'")
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
