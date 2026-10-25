from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Numeric, String, Text, text
from sqlalchemy.dialects.mysql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    test_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    test_name: Mapped[str] = mapped_column(String(200))
    test_code: Mapped[str] = mapped_column(String(50), unique=True)
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    sample_type: Mapped[str | None] = mapped_column(String(100))
    platform_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("1")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
