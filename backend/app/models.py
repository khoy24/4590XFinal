"""SQLAlchemy models for users and AWS connections."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
    )

    aws_connection: Mapped[AwsConnection | None] = relationship(
        "AwsConnection",
        back_populates="user",
        uselist=False,
    )


class AwsConnection(Base):
    """One AWS IAM role connection per user (CloudFormation + ExternalId)."""

    __tablename__ = "aws_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    # sts:ExternalId (high-entropy UUID); used for webhook lookup and AssumeRole
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Fernet-encrypted IAM role ARN from the customer account
    encrypted_role_arn: Mapped[str | None] = mapped_column(Text, nullable=True)

    # pending | role_ready | active
    connect_status: Mapped[str] = mapped_column(String(32), default="pending")

    aws_account_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Last successful STS AssumedRoleUser ARN (for UI); not a long-lived secret
    user_arn: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str] = mapped_column(String(32), default="us-east-1")

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
        onupdate=lambda: dt.datetime.now(dt.UTC),
    )

    user: Mapped[User] = relationship("User", back_populates="aws_connection")
