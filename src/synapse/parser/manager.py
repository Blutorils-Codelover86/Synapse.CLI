"""Parser manager: orchestrates language detection, parsing, and database storage."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config.defaults import EXTENSION_LANGUAGE_MAP
from ..database.models import File, Symbol, FileImport, file_content_hash, utcnow
from .base import ParsedFile, ParsedSymbol, ParsedImport, SymbolType

logger = logging.getLogger("synapse.parser")

# Map from Synapse language names to parser language names
_LANGUAGE_PARSER_MAP = {
    "Python": "python",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
    "TSX": "tsx",
    "Dart": "dart",
}

# Map file extensions to whether they need the TSX parser
_TSX_EXTENSIONS = {".tsx", ".jsx"}


class ParserManager:
    """Manages language-specific parsers and stores results in the database."""

    def __init__(self):
        self._parsers = {}
        self._init_parsers()

    def _init_parsers(self):
        try:
            from .python_parser import PythonParser
            self._parsers["python"] = PythonParser()
        except ImportError as e:
            logger.warning(f"Python parser not available: {e}")

        try:
            from .javascript_parser import JavaScriptParser
            self._parsers["javascript"] = JavaScriptParser()
        except ImportError as e:
            logger.warning(f"JavaScript parser not available: {e}")

        try:
            from .typescript_parser import TypeScriptParser
            self._parsers["typescript"] = TypeScriptParser(tsx=False)
            self._parsers["tsx"] = TypeScriptParser(tsx=True)
        except ImportError as e:
            logger.warning(f"TypeScript parser not available: {e}")

        try:
            from .dart_parser import DartParser
            self._parsers["dart"] = DartParser()
        except ImportError as e:
            logger.warning(f"Dart parser not available: {e}")

    def get_parser_key(self, language: str) -> Optional[str]:
        """Get the parser key for a given language name."""
        return _LANGUAGE_PARSER_MAP.get(language)

    def can_parse(self, language: str) -> bool:
        """Check if we can parse files of this language."""
        key = self.get_parser_key(language)
        return key is not None and key in self._parsers

    def parse_source(self, source_code: str, language: str, file_ext: str = "") -> ParsedFile:
        """Parse source code and return structured results."""
        # Determine if this is a TSX/JSX file
        if file_ext.lower() in _TSX_EXTENSIONS:
            key = "tsx"
        else:
            key = self.get_parser_key(language)

        if key is None or key not in self._parsers:
            return ParsedFile(language=language, errors=[f"No parser for language: {language}"])

        parser = self._parsers[key]
        return parser.parse(source_code)

    def parse_file(self, file_path: Path, language: str) -> ParsedFile:
        """Parse a file from disk."""
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as e:
            return ParsedFile(language=language, errors=[f"Cannot read file: {e}"])

        _, ext = os.path.splitext(file_path.name)
        return self.parse_source(source, language, file_ext=ext)

    def store_parsed_file(
        self,
        db: Session,
        file_record: File,
        parsed: ParsedFile,
    ) -> dict:
        """
        Store parsed results into the database for a given file record.
        Handles incremental updates: removes old symbols/imports for this file,
        then inserts new ones.

        Returns a summary dict.
        """
        # Remove old symbols and imports for this file
        db.query(Symbol).filter(Symbol.file_id == file_record.id).delete()
        db.query(FileImport).filter(FileImport.file_id == file_record.id).delete()
        db.flush()

        # Insert new symbols — two-pass to resolve parent IDs
        symbol_name_to_id: dict[str, int] = {}
        symbols_to_insert = []

        for sym in parsed.symbols:
            symbols_to_insert.append(sym)

        # First pass: top-level symbols (no parent)
        for sym in symbols_to_insert:
            if sym.parent_name is None:
                db_sym = Symbol(
                    file_id=file_record.id,
                    name=sym.name,
                    symbol_type=sym.symbol_type.value,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    start_column=sym.start_column,
                    end_column=sym.end_column,
                    source_excerpt=None,
                    signature=sym.signature,
                    metadata_=sym.metadata if sym.metadata else None,
                )
                db.add(db_sym)
                db.flush()
                symbol_name_to_id[sym.name] = db_sym.id

        # Second pass: child symbols
        for sym in symbols_to_insert:
            if sym.parent_name is not None:
                parent_id = symbol_name_to_id.get(sym.parent_name)
                db_sym = Symbol(
                    file_id=file_record.id,
                    name=sym.name,
                    symbol_type=sym.symbol_type.value,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    start_column=sym.start_column,
                    end_column=sym.end_column,
                    source_excerpt=None,
                    signature=sym.signature,
                    parent_symbol_id=parent_id,
                    metadata_=sym.metadata if sym.metadata else None,
                )
                db.add(db_sym)
                db.flush()

        # Insert imports
        for imp in parsed.imports:
            db_import = FileImport(
                file_id=file_record.id,
                module_name=imp.module_name,
                import_type=imp.import_type,
                alias=imp.alias,
                line_number=imp.line_number,
                is_relative=1 if imp.is_relative else 0,
                metadata_=imp.metadata if imp.metadata else None,
            )
            db.add(db_import)

        db.flush()

        return {
            "classes": parsed.class_count,
            "functions": parsed.function_count,
            "methods": parsed.method_count,
            "components": parsed.component_count,
            "interfaces": parsed.interface_count,
            "imports": len(parsed.imports),
            "errors": len(parsed.errors),
        }


def parse_all_files(
    db: Session,
    workspace_id: int,
    progress_callback=None,
) -> dict:
    """
    Parse all source files in the workspace that have a supported language.
    Only re-parses files whose content_hash has changed or that have no symbols yet.

    Returns aggregate stats.
    """
    manager = ParserManager()

    # Get all files in the workspace
    from ..database.models import Project
    files = (
        db.query(File)
        .join(Project)
        .filter(Project.workspace_id == workspace_id)
        .all()
    )

    total = len(files)
    parsed_count = 0
    skipped_count = 0
    error_count = 0
    total_stats = {
        "classes": 0, "functions": 0, "methods": 0,
        "components": 0, "interfaces": 0, "imports": 0, "errors": 0,
    }

    # Group by language for progress
    lang_files: dict[str, list[File]] = {}
    for f in files:
        lang = f.language or "Unknown"
        if lang not in lang_files:
            lang_files[lang] = []
        lang_files[lang].append(f)

    for lang, lfiles in lang_files.items():
        if not manager.can_parse(lang):
            skipped_count += len(lfiles)
            continue

        if progress_callback:
            progress_callback(f"Parsing {lang} ({len(lfiles)} files)...")

        for fobj in lfiles:
            # Get the full file path
            proj = db.query(Project).filter(Project.id == fobj.project_id).first()
            if not proj:
                continue
            full_path = Path(proj.path) / fobj.path

            if not full_path.exists():
                continue

            # Check if we need to reparse: compare content hash with existing symbols
            existing_symbol_count = db.query(Symbol).filter(Symbol.file_id == fobj.id).count()
            needs_reparse = existing_symbol_count == 0

            if not needs_reparse:
                # Check if the file hash changed
                try:
                    new_hash = file_content_hash(full_path)
                    if new_hash == fobj.content_hash:
                        # File hasn't changed, skip
                        skipped_count += 1
                        continue
                    else:
                        needs_reparse = True
                except Exception:
                    needs_reparse = True

            if needs_reparse:
                parsed = manager.parse_file(full_path, lang)
                stats = manager.store_parsed_file(db, fobj, parsed)
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)
                parsed_count += 1

                if stats.get("errors", 0) > 0:
                    error_count += stats["errors"]

    db.commit()

    total_stats["parsed_files"] = parsed_count
    total_stats["skipped_files"] = skipped_count
    total_stats["error_files"] = error_count
    total_stats["total_files"] = total

    return total_stats
