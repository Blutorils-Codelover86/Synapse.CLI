"""Tests for the Rust parser."""

import pytest
from synapse.parser.rust_parser import RustParser
from synapse.parser.base import SymbolType


@pytest.fixture
def parser():
    return RustParser()


class TestRustParser:
    def test_use_statements(self, parser):
        source = """
use std::collections::HashMap;
use std::io::{self, Read};
use crate::module::*;
use self::sub as alias;
"""
        result = parser.parse(source)
        assert len(result.imports) == 4
        modules = [i.module_name for i in result.imports]
        assert any("HashMap" in m or "collections" in m for m in modules)

    def test_structs(self, parser):
        source = """
struct Point {
    x: f64,
    y: f64,
}
"""
        result = parser.parse(source)
        structs = [s for s in result.symbols if s.symbol_type == SymbolType.STRUCT]
        assert len(structs) == 1
        assert structs[0].name == "Point"
        assert structs[0].signature == "struct Point"

    def test_enums(self, parser):
        source = """
enum Direction {
    North,
    South,
    East,
    West,
}
"""
        result = parser.parse(source)
        enums = [s for s in result.symbols if s.symbol_type == SymbolType.ENUM]
        assert len(enums) == 1
        assert enums[0].name == "Direction"

    def test_traits(self, parser):
        source = """
trait Drawable {
    fn draw(&self);
    fn area(&self) -> f64;
}
"""
        result = parser.parse(source)
        traits = [s for s in result.symbols if s.symbol_type == SymbolType.TRAIT]
        assert len(traits) == 1
        assert traits[0].name == "Drawable"
        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD and s.parent_name == "Drawable"]
        assert len(methods) == 2

    def test_standalone_functions(self, parser):
        source = """
fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn main() {
    println!(\"hello\");
}
"""
        result = parser.parse(source)
        funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(funcs) == 2
        names = [f.name for f in funcs]
        assert "add" in names
        assert "main" in names

    def test_impl_blocks(self, parser):
        source = """
struct Foo;

impl Foo {
    fn new() -> Self { Foo }
    fn method(&self) {}
}
"""
        result = parser.parse(source)
        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 2
        assert all(m.parent_name == "Foo" for m in methods)

    def test_methods(self, parser):
        source = """
struct Bar;

impl Bar {
    fn hello(&self, name: &str) -> String {
        format!(\"hello {}\", name)
    }
}
"""
        result = parser.parse(source)
        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "hello"
        assert "fn hello" in methods[0].signature

    def test_parent_relationships(self, parser):
        source = """
mod outer {
    struct Inner;
    fn helper() {}
}
"""
        result = parser.parse(source)
        modules = [s for s in result.symbols if s.symbol_type == SymbolType.MODULE]
        assert len(modules) == 1
        assert modules[0].name == "outer"
        children = [s for s in result.symbols if s.parent_name == "outer"]
        assert len(children) == 2

    def test_malformed_rust(self, parser):
        source = "struct Foo { pub fn broken("
        result = parser.parse(source)
        assert len(result.errors) > 0

    def test_empty_file(self, parser):
        source = ""
        result = parser.parse(source)
        assert len(result.symbols) == 0
        assert len(result.imports) == 0
        assert len(result.errors) == 0
