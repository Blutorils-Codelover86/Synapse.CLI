"""JavaScript source code parser using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_javascript as tsjs

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_JS_LANGUAGE = tree_sitter.Language(tsjs.language())


class JavaScriptParser(BaseParser):
    language = "JavaScript"

    def __init__(self):
        self._parser = tree_sitter.Parser(_JS_LANGUAGE)

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
            elif child.type == "lexical_declaration" or child.type == "variable_declaration":
                self._extract_require_imports(child, source, result)
                self._extract_imports(child, source, result)
            elif child.type == "export_statement" and child.children:
                for sub in child.children:
                    if sub.type == "import_statement":
                        self._extract_imports(sub, source, result)
                        break
            else:
                self._extract_imports(child, source, result)

    def _extract_require_imports(self, node, source: str, result: ParsedFile):
        """Extract require() calls from variable declarations."""
        for child in node.children:
            if child.type == "variable_declarator":
                value_node = self._child_by_field(child, "value")
                if value_node and value_node.type == "call_expression":
                    func_node = self._child_by_field(value_node, "function")
                    if func_node and self._get_text(func_node, source) == "require":
                        args = self._child_by_field(value_node, "arguments")
                        if args and args.children:
                            for arg in args.children:
                                if arg.type == "string":
                                    module_name = self._get_text(arg, source).strip("'\"")
                                    line = node.start_point[0] + 1
                                    result.imports.append(ParsedImport(
                                        module_name=module_name,
                                        import_type="dynamic",
                                        line_number=line,
                                        is_relative=module_name.startswith("."),
                                    ))

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_declaration":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_declaration":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "lexical_declaration" or child.type == "variable_declaration":
                self._handle_variable_declaration(child, source, result, parent_name)
            elif child.type == "export_statement":
                self._handle_export(child, source, result, parent_name)
            elif child.type in ("statement_block", "program", "module"):
                self._extract_symbols(child, source, result, parent_name)

    def _handle_export(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_declaration":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_declaration":
                self._handle_function(child, source, result, parent_name)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._handle_variable_declaration(child, source, result, parent_name)

    def _handle_class(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            return
        class_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Build signature
        sig_parts = []
        # Check for export
        if self._has_export_modifier(node):
            sig_parts.append("export")
        sig_parts.append(f"class {class_name}")

        # Check for extends
        for child in node.children:
            if child.type == "class_heritage":
                sig_parts.append(f"extends {self._get_text(child, source).lstrip('extends ')}")

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

        # Extract methods inside the class
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        self._handle_method(member, source, result, class_name)
                    elif member.type == "field_definition" and self._is_function_field(member, source):
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

        sig_parts = []
        if "static" in [self._get_text(c, source) for c in node.children if c.type == "identifier"]:
            sig_parts.append("static")
        sig_parts.append(f"{method_name}{params_text}")
        signature = " ".join(sig_parts) if sig_parts else None

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

        sig_parts = []
        if self._has_export_modifier(node):
            sig_parts.append("export")
        sig_parts.append(f"function {func_name}{params_text}")
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
                        sig = f"const {name_text} = {params_text} => ..."
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

    def _handle_function_field(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "property")
        if name_node:
            name_text = self._get_text(name_node, source)
            result.symbols.append(ParsedSymbol(
                name=name_text,
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
        for child in (node.children if node.children else []):
            if child.type == "export" or self._get_text(child, "") == "export":
                return True
        return False

    def _extract_module_from_import(self, text: str) -> str | None:
        # Find the module string in import statements
        import re
        match = re.search(r'from\s+["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        match = re.search(r'import\s+["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        return None

    def _extract_module_from_require(self, text: str) -> str | None:
        import re
        match = re.search(r'require\s*\(\s*["\']([^"\']+)["\']', text)
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
