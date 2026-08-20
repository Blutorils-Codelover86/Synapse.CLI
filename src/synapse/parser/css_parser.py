"""CSS source code parser using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_css as tscss

from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, SymbolType

_CSS_LANGUAGE = tree_sitter.Language(tscss.language())


class CSSParser(BaseParser):
    language = "CSS"

    def __init__(self):
        self._parser = tree_sitter.Parser(_CSS_LANGUAGE)

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
            result.errors.append("CSS contains syntax errors")

        return result

    def _extract_imports(self, node, source: str, result: ParsedFile):
        for child in node.children:
            if child.type == "import_statement":
                line = child.start_point[0] + 1
                module_name = self._extract_import_module(child, source)
                if module_name:
                    result.imports.append(ParsedImport(
                        module_name=module_name,
                        import_type="from",
                        line_number=line,
                        metadata={"statement": self._get_text(child, source).strip()},
                    ))
            elif child.type in ("stylesheet", "block", "keyframe_block_list"):
                self._extract_imports(child, source, result)

    def _extract_import_module(self, node, source: str) -> str:
        for child in node.children:
            if child.type == "call_expression":
                for arg in child.children:
                    if arg.type == "arguments":
                        for a in arg.children:
                            if a.type == "string_value":
                                return self._get_text(a, source).strip("'\"")
            elif child.type == "string_value":
                return self._get_text(child, source).strip("'\"")
        return ""

    def _extract_symbols(self, node, source: str, result: ParsedFile, parent_name: str | None):
        for child in node.children:
            if child.type == "rule_set":
                self._handle_rule_set(child, source, result, parent_name)
            elif child.type == "media_statement":
                self._handle_media_statement(child, source, result, parent_name)
            elif child.type == "keyframes_statement":
                self._handle_keyframes_statement(child, source, result, parent_name)

    def _handle_rule_set(self, node, source: str, result: ParsedFile, parent_name: str | None):
        selector_text = self._extract_selector_text(node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        result.symbols.append(ParsedSymbol(
            name=selector_text,
            symbol_type=SymbolType.SELECTOR,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=selector_text,
            metadata={"selector_kind": self._classify_selector(node, source)},
        ))

        block = self._find_child(node, "block")
        if block:
            self._extract_declarations(block, source, result, parent_name=selector_text)

    def _handle_media_statement(self, node, source: str, result: ParsedFile, parent_name: str | None):
        media_text = self._extract_media_text(node, source)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        result.symbols.append(ParsedSymbol(
            name=media_text,
            symbol_type=SymbolType.MEDIA_QUERY,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=media_text,
        ))

        block = self._find_child(node, "block")
        if block:
            self._extract_symbols(block, source, result, parent_name=media_text)

    def _handle_keyframes_statement(self, node, source: str, result: ParsedFile, parent_name: str | None):
        name_node = self._find_child(node, "keyframes_name")
        keyframes_name = self._get_text(name_node, source) if name_node else "@keyframes"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        result.symbols.append(ParsedSymbol(
            name=keyframes_name,
            symbol_type=SymbolType.KEYFRAMES,
            start_line=start_line,
            end_line=end_line,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            parent_name=parent_name,
            signature=f"@keyframes {keyframes_name}",
        ))

        block_list = self._find_child(node, "keyframe_block_list")
        if block_list:
            self._extract_keyframe_blocks(block_list, source, result, parent_name=keyframes_name)

    def _extract_keyframe_blocks(self, node, source: str, result: ParsedFile, parent_name: str):
        for child in node.children:
            if child.type == "keyframe_block":
                label = self._get_keyframe_label(child, source)
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                result.symbols.append(ParsedSymbol(
                    name=label,
                    symbol_type=SymbolType.SELECTOR,
                    start_line=start_line,
                    end_line=end_line,
                    start_column=child.start_point[1],
                    end_column=child.end_point[1],
                    parent_name=parent_name,
                    signature=label,
                    metadata={"selector_kind": "keyframe_stop"},
                ))

                block = self._find_child(child, "block")
                if block:
                    self._extract_declarations(block, source, result, parent_name=label)

    def _get_keyframe_label(self, node, source: str) -> str:
        for child in node.children:
            if child.type in ("from", "to"):
                text = self._get_text(child, source)
                if text:
                    return text
            elif child.type in ("integer_value", "float_value", "percentage"):
                text = self._get_text(child, source)
                if text:
                    return text
        return "keyframe"

    def _extract_declarations(self, block_node, source: str, result: ParsedFile, parent_name: str):
        for child in block_node.children:
            if child.type == "declaration":
                prop_node = self._find_child(child, "property_name")
                if not prop_node:
                    continue
                prop_name = self._get_text(prop_node, source)
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                result.symbols.append(ParsedSymbol(
                    name=prop_name,
                    symbol_type=SymbolType.PROPERTY,
                    start_line=start_line,
                    end_line=end_line,
                    start_column=child.start_point[1],
                    end_column=child.end_point[1],
                    parent_name=parent_name,
                    signature=self._get_text(child, source).strip(),
                ))

    def _extract_selector_text(self, rule_set_node, source: str) -> str:
        selectors_node = self._find_child(rule_set_node, "selectors")
        if not selectors_node:
            return ""
        return self._get_text(selectors_node, source).strip()

    def _classify_selector(self, rule_set_node, source: str) -> str:
        selectors_node = self._find_child(rule_set_node, "selectors")
        if not selectors_node:
            return "unknown"
        first = selectors_node.children[0] if selectors_node.children else None
        if first is None:
            return "unknown"
        kind = first.type
        if kind == "class_selector":
            return "class"
        if kind == "id_selector":
            return "id"
        if kind == "tag_name":
            return "tag"
        if kind == "pseudo_class_selector":
            return "pseudo"
        if kind in ("child_selector", "adjacent_sibling_selector", "sibling_selector", "descendant_selector"):
            return "compound"
        return "unknown"

    def _extract_media_text(self, node, source: str) -> str:
        query_types = ("feature_query", "keyword_query", "binary_query", "unary_query")
        parts = ["@media"]
        for child in node.children:
            if child.type == "block":
                break
            if child.type in query_types:
                parts.append(self._get_text(child, source).strip())
        return " ".join(parts)

    def _find_child(self, node, field_type: str):
        for child in node.children:
            if child.type == field_type:
                return child
        return None

    def _get_text(self, node, source: str) -> str:
        if node is None:
            return ""
        start = node.start_byte
        end = node.end_byte
        return source[start:end]
