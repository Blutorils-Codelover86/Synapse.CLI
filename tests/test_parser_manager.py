"""Tests for the parser manager and database storage."""

import pytest
from synapse.parser.manager import ParserManager
from synapse.parser.base import SymbolType


@pytest.fixture
def manager():
    return ParserManager()


class TestParserManager:
    def test_can_parse_python(self, manager):
        assert manager.can_parse("Python") is True

    def test_can_parse_javascript(self, manager):
        assert manager.can_parse("JavaScript") is True

    def test_can_parse_typescript(self, manager):
        assert manager.can_parse("TypeScript") is True

    def test_can_parse_dart(self, manager):
        assert manager.can_parse("Dart") is True

    def test_cannot_parse_rust(self, manager):
        assert manager.can_parse("Rust") is False

    def test_parse_python_source(self, manager):
        source = """
import os

class Foo:
    def bar(self):
        pass

def baz():
    return 42
"""
        result = manager.parse_source(source, "Python")
        assert len(result.symbols) == 3
        assert len(result.imports) == 1

    def test_parse_javascript_source(self, manager):
        source = """
const express = require('express');
function hello() { return "world"; }
"""
        result = manager.parse_source(source, "JavaScript")
        assert len(result.imports) == 1
        assert len(result.symbols) == 1

    def test_parse_unsupported_language(self, manager):
        source = "fn main() { println!(\"hello\"); }"
        result = manager.parse_source(source, "Rust")
        assert len(result.errors) > 0

    def test_tsx_detection(self, manager):
        source = """
import React from "react";
const App = () => <div>hello</div>;
"""
        result = manager.parse_source(source, "TypeScript", file_ext=".tsx")
        assert result.language == "TSX"


class TestRepeatedParsing:
    def test_no_duplicate_symbols(self, manager):
        """Parsing the same file twice should produce the same result."""
        source = """
class Foo:
    def bar(self):
        pass
"""
        result1 = manager.parse_source(source, "Python")
        result2 = manager.parse_source(source, "Python")
        assert len(result1.symbols) == len(result2.symbols)
        assert len(result1.imports) == len(result2.imports)
