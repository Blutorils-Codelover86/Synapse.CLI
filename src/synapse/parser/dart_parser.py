"""Dart source code parser using Tree-sitter."""

from __future__ import annotations

import re

import tree_sitter
import tree_sitter_dart as tsdart

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_DART_LANGUAGE = tree_sitter.Language(tsdart.language())


class DartParser(BaseParser):
    language = "Dart"

    def __init__(self):
        self._parser = tree_sitter.Parser(_DART_LANGUAGE)

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
            if child.type == "import_or_export":
                import_text = self._get_text(child, source)
                line = child.start_point[0] + 1
                if "import" in import_text[:20]:
                    # import 'package:foo/bar.dart';
                    match = re.search(r"import\s+['\"]([^'\"]+)['\"]", import_text)
                    if match:
                        module_name = match.group(1)
                        is_relative = module_name.startswith(".")
                        result.imports.append(ParsedImport(
                            module_name=module_name,
                            import_type="standard",
                            line_number=line,
                            is_relative=is_relative,
                        ))
                elif "export" in import_text[:20]:
                    match = re.search(r"export\s+['\"]([^'\"]+)['\"]", import_text)
                    if match:
                        module_name = match.group(1)
                        result.imports.append(ParsedImport(
                            module_name=module_name,
                            import_type="standard",
                            line_number=line,
                            is_relative=module_name.startswith("."),
                            metadata={"is_export": True},
                        ))
            elif child.type == "import_specification":
                import_text = self._get_text(child, source)
                line = child.start_point[0] + 1
                match = re.search(r"import\s+['\"]([^'\"]+)['\"]", import_text)
                if match:
                    module_name = match.group(1)
                    result.imports.append(ParsedImport(
                        module_name=module_name,
                        import_type="standard",
                        line_number=line,
                        is_relative=module_name.startswith("."),
                    ))
            else:
                self._extract_imports(child, source, result)

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_definition":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_definition":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "function_declaration":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "constructor_declaration":
                self._handle_constructor(child, source, result, parent_name)
            elif child.type == "enum_declaration":
                self._handle_enum(child, source, result, parent_name)
            elif child.type in ("program", "class_body", "declaration_list", "block"):
                self._extract_symbols(child, source, result, parent_name)
            elif child.type == "function_signature":
                # Dart splits function_signature + function_body as siblings
                self._handle_function_signature_pair(child, node, source, result, parent_name)

    def _handle_class(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            # Try finding identifier child
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
        if not name_node:
            return

        class_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Build signature
        sig_parts = []
        # Check for annotations/modifiers before class
        for child in node.children:
            if child.type == "metadata" or child.type == "annotation":
                sig_parts.append(f"@{self._get_text(child, source).lstrip('@')}")
        sig_parts.append(f"class {class_name}")

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
            if child.type == "class_body" or child.type == "declaration_list":
                for member in child.children:
                    if member.type == "function_declaration":
                        self._handle_function(member, source, result, parent_name=class_name)
                    elif member.type == "constructor_declaration":
                        self._handle_constructor(member, source, result, parent_name=class_name)
                    elif member.type == "method_signature":
                        self._handle_method_signature(member, child, source, result, class_name)

    def _handle_function(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
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
            return_type = f" {self._get_text(ret, source)}"

        signature = f"{func_name}{params_text}{return_type}"

        is_method = parent_name is not None
        result.symbols.append(ParsedSymbol(
            name=func_name,
            symbol_type=SymbolType.METHOD if is_method else SymbolType.FUNCTION,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

    def _handle_function_signature_pair(self, sig_node, parent_node, source: str, result: ParsedFile, parent_name: str | None):
        """Handle Dart function_signature + function_body as sibling nodes."""
        # Find the name from the function_signature
        name_node = None
        for child in sig_node.children:
            if child.type == "identifier":
                name_node = child
                break
        if not name_node:
            return

        func_name = self._get_text(name_node, source)
        start_line = sig_node.start_point[0] + 1

        # Find the corresponding function_body to get the end line
        end_line = start_line
        body_node = None
        sig_idx = None
        for i, child in enumerate(parent_node.children):
            if child is sig_node:
                sig_idx = i
                break
        if sig_idx is not None and sig_idx + 1 < len(parent_node.children):
            next_node = parent_node.children[sig_idx + 1]
            if next_node.type == "function_body":
                body_node = next_node
                end_line = body_node.end_point[0] + 1

        # Build params
        params_node = None
        for child in sig_node.children:
            if child.type == "formal_parameter_list":
                params_node = child
                break
        params_text = self._get_text(params_node, source) if params_node else "()"

        # Build return type
        return_type = ""
        for child in sig_node.children:
            if child.type in ("type_identifier", "void_type", "Future", "dynamic_type"):
                return_type_text = self._get_text(child, source)
                # Check for type arguments
                for sub in child.children:
                    if sub.type == "type_arguments":
                        return_type_text += self._get_text(sub, source)
                return_type = f" {return_type_text}"
                break

        signature = f"{func_name}{params_text}{return_type}"

        is_method = parent_name is not None
        result.symbols.append(ParsedSymbol(
            name=func_name,
            symbol_type=SymbolType.METHOD if is_method else SymbolType.FUNCTION,
            start_line=start_line,
            end_line=end_line,
            start_column=sig_node.start_point[1],
            end_column=sig_node.end_point[1],
            parent_name=parent_name,
            signature=signature,
        ))

    def _handle_method_signature(self, sig_node, class_body_node, source: str, result: ParsedFile, class_name: str):
        """Handle Dart method_signature + function_body inside a class body."""
        name_node = None
        for child in sig_node.children:
            if child.type == "function_signature":
                for sub in child.children:
                    if sub.type == "identifier":
                        name_node = sub
                        break
            elif child.type == "identifier":
                name_node = child
        if not name_node:
            # Try the function_signature children
            for child in sig_node.children:
                if child.type == "function_signature":
                    for sub in child.children:
                        if sub.type == "identifier":
                            name_node = sub
                            break
        if not name_node:
            return

        method_name = self._get_text(name_node, source)
        start_line = sig_node.start_point[0] + 1

        # Find function_body after this method_signature
        end_line = start_line
        sig_idx = None
        for i, child in enumerate(class_body_node.children):
            if child is sig_node:
                sig_idx = i
                break
        if sig_idx is not None and sig_idx + 1 < len(class_body_node.children):
            next_node = class_body_node.children[sig_idx + 1]
            if next_node.type == "function_body":
                end_line = next_node.end_point[0] + 1

        # Build params
        params_text = "()"
        for child in sig_node.children:
            if child.type == "function_signature":
                for sub in child.children:
                    if sub.type == "formal_parameter_list":
                        params_text = self._get_text(sub, source)
                        break
            elif child.type == "formal_parameter_list":
                params_text = self._get_text(child, source)

        result.symbols.append(ParsedSymbol(
            name=method_name,
            symbol_type=SymbolType.METHOD,
            start_line=start_line,
            end_line=end_line,
            start_column=sig_node.start_point[1],
            end_column=sig_node.end_point[1],
            parent_name=class_name,
            signature=f"{method_name}{params_text}",
        ))

    def _handle_constructor(self, node, source: str, result: ParsedFile, parent_name: str | None):
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Constructors can be named: ClassName() or ClassName.named()
        # Try to get the name from the identifier children
        name_parts = []
        for child in node.children:
            if child.type == "identifier":
                name_parts.append(self._get_text(child, source))
            elif child.type == "formal_parameters":
                params_text = self._get_text(child, source)
        
        constructor_name = ".".join(name_parts) if name_parts else "constructor"
        params_node = self._child_by_field(node, "parameters")
        params_text = self._get_text(params_node, source) if params_node else "()"

        result.symbols.append(ParsedSymbol(
            name=constructor_name,
            symbol_type=SymbolType.METHOD,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"{constructor_name}{params_text}",
        ))

    def _handle_enum(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._child_by_field(node, "name")
        if not name_node:
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
        if not name_node:
            return

        name = self._get_text(name_node, source)
        result.symbols.append(ParsedSymbol(
            name=name,
            symbol_type=SymbolType.ENUM,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
        ))

    def _child_by_field(self, node, name: str):
        result = node.child_by_field_name(name)
        return result if result is not None else None

    def _get_text(self, node, source: str) -> str:
        if node is None:
            return ""
        return source[node.start_byte:node.end_byte]
