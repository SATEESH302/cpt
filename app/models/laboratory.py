from datetime import datetime

from sqlalchemy import BigInteger, FetchedValue, String, Text, text
from sqlalchemy.dialects.mysql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Laboratory(Base):
    __tablename__ = "laboratories"

    lab_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lab_name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    accreditation_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(
        ENUM("PENDING", "ACTIVE", "INACTIVE"), server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=FetchedValue(),
    )
