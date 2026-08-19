"""Tests for the JavaScript parser."""

import pytest
from synapse.parser.javascript_parser import JavaScriptParser
from synapse.parser.base import SymbolType


@pytest.fixture
def parser():
    return JavaScriptParser()


class TestJavaScriptParser:
    def test_import_statement(self, parser):
        source = """
import React from "react";
import { useState } from "react";
"""
        result = parser.parse(source)
        assert len(result.imports) == 2

    def test_require_import(self, parser):
        source = """
const express = require('express');
const path = require("path");
"""
        result = parser.parse(source)
        assert len(result.imports) == 2
        modules = [i.module_name for i in result.imports]
        assert "express" in modules
        assert "path" in modules

    def test_class_declaration(self, parser):
        source = """
class CameraManager {
    constructor(config) {
        this.config = config;
    }

    captureFrame() {
        return this.config;
    }

    stop() {
        return true;
    }
}
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "CameraManager"

        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 3

    def test_function_declaration(self, parser):
        source = """
function computeHash(data) {
    return data;
}

function loadJSON(path) {
    return {};
}
"""
        result = parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 2

    def test_arrow_function_export(self, parser):
        source = """
export const helper = () => {
    return 42;
};
"""
        result = parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert functions[0].name == "helper"

    def test_invalid_javascript(self, parser):
        source = """
function broken(
    this is not valid javascript
    @@@
"""
        result = parser.parse(source)
        # Should not crash, may have errors or empty symbols
        assert isinstance(result.errors, list)

    def test_empty_file(self, parser):
        result = parser.parse("")
        assert len(result.symbols) == 0
        assert len(result.imports) == 0

    def test_export_function(self, parser):
        source = """
export function hello() {
    return "world";
}
"""
        result = parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert "export" in (functions[0].signature or "")

    def test_class_with_extends(self, parser):
        source = """
class MyComponent extends React.Component {
    render() {
        return null;
    }
}
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert "extends" in (classes[0].signature or "")

    def test_relative_import(self, parser):
        source = 'import utils from "./utils";\n'
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].is_relative is True
