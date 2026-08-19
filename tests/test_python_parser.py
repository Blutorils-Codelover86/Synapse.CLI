"""Tests for the Python parser."""

import pytest
from synapse.parser.python_parser import PythonParser
from synapse.parser.base import SymbolType


@pytest.fixture
def parser():
    return PythonParser()


class TestPythonParser:
    def test_imports(self, parser):
        source = """
import os
import numpy as np
from pathlib import Path
from typing import Optional, List
"""
        result = parser.parse(source)
        # 2 standard imports + 1 from pathlib + 2 from typing = 5
        assert len(result.imports) == 5
        modules = [i.module_name for i in result.imports]
        assert "os" in modules
        assert "numpy" in modules
        assert any("pathlib" in m for m in modules)
        assert any("typing" in m for m in modules)

    def test_class_extraction(self, parser):
        source = """
class CameraManager:
    def __init__(self, config):
        self.config = config

    def capture_frame(self):
        return self.config

    def stop(self):
        pass
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "CameraManager"

        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 3
        method_names = [m.name for m in methods]
        assert "__init__" in method_names
        assert "capture_frame" in method_names
        assert "stop" in method_names

    def test_parent_child_relationship(self, parser):
        source = """
class Foo:
    def bar(self):
        pass

def standalone():
    pass
"""
        result = parser.parse(source)
        foo_method = [s for s in result.symbols if s.name == "bar"][0]
        assert foo_method.parent_name == "Foo"

        standalone = [s for s in result.symbols if s.name == "standalone"][0]
        assert standalone.parent_name is None

    def test_functions(self, parser):
        source = """
def compute_hash(data: bytes) -> str:
    return "hash"

def load_json(path):
    return {}
"""
        result = parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 2
        names = [f.name for f in functions]
        assert "compute_hash" in names
        assert "load_json" in names

    def test_decorators(self, parser):
        source = """
@dataclass
class Config:
    name: str
    value: int
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].signature is not None
        assert "@dataclass" in classes[0].signature

    def test_nested_class(self, parser):
        source = """
class Outer:
    class Inner:
        pass
"""
        result = parser.parse(source)
        assert len(result.symbols) >= 2

    def test_invalid_python(self, parser):
        source = """
def broken(
    this is not valid python
    @@@
"""
        result = parser.parse(source)
        assert len(result.errors) > 0 or len(result.symbols) == 0

    def test_empty_file(self, parser):
        result = parser.parse("")
        assert len(result.symbols) == 0
        assert len(result.imports) == 0

    def test_line_ranges(self, parser):
        source = """import os


class Foo:
    pass
"""
        result = parser.parse(source)
        foo = [s for s in result.symbols if s.name == "Foo"][0]
        assert foo.start_line == 4
        assert foo.end_line == 5


class TestPythonImportEdgeCases:
    def test_from_import_with_alias(self, parser):
        source = "from os import path as p\n"
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].alias == "p"

    def test_wildcard_import(self, parser):
        source = "from os import *\n"
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].import_type == "wildcard"

    def test_multiple_imports(self, parser):
        source = "import os, sys, json\n"
        result = parser.parse(source)
        assert len(result.imports) == 3

    def test_relative_import(self, parser):
        source = "from .utils import helper\n"
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].is_relative is True
