"""Rust source code parser using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_rust as tsrust

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_RUST_LANGUAGE = tree_sitter.Language(tsrust.language())

# Node types whose bodies may contain nested symbols worth recursing into
_CONTAINER_TYPES = {"source_file", "declaration_list", "block", "field_declaration_list"}


class RustParser(BaseParser):
    language = "Rust"

    def __init__(self):
        self._parser = tree_sitter.Parser(_RUST_LANGUAGE)

    def parse(self, source_code: str) -> ParsedFile:
        result = ParsedFile(language=self.language)
        try:
            tree = self._parser.parse(source_code.encode("utf-8"))
        except Exception as e:
            result.errors.append(f"Parse error: {e}")
            return result

        root = tree.root_node
        self._extract_imports(root, source_code, result)
        self._extract_symbols(root, source_code, result, parent_name=None)

        if tree.root_node.has_error:
            result.errors.append("Rust contains syntax errors")

        return result

    def _extract_imports(self, node, source: str, result: ParsedFile):
        for child in node.children:
            if child.type == "use_declaration":
                line = child.start_point[0] + 1
                imp = self._extract_use_declaration(child, source)
                if imp:
                    imp.line_number = line
                    result.imports.append(imp)
            elif child.type in _CONTAINER_TYPES or child.type == "mod_item":
                self._extract_imports(child, source, result)

    def _extract_use_declaration(self, node, source: str) -> ParsedImport | None:
        argument = node.child_by_field_name("argument")
        if argument is None:
            return None

        text = self._get_text(argument, source).strip()
        if not text:
            return None

        # use foo as bar;
        if argument.type == "use_as_clause":
            left, _, right = text.partition(" as ")
            return ParsedImport(
                module_name=left.strip(),
                import_type="standard",
                alias=right.strip() if right else None,
                metadata={"statement": text},
            )

        if argument.type == "use_wildcard":
            return ParsedImport(
                module_name=text,
                import_type="wildcard",
                metadata={"statement": text},
            )

        if argument.type in ("scoped_use_list", "use_list"):
            return ParsedImport(
                module_name=text,
                import_type="from",
                metadata={"statement": text},
            )

        return ParsedImport(
            module_name=text,
            import_type="standard",
            metadata={"statement": text},
        )

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "struct_item":
                self._handle_struct(child, source, result, parent_name)
            elif child.type == "enum_item":
                self._handle_enum(child, source, result, parent_name)
            elif child.type == "trait_item":
                self._handle_trait(child, source, result, parent_name)
            elif child.type == "function_item":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "impl_item":
                self._handle_impl(child, source, result, parent_name)
            elif child.type == "mod_item":
                self._handle_module(child, source, result, parent_name)
            elif child.type in _CONTAINER_TYPES:
                self._extract_symbols(child, source, result, parent_name)

    def _handle_struct(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name = self._get_name(node, source)
        if not name:
            return
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.STRUCT,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"struct {name}",
        ))

    def _handle_enum(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name = self._get_name(node, source)
        if not name:
            return
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.ENUM,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"enum {name}",
        ))

    def _handle_trait(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name = self._get_name(node, source)
        if not name:
            return
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.TRAIT,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"trait {name}",
        ))

        for child in node.children:
            if child.type in ("declaration_list", "block"):
                for member in child.children:
                    if member.type in ("function_signature_item", "function_item"):
                        self._handle_function(member, source, result, parent_name=name)

    def _handle_impl(self, node, source: str, result: ParsedFile, parent_name: str | None):
        impl_type = self._impl_type_name(node, source)
        if not impl_type:
            impl_type = "impl"

        for child in node.children:
            if child.type == "declaration_list":
                for member in child.children:
                    if member.type == "function_item":
                        self._handle_function(member, source, result, parent_name=impl_type)

    def _handle_function(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name = self._get_name(node, source)
        if not name:
            return
        is_method = parent_name is not None

        parameters = node.child_by_field_name("parameters")
        params_text = self._get_text(parameters, source) if parameters else "()"

        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.METHOD if is_method else SymbolType.FUNCTION,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"fn {name}{params_text}",
        ))

    def _handle_module(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name = self._get_name(node, source)
        if not name:
            return
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.MODULE,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"mod {name}",
        ))

        for child in node.children:
            if child.type in ("declaration_list", "block"):
                self._extract_symbols(child, source, result, parent_name=name)

    def _impl_type_name(self, node, source: str) -> str:
        impl_type = node.child_by_field_name("type")
        if impl_type is None:
            return ""
        text = self._get_text(impl_type, source).strip()
        if impl_type.type == "generic_type":
            base = text.split("<", 1)[0].strip()
            if base:
                return base
        return text

    def _get_name(self, node, source: str) -> str:
        name = node.child_by_field_name("name")
        if name is not None:
            return self._get_text(name, source)
        return ""

    def _get_text(self, node, source: str) -> str:
        if node is None:
            return ""
        return source[node.start_byte:node.end_byte]