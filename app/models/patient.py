from datetime import date, datetime

from sqlalchemy import BigInteger, Date, FetchedValue, String, Text, text
from sqlalchemy.dialects.mysql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Patient(Base):
    __tablename__ = "patients"

    credential: Mapped["PatientCredential | None"] = relationship(
        back_populates="patient", uselist=False
    )

    patient_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
    )
