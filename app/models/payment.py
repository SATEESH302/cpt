from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.mysql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.booking_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[str | None] = mapped_column(
        ENUM("UPI", "CARD", "CASH", "NET_BANKING")
    )
    payment_status: Mapped[str | None] = mapped_column(
        ENUM("PENDING", "SUCCESS", "FAILED", "REFUNDED"),
        server_default=text("'PENDING'"),
    )
    transaction_reference: Mapped[str | None] = mapped_column(
        String(255), unique=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
