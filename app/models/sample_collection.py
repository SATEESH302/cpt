from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.mysql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SampleCollection(Base):
    __tablename__ = "sample_collections"

    collection_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.booking_id"))
    collector_name: Mapped[str | None] = mapped_column(String(150))
    collector_phone: Mapped[str | None] = mapped_column(String(20))
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime)
    collected_time: Mapped[datetime | None] = mapped_column(DateTime)
    collection_status: Mapped[str | None] = mapped_column(
        ENUM("SCHEDULED", "ASSIGNED", "COLLECTED", "DELIVERED", "CANCELLED"),
        server_default=text("'SCHEDULED'"),
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
