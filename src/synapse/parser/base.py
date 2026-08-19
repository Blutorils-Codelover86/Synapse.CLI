"""Base types and abstractions for the Synapse parser system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SymbolType(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    COMPONENT = "component"
    INTERFACE = "interface"
    ENUM = "enum"
    VARIABLE = "variable"


@dataclass
class ParsedSymbol:
    name: str
    symbol_type: SymbolType
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    parent_name: Optional[str] = None
    signature: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def full_path(self) -> str:
        if self.parent_name:
            return f"{self.parent_name}.{self.name}"
        return self.name


@dataclass
class ParsedImport:
    module_name: str
    import_type: str  # standard, from, wildcard, dynamic
    alias: Optional[str] = None
    line_number: int = 0
    is_relative: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedFile:
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def class_count(self) -> int:
        return sum(1 for s in self.symbols if s.symbol_type == SymbolType.CLASS)

    @property
    def function_count(self) -> int:
        return sum(1 for s in self.symbols if s.symbol_type == SymbolType.FUNCTION)

    @property
    def method_count(self) -> int:
        return sum(1 for s in self.symbols if s.symbol_type == SymbolType.METHOD)

    @property
    def component_count(self) -> int:
        return sum(1 for s in self.symbols if s.symbol_type == SymbolType.COMPONENT)

    @property
    def interface_count(self) -> int:
        return sum(1 for s in self.symbols if s.symbol_type == SymbolType.INTERFACE)


class BaseParser:
    """Base class for language-specific parsers."""

    language: str = ""

    def parse(self, source_code: str) -> ParsedFile:
        raise NotImplementedError
