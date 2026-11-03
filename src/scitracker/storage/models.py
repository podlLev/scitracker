from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

STATUSES = "('to_read', 'reading', 'done')"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="role_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthorRow(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique by name is a temporary simplification (see ADR-003 on author identity).
    name: Mapped[str] = mapped_column(String(300), unique=True)


class PublicationAuthorRow(Base):
    """Association object: keeps the order of authors in a publication."""

    __tablename__ = "publication_authors"

    publication_id: Mapped[int] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int]

    author: Mapped[AuthorRow] = relationship()

    __table_args__ = (Index("ix_publication_authors_author_id", "author_id"),)


class PublicationRow(Base):
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint("doi IS NOT NULL OR arxiv_id IS NOT NULL", name="has_identifier"),
        Index("ix_publications_published_on", "published_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(1000))
    # In PostgreSQL several NULLs do not violate UNIQUE, so publications
    # without a DOI (or without an arXiv ID) are allowed.
    doi: Mapped[str | None] = mapped_column(String(255), unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    abstract: Mapped[str | None] = mapped_column(Text)
    published_on: Mapped[date | None]
    url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author_links: Mapped[list[PublicationAuthorRow]] = relationship(
        order_by=PublicationAuthorRow.position,
        cascade="all, delete-orphan",
    )


class TopicRow(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(500))
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReadingItemRow(Base):
    __tablename__ = "reading_items"
    __table_args__ = (
        UniqueConstraint("user_id", "publication_id", name="user_publication"),
        CheckConstraint(f"status IN {STATUSES}", name="status_valid"),
        CheckConstraint(
            "(status = 'done') = (finished_at IS NOT NULL)", name="finished_matches_status"
        ),
        Index("ix_reading_items_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="to_read")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StatusChangeRow(Base):
    __tablename__ = "status_changes"
    __table_args__ = (
        CheckConstraint(f"from_status IN {STATUSES}", name="from_status_valid"),
        CheckConstraint(f"to_status IN {STATUSES}", name="to_status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_item_id: Mapped[int] = mapped_column(
        ForeignKey("reading_items.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NoteRow(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_item_id: Mapped[int] = mapped_column(
        ForeignKey("reading_items.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
