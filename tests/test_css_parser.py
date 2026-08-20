"""Tests for the CSS parser."""

import pytest
from synapse.parser.css_parser import CSSParser
from synapse.parser.base import SymbolType


@pytest.fixture
def parser():
    return CSSParser()


class TestCSSParser:
    def test_tag_selector(self, parser):
        source = "body { margin: 0; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert selectors[0].name == "body"
        assert selectors[0].metadata["selector_kind"] == "tag"

    def test_class_selector(self, parser):
        source = ".container { width: 100%; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert ".container" in selectors[0].name
        assert selectors[0].metadata["selector_kind"] == "class"

    def test_id_selector(self, parser):
        source = "#main { display: flex; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert "#main" in selectors[0].name
        assert selectors[0].metadata["selector_kind"] == "id"

    def test_pseudo_selector(self, parser):
        source = "a:hover { color: red; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert selectors[0].metadata["selector_kind"] == "pseudo"

    def test_multiple_selectors(self, parser):
        source = "h1, h2, h3 { font-weight: bold; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        names = selectors[0].name
        assert "h1" in names and "h2" in names and "h3" in names

    def test_compound_selector(self, parser):
        source = "div > p { margin: 10px; }"
        result = parser.parse(source)
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert selectors[0].metadata["selector_kind"] == "compound"

    def test_declarations(self, parser):
        source = ".box { color: blue; font-size: 14px; margin: 0 auto; }"
        result = parser.parse(source)
        props = [s for s in result.symbols if s.symbol_type == SymbolType.PROPERTY]
        prop_names = [p.name for p in props]
        assert "color" in prop_names
        assert "font-size" in prop_names
        assert "margin" in prop_names

    def test_import(self, parser):
        source = '@import url("reset.css");'
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert "reset.css" in result.imports[0].module_name

    def test_media_with_nested_rules(self, parser):
        source = "@media (max-width: 600px) { .sidebar { display: none; } }"
        result = parser.parse(source)
        media = [s for s in result.symbols if s.symbol_type == SymbolType.MEDIA_QUERY]
        assert len(media) == 1
        selectors = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        assert len(selectors) == 1
        assert selectors[0].parent_name == media[0].name

    def test_keyframes(self, parser):
        source = "@keyframes fade { from { opacity: 0; } to { opacity: 1; } }"
        result = parser.parse(source)
        kf = [s for s in result.symbols if s.symbol_type == SymbolType.KEYFRAMES]
        assert len(kf) == 1
        assert kf[0].name == "fade"
        stops = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR and s.parent_name == "fade"]
        assert len(stops) == 2
        stop_names = [s.name for s in stops]
        assert "from" in stop_names
        assert "to" in stop_names

    def test_keyframes_percent(self, parser):
        source = "@keyframes slide { 0% { left: 0; } 50% { left: 50px; } 100% { left: 100px; } }"
        result = parser.parse(source)
        stops = [s for s in result.symbols if s.symbol_type == SymbolType.SELECTOR]
        stop_names = [s.name for s in stops]
        assert any("0" in n for n in stop_names)
        assert any("50" in n for n in stop_names)
        assert any("100" in n for n in stop_names)

    def test_malformed_css(self, parser):
        source = ".broken { color: } .valid { display: block; }"
        result = parser.parse(source)
        assert len(result.errors) > 0

    def test_empty_file(self, parser):
        source = ""
        result = parser.parse(source)
        assert len(result.symbols) == 0
        assert len(result.imports) == 0
        assert len(result.errors) == 0

    def test_repeated_parsing(self, parser):
        source = ".a { color: red; } .b { color: blue; }"
        r1 = parser.parse(source)
        r2 = parser.parse(source)
        assert len(r1.symbols) == len(r2.symbols)
        assert len(r1.imports) == len(r2.imports)
