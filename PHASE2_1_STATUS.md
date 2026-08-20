# SYNAPSE — PHASE 2.1 WORK STATUS

Last updated: 2026-08-20

## Summary

Phase 2.1 is **COMPLETE**. CSS and Rust parsers are fully registered, tested, and working. All 82 tests passing (up from 57 baseline).

## What Was Done

1. **`src/synapse/parser/manager.py`** — Registered CSS + Rust parsers:
   - Added `"CSS": "css"` and `"Rust": "rust"` to `_LANGUAGE_PARSER_MAP`.
   - Imported + registered `CSSParser` and `RustParser` in `_init_parsers` with try/except ImportError.
   - Fixed `store_parsed_file` nested parent-child resolution: replaced two-pass approach with single-pass, `symbol_name_to_id` dict now updated for all symbols (not just top-level), enabling multi-level nesting (CSS media→selector→property, Rust impl→method).

2. **`pyproject.toml`** — Added `tree-sitter-css>=0.20.0` and `tree-sitter-rust>=0.23.0` to dependencies.

3. **`src/synapse/cli.py`** — Added colors for new symbol types in `_print_symbol_tree`: selector, media_query, keyframes, property, struct, trait, module, variable.

4. **`tests/test_parser_manager.py`** — Fixed:
   - `test_cannot_parse_rust` → `test_can_parse_rust` (asserts Rust is supported).
   - Added `test_can_parse_css`.
   - `test_parse_unsupported_language` switched from "Rust" to "Go".

5. **`tests/test_css_parser.py`** — Created with 13 test cases: tag/class/ID/pseudo/multiple/compound selectors, declarations, @import, @media with nested rules, @keyframes (from/to + percent), malformed CSS, empty file, repeated parsing.

6. **`tests/test_rust_parser.py`** — Created with 10 test cases: use statements, structs, enums, traits, standalone functions, impl blocks, methods, parent relationships, malformed Rust, empty file.

## Test Results

```
82 passed in 1.76s
```

## Files Modified

- `src/synapse/parser/manager.py`
- `pyproject.toml`
- `src/synapse/cli.py`
- `tests/test_parser_manager.py`

## Files Created

- `tests/test_css_parser.py`
- `tests/test_rust_parser.py`

## Files Previously Created (Phase 2.1 prep)

- `src/synapse/parser/css_parser.py`
- `src/synapse/parser/rust_parser.py`
