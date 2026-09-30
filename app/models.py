from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum, StrEnum

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HSKLevel(StrEnum):
    HSK1 = "HSK1"
    HSK2 = "HSK2"
    HSK3 = "HSK3"
    HSK4 = "HSK4"
    HSK5 = "HSK5"
    HSK6 = "HSK6"


class RegistrationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_code: Mapped[str] = mapped_column(
        String(10), unique=True, index=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    nationality: Mapped[str] = mapped_column(String(100), nullable=False)
    passport_number: Mapped[str] = mapped_column(String(32), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(24), nullable=False)
    parent_phone_number: Mapped[str] = mapped_column(String(24), nullable=False)
    hsk_level: Mapped[HSKLevel] = mapped_column(
        SqlEnum(
            HSKLevel,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            name="hsk_level",
        ),
        nullable=False,
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        SqlEnum(
            RegistrationStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            name="registration_status",
        ),
        default=RegistrationStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[int | None] = mapped_column(Integer)
