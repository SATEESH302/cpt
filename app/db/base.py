"""Shared SQLAlchemy declarative registry."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
