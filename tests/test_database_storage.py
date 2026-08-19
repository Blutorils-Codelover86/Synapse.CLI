"""Integration tests for the database storage layer."""

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from synapse.database.models import (
    Base, Workspace, Project, File, Symbol, FileImport,
)
from synapse.parser.manager import ParserManager


@pytest.fixture
def db_session():
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def manager():
    return ParserManager()


class TestDatabaseStorage:
    def test_store_symbols(self, db_session, manager):
        # Create workspace and project
        workspace = Workspace(root_path="/test", synapse_dir="/test/.synapse")
        db_session.add(workspace)
        db_session.commit()

        project = Project(workspace_id=workspace.id, name="test", path="/test")
        db_session.add(project)
        db_session.commit()

        file_record = File(
            project_id=project.id, path="main.py",
            language="Python", content_hash="abc123",
        )
        db_session.add(file_record)
        db_session.commit()

        # Parse and store
        source = """
import os

class Foo:
    def bar(self):
        pass

def baz():
    return 42
"""
        parsed = manager.parse_source(source, "Python")
        stats = manager.store_parsed_file(db_session, file_record, parsed)

        # Verify stored
        symbols = db_session.query(Symbol).filter(Symbol.file_id == file_record.id).all()
        assert len(symbols) == 3  # Foo, bar, baz

        imports = db_session.query(FileImport).filter(FileImport.file_id == file_record.id).all()
        assert len(imports) == 1

        assert stats["classes"] == 1
        assert stats["functions"] == 1
        assert stats["methods"] == 1

    def test_parent_child_in_db(self, db_session, manager):
        workspace = Workspace(root_path="/test", synapse_dir="/test/.synapse")
        db_session.add(workspace)
        db_session.commit()

        project = Project(workspace_id=workspace.id, name="test", path="/test")
        db_session.add(project)
        db_session.commit()

        file_record = File(
            project_id=project.id, path="main.py",
            language="Python", content_hash="abc123",
        )
        db_session.add(file_record)
        db_session.commit()

        source = """
class MyClass:
    def my_method(self):
        pass
"""
        parsed = manager.parse_source(source, "Python")
        manager.store_parsed_file(db_session, file_record, parsed)

        # Check parent-child
        symbols = db_session.query(Symbol).filter(Symbol.file_id == file_record.id).all()
        class_sym = [s for s in symbols if s.symbol_type == "class"][0]
        method_sym = [s for s in symbols if s.symbol_type == "method"][0]

        assert method_sym.parent_symbol_id == class_sym.id

    def test_incremental_update_no_duplicates(self, db_session, manager):
        workspace = Workspace(root_path="/test", synapse_dir="/test/.synapse")
        db_session.add(workspace)
        db_session.commit()

        project = Project(workspace_id=workspace.id, name="test", path="/test")
        db_session.add(project)
        db_session.commit()

        file_record = File(
            project_id=project.id, path="main.py",
            language="Python", content_hash="abc123",
        )
        db_session.add(file_record)
        db_session.commit()

        source = """
def hello():
    pass
"""
        # Parse twice — should not create duplicates
        parsed1 = manager.parse_source(source, "Python")
        manager.store_parsed_file(db_session, file_record, parsed1)

        parsed2 = manager.parse_source(source, "Python")
        manager.store_parsed_file(db_session, file_record, parsed2)

        symbols = db_session.query(Symbol).filter(Symbol.file_id == file_record.id).all()
        assert len(symbols) == 1  # No duplicate

    def test_store_imports(self, db_session, manager):
        workspace = Workspace(root_path="/test", synapse_dir="/test/.synapse")
        db_session.add(workspace)
        db_session.commit()

        project = Project(workspace_id=workspace.id, name="test", path="/test")
        db_session.add(project)
        db_session.commit()

        file_record = File(
            project_id=project.id, path="app.js",
            language="JavaScript", content_hash="abc123",
        )
        db_session.add(file_record)
        db_session.commit()

        source = """
const express = require('express');
import React from "react";
"""
        parsed = manager.parse_source(source, "JavaScript")
        manager.store_parsed_file(db_session, file_record, parsed)

        imports = db_session.query(FileImport).filter(FileImport.file_id == file_record.id).all()
        assert len(imports) == 2
        modules = [i.module_name for i in imports]
        assert "express" in modules
        assert "react" in modules
