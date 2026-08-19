"""Python source code parser using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_python as tspython

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_PYTHON_LANGUAGE = tree_sitter.Language(tspython.language())


class PythonParser(BaseParser):
    language = "Python"

    def __init__(self):
        self._parser = tree_sitter.Parser(_PYTHON_LANGUAGE)

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
                # Parse the import statement text directly
                # "import os" or "import os, sys, json" or "import numpy as np"
                after_import = import_text[len("import"):].strip()
                for part in after_import.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    as_parts = part.split(" as ")
                    module = as_parts[0].strip()
                    alias = as_parts[1].strip() if len(as_parts) > 1 else None
                    result.imports.append(ParsedImport(
                        module_name=module,
                        import_type="standard",
                        alias=alias,
                        line_number=line,
                    ))
            elif child.type == "import_from_statement":
                line = child.start_point[0] + 1
                import_text = self._get_text(child, source)
                # Parse "from X import Y, Z" from text
                # Extract the module part (between 'from' and 'import')
                after_from = import_text[len("from"):].strip()
                # Find where ' import ' keyword is (with spaces on both sides)
                import_idx = after_from.find(" import ")
                if import_idx >= 0:
                    module_name = after_from[:import_idx].strip()
                    names_start = import_idx + len(" import ")
                    names_part = after_from[names_start:].strip()
                else:
                    # Fallback: try rfind for " import" at end
                    import_idx = after_from.rfind(" import")
                    if import_idx >= 0:
                        module_name = after_from[:import_idx].strip()
                        names_start = import_idx + len(" import")
                        while names_start < len(after_from) and after_from[names_start] == " ":
                            names_start += 1
                        names_part = after_from[names_start:].strip()
                    else:
                        module_name = after_from
                        names_part = ""

                is_relative = module_name.startswith(".") if module_name else False

                if not names_part:
                    # from X import (empty)
                    continue

                # Parse imported names
                imported_names = []
                # Handle parenthesized imports
                names_part = names_part.strip("()")
                for name_part in names_part.split(","):
                    name_part = name_part.strip()
                    if not name_part:
                        continue
                    if name_part == "*":
                        imported_names.append(("*", None))
                    elif " as " in name_part:
                        parts = name_part.split(" as ")
                        imported_names.append((parts[0].strip(), parts[1].strip()))
                    else:
                        imported_names.append((name_part.strip(), None))

                for name, alias in imported_names:
                    result.imports.append(ParsedImport(
                        module_name=f"{module_name}.{name}" if module_name else name,
                        import_type="wildcard" if name == "*" else "from",
                        alias=alias,
                        line_number=line,
                        is_relative=is_relative,
                        metadata={"from_module": module_name, "imported_name": name},
                    ))
            else:
                self._extract_imports(child, source, result)

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "class_definition":
                self._handle_class(child, source, result, parent_name)
            elif child.type == "function_definition":
                self._handle_function(child, source, result, parent_name)
            elif child.type == "decorated_definition":
                # Unwrap decorated definitions
                for sub in child.children:
                    if sub.type == "class_definition":
                        self._handle_class(sub, source, result, parent_name)
                    elif sub.type == "function_definition":
                        self._handle_function(sub, source, result, parent_name)
            else:
                if child.type in ("block", "module", "compound_statement"):
                    self._extract_symbols(child, source, result, parent_name)

    def _handle_class(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = child_by_field_name(node, "name")
        if not name_node:
            return
        class_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Extract class signature (bases, decorators)
        decorators = self._extract_decorators(node, source)
        bases = self._extract_class_bases(node, source)
        sig_parts = []
        if decorators:
            sig_parts.extend(decorators)
        sig_parts.append(f"class {class_name}")
        if bases:
            sig_parts.append(f"({', '.join(bases)})")
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
            if child.type == "block":
                for method_node in child.children:
                    if method_node.type == "function_definition":
                        self._handle_function(method_node, source, result, parent_name=class_name)
                    elif method_node.type == "class_definition":
                        self._handle_class(method_node, source, result, parent_name=class_name)
                    elif method_node.type == "decorated_definition":
                        for sub in method_node.children:
                            if sub.type == "function_definition":
                                self._handle_function(sub, source, result, parent_name=class_name)
                            elif sub.type == "class_definition":
                                self._handle_class(sub, source, result, parent_name=class_name)

    def _handle_function(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = child_by_field_name(node, "name")
        if not name_node:
            return
        func_name = self._get_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        is_method = parent_name is not None

        # Build signature
        decorators = self._extract_decorators(node, source)
        params_node = child_by_field_name(node, "parameters")
        params_text = self._get_text(params_node, source) if params_node else "()"
        return_type = ""
        ret_node = child_by_field_name(node, "return_type")
        if ret_node:
            return_type = f" -> {self._get_text(ret_node, source)}"

        sig_parts = []
        if decorators:
            sig_parts.extend(decorators)
        if is_method:
            sig_parts.append(f"def {func_name}{params_text}{return_type}")
        else:
            sig_parts.append(f"def {func_name}{params_text}{return_type}")
        signature = " ".join(sig_parts) if sig_parts else None

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

    def _extract_decorators(self, node, source: str) -> list[str]:
        decorators = []
        # Check if this node is inside a decorated_definition
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    decorators.append(f"@{self._get_text(child, source).lstrip('@')}")
        return decorators

    def _extract_class_bases(self, node, source: str) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type in ("identifier", "attribute"):
                        bases.append(self._get_text(arg, source))
        return bases

    def _get_text(self, node, source: str) -> str:
        if node is None:
            return ""
        start = node.start_byte
        end = node.end_byte
        return source[start:end]


def child_by_field_name(node, name: str):
    """Get a child node by its field name."""
    result = node.child_by_field_name(name)
    return result if result is not None else None
