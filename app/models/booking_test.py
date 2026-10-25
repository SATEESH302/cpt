from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BookingTest(Base):
    __tablename__ = "booking_tests"
    __table_args__ = (
        UniqueConstraint("booking_id", "test_id", name="uq_booking_test"),
        Base.__table_args__,
    )

    booking_test_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.booking_id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_tests.test_id"))
    price_at_booking: Mapped[Decimal] = mapped_column(Numeric(10, 2))
