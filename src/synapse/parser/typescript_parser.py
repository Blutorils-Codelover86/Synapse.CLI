"""TypeScript / TSX source code parser using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_typescript as tsts

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_TS_LANGUAGE = tree_sitter.Language(tsts.language_typescript())
_TSX_LANGUAGE = tree_sitter.Language(tsts.language_tsx())


class TypeScriptParser(BaseParser):
    language = "TypeScript"

    def __init__(self, tsx: bool = False):
        self._tsx = tsx
        lang = _TSX_LANGUAGE if tsx else _TS_LANGUAGE
        self._parser = tree_sitter.Parser(lang)
        self.language = "TSX" if tsx else "TypeScript"

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
        return result

    def _extract_imports(self, node, source: str, result: ParsedFile):
        for child in node.children:
            if child.type == "import_statement":
                line = child.start_point[0] + 1
                import_text = self._get_text(child, source)
                module_name = self._extract_module_from_import(import_text)
                if module_name:
                    is_relative = module_name.startswith(".")
                    result.imports.append(ParsedImport(
                        module_name=module_name,
                        import_type="from" if " from " in import_text else "standard",
                        line_number=line,
                        is_relative=is_relative,
                    ))
            elif child.type == "export_statement":
                for sub in child.children:
                    if sub.type == "import_statement":
                        self._extract_imports(sub, source, result)
                        break
            else:
                self._extract_imports(child, source, result)

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_declaration":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_declaration":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "lexical_declaration" or child.type == "variable_declaration":
                self._handle_variable_declaration(child, source, result, parent_name)
            elif child.type == "interface_declaration":
                self._handle_interface(child, source, result, parent_name)
            elif child.type == "enum_declaration":
                self._handle_enum(child, source, result, parent_name)
            elif child.type == "export_statement":
                self._handle_export(child, source, result, parent_name)
            elif child.type in ("statement_block", "program", "module", "ambient_declaration"):
                self._extract_symbols(child, source, result, parent_name)
            elif child.type == "type_alias_declaration":
                pass  # Skip type aliases for now
            elif self._tsx and child.type == "function_component":
                self._handle_function_component(child, source, result, parent_name)

    def _handle_export(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_declaration":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_declaration":
                self._handle_function(child, source, result, parent_name)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._handle_variable_declaration(child, source, result, parent_name)
            elif child.type == "interface_declaration":
                self._handle_interface(child, source, result, parent_name)

    def _handle_class(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        class_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        sig_parts = []
        if self._has_export_modifier(node):
            sig_parts.append("export")
        sig_parts.append(f"class {class_name}")

        for child in node.children:
            if child.type == "class_heritage":
                text = self._get_text(child, source)
                sig_parts.append(text)

        signature = " ".join(sig_parts) if sig_parts else None

        result.symbols.append(ParsedSymbol(
            name=class_name,
            symbol_type=SymbolType.CLASS,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        self._handle_method(member, source, result, class_name)
                    elif member.type == "public_field_definition":
                        if self._is_function_field(member, source):
                            self._handle_function_field(member, source, result, class_name)

    def _handle_method(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        method_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        params_node = self._child_by_field(node, "parameters")
        params_text = self._get_text(params_node, source) if params_node else "()"

        return_type = ""
        ret = self._child_by_field(node, "return_type")
        if ret:
            return_type = f": {self._get_text(ret, source)}"

        signature = f"{method_name}{params_text}{return_type}"

        result.symbols.append(ParsedSymbol(
            name=method_name,
            symbol_type=SymbolType.METHOD,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

    def _handle_function(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        func_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        params_node = self._child_by_field(node, "parameters")
        params_text = self._get_text(params_node, source) if params_node else "()"

        return_type = ""
        ret = self._child_by_field(node, "return_type")
        if ret:
            return_type = f": {self._get_text(ret, source)}"

        sig_parts = []
        if self._has_export_modifier(node):
            sig_parts.append("export")
        sig_parts.append(f"function {func_name}{params_text}{return_type}")
        signature = " ".join(sig_parts) if sig_parts else None

        result.symbols.append(ParsedSymbol(
            name=func_name,
            symbol_type=SymbolType.FUNCTION,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

    def _handle_interface(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        sig_parts = []
        if self._has_export_modifier(node):
            sig_parts.append("export")
        sig_parts.append(f"interface {name}")
        signature = " ".join(sig_parts) if sig_parts else None

        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.INTERFACE,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

    def _handle_enum(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.ENUM,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
        ))

    def _handle_variable_declaration(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = self._child_by_field(child, "name")
                value_node = self._child_by_field(child, "value")
                if name_node:
                    name_text = self._get_text(name_node, source)
                    if value_node and value_node.type in ("arrow_function", "function"):
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        params_node = self._child_by_field(value_node, "parameters")
                        params_text = self._get_text(params_node, source) if params_node else "()"

                        return_type = ""
                        ret = self._child_by_field(value_node, "return_type")
                        if ret:
                            return_type = f": {self._get_text(ret, source)}"

                        sig = f"const {name_text} = {params_text}{return_type} => ..."
                        result.symbols.append(ParsedSymbol(
                            name=name_text,
                            symbol_type=SymbolType.FUNCTION,
                            start_line=start_line,
                            end_line=end_line,
                            start_column=node.start_point[1],
                            end_column=node.end_point[1],
                            parent_name=parent_name,
                            signature=sig,
                            metadata={"is_arrow": True},
                        ))

    def _handle_function_component(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        name = self._get_text(name_node, source)
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.COMPONENT,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
        ))

    def _handle_function_field(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if name_node:
            result.symbols.append(ParsedSymbol(
                name=self._get_text(name_node, source),
                symbol_type=SymbolType.METHOD,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_name=parent_name,
            ))

    def _is_function_field(self, node, source: str) -> bool:
        value_node = self._child_by_field(node, "value")
        if value_node and value_node.type in ("arrow_function", "function"):
            return True
        return False

    def _has_export_modifier(self, node) -> bool:
        parent = node.parent
        if parent and parent.type == "export_statement":
            return True
        return False

    def _extract_module_from_import(self, text: str) -> str | None:
        import re
        match = re.search(r'from\s+["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        match = re.search(r'import\s+["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        return None

    def _child_by_field(self, node, name: str):
        result = node.child_by_field_name(name)
        return result if result is not None else None

    def _get_text(self, node, source: str) -> str:
        if node is None:
            return ""
        return source[node.start_byte:node.end_byte]
