from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, text
from sqlalchemy.dialects.mysql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Prescription(Base):
    __tablename__ = "prescriptions"

    prescription_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.patient_id"))
    doctor_name: Mapped[str | None] = mapped_column(String(150))
    prescription_file_url: Mapped[str | None] = mapped_column(String(1000))
    uploaded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
