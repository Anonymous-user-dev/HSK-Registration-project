from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum, StrEnum

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, text
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


class AuditAction(StrEnum):
    REGISTRATION_UPDATED = "REGISTRATION_UPDATED"
    REGISTRATION_VERIFIED = "REGISTRATION_VERIFIED"
    REGISTRATION_REJECTED = "REGISTRATION_REJECTED"


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
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    staff_user_id: Mapped[int] = mapped_column(
        ForeignKey("staff_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[AuditAction] = mapped_column(
        SqlEnum(
            AuditAction,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            name="audit_action",
        ),
        nullable=False,
    )
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
