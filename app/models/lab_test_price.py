from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy import text
from sqlalchemy.dialects.mysql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LabTestPrice(Base):
    __tablename__ = "lab_test_prices"
    __table_args__ = (
        UniqueConstraint("lab_id", "test_id", name="uq_lab_test"),
        Base.__table_args__,
    )

    lab_test_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.lab_id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_tests.test_id"))
    lab_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_available: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("1")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
