"""Tests for the TypeScript/TSX parser."""

import pytest
from synapse.parser.typescript_parser import TypeScriptParser
from synapse.parser.base import SymbolType


@pytest.fixture
def ts_parser():
    return TypeScriptParser(tsx=False)


@pytest.fixture
def tsx_parser():
    return TypeScriptParser(tsx=True)


class TestTypeScriptParser:
    def test_import_statement(self, ts_parser):
        source = """
import React from "react";
import { useState, useEffect } from "react";
"""
        result = ts_parser.parse(source)
        assert len(result.imports) == 2

    def test_interface(self, ts_parser):
        source = """
interface MetricData {
    cpu: number;
    memory: number;
    timestamp: string;
}
"""
        result = ts_parser.parse(source)
        interfaces = [s for s in result.symbols if s.symbol_type == SymbolType.INTERFACE]
        assert len(interfaces) == 1
        assert interfaces[0].name == "MetricData"

    def test_enum(self, ts_parser):
        source = """
enum Direction {
    Up,
    Down,
    Left,
    Right,
}
"""
        result = ts_parser.parse(source)
        enums = [s for s in result.symbols if s.symbol_type == SymbolType.ENUM]
        assert len(enums) == 1
        assert enums[0].name == "Direction"

    def test_class_with_types(self, ts_parser):
        source = """
class DataProcessor {
    process(input: string): string {
        return input;
    }
}
"""
        result = ts_parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 1
        assert "string" in (methods[0].signature or "")

    def test_arrow_function(self, ts_parser):
        source = """
const helper = (x: number): number => {
    return x * 2;
};
"""
        result = ts_parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert functions[0].name == "helper"

    def test_export_function(self, ts_parser):
        source = """
export function hello(): string {
    return "world";
}
"""
        result = ts_parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert "export" in (functions[0].signature or "")


class TestTSXParser:
    def test_react_component(self, tsx_parser):
        source = """
import React from "react";

const Dashboard: React.FC = () => {
    return <div>Hello</div>;
};

export default Dashboard;
"""
        result = tsx_parser.parse(source)
        assert len(result.symbols) >= 1
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) >= 1

    def test_class_component(self, tsx_parser):
        source = """
import React, { Component } from "react";

class App extends Component {
    render() {
        return <div>App</div>;
    }
}
"""
        result = tsx_parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "App"

    def test_interface_with_react(self, tsx_parser):
        source = """
interface Props {
    title: string;
    onClick: () => void;
}

const Button: React.FC<Props> = ({ title, onClick }) => {
    return <button onClick={onClick}>{title}</button>;
};
"""
        result = tsx_parser.parse(source)
        interfaces = [s for s in result.symbols if s.symbol_type == SymbolType.INTERFACE]
        assert len(interfaces) == 1
        assert interfaces[0].name == "Props"


class TestTypeScriptEdgeCases:
    def test_invalid_typescript(self, ts_parser):
        source = """
function broken(
    this is not valid typescript
    @@@
"""
        result = ts_parser.parse(source)
        assert isinstance(result.errors, list)

    def test_empty_file(self, ts_parser):
        result = ts_parser.parse("")
        assert len(result.symbols) == 0
        assert len(result.imports) == 0
