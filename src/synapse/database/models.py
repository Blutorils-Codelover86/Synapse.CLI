"""SQLite database models and connection for Synapse."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey,
    create_engine, JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    root_path = Column(String, nullable=False, unique=True)
    synapse_dir = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_scan = Column(DateTime, nullable=True)

    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    project_type = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    last_modified = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    workspace = relationship("Workspace", back_populates="projects")
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    technologies = relationship("Technology", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("workspace_id", "path", name="uq_project_workspace_path"),
    )


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    path = Column(String, nullable=False)
    language = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    content_hash = Column(String, nullable=True)
    last_modified = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="files")
    symbols = relationship("Symbol", back_populates="file", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_file_project_path"),
    )


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    name = Column(String, nullable=False)
    symbol_type = Column(String, nullable=False)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    source_excerpt = Column(Text, nullable=True)
    parent_symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=True)

    file = relationship("File", back_populates="symbols")
    parent = relationship("Symbol", remote_side="Symbol.id", backref="children", foreign_keys=[parent_symbol_id])


class Technology(Base):
    __tablename__ = "technologies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # language, framework, library, dependency, concept

    project = relationship("Project", back_populates="technologies")

    __table_args__ = (
        UniqueConstraint("project_id", "name", "category", name="uq_tech_project_name_cat"),
    )


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)
    source_id = Column(Integer, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=False)
    relationship_type = Column(String, nullable=False)
    strength = Column(Float, default=0.0)
    metadata_ = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_rel_source", "source_type", "source_id"),
        Index("ix_rel_target", "target_type", "target_id"),
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "relationship_type",
            name="uq_relationship_pair",
        ),
    )


# ── Engine & session factory ──────────────────────────────────────────────

_DEFAULT_DB_DIR = Path.home() / ".synapse"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "synapse.db"

engine = create_engine(
    f"sqlite:///{_DEFAULT_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist."""
    _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Return a new database session."""
    init_db()
    return SessionLocal()


# ── Utility helpers ────────────────────────────────────────────────────────

def file_content_hash(path: str | Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
