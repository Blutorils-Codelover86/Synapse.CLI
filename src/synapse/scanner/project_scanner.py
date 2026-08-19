"""Project scanner: discovers projects, files, and metadata from a root folder."""

from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config.defaults import (
    IGNORED_DIRS,
    IGNORED_EXTENSIONS,
    IGNORED_FILENAMES,
    PROJECT_INDICATORS,
    EXTENSION_LANGUAGE_MAP,
    SOURCE_EXTENSIONS,
)
from ..database.models import (
    Workspace, Project, File, Technology, init_db, file_content_hash, utcnow,
)


def _should_ignore_dir(name: str) -> bool:
    """Check if a directory name should be ignored."""
    if name in IGNORED_DIRS:
        return True
    for pattern in IGNORED_DIRS:
        if "*" in pattern and fnmatch.fnmatch(name, pattern):
            return True
    return False


def _should_ignore_file(name: str) -> bool:
    """Check if a file should be ignored by name or extension."""
    if name in IGNORED_FILENAMES:
        return True
    _, ext = os.path.splitext(name)
    if ext.lower() in IGNORED_EXTENSIONS:
        return True
    return False


def _detect_language(file_path: Path) -> Optional[str]:
    """Detect the programming language of a file from its extension."""
    _, ext = os.path.splitext(file_path.name)
    # Handle special cases like Dockerfile
    if file_path.name.lower() == "dockerfile":
        return "Dockerfile"
    return EXTENSION_LANGUAGE_MAP.get(ext.lower())


def _is_source_file(file_path: Path) -> bool:
    """Check if a file is a source code file worth indexing."""
    _, ext = os.path.splitext(file_path.name)
    return ext.lower() in SOURCE_EXTENSIONS


def _read_project_metadata(project_path: Path, indicators: list[str]) -> dict:
    """Read metadata from project indicator files."""
    meta: dict = {}
    for indicator in indicators:
        fpath = project_path / indicator
        if not fpath.exists():
            continue
        try:
            if indicator == "package.json":
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                meta["name"] = data.get("name", "")
                meta["description"] = data.get("description", "")
                meta["version"] = data.get("version", "")
                deps = {}
                deps.update(data.get("dependencies", {}))
                deps.update(data.get("devDependencies", {}))
                meta["dependencies"] = list(deps.keys())
            elif indicator == "pyproject.toml":
                content = fpath.read_text(encoding="utf-8", errors="replace")
                # Basic TOML parsing for project name
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("name"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            meta["name"] = parts[1].strip().strip('"').strip("'")
                    elif line.startswith("description"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            meta["description"] = parts[1].strip().strip('"').strip("'")
            elif indicator == "Cargo.toml":
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("name"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            meta["name"] = parts[1].strip().strip('"').strip("'")
                    elif line.startswith("description"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            meta["description"] = parts[1].strip().strip('"').strip("'")
            elif indicator == "go.mod":
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("module"):
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            meta["name"] = parts[1].strip()
            elif indicator == "pubspec.yaml":
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("name:"):
                        meta["name"] = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith("description:"):
                        meta["description"] = stripped.split(":", 1)[1].strip()
        except Exception:
            continue
    return meta


def _detect_technologies(project_path: Path, project_type: str, indicators: list[str]) -> list[dict[str, str]]:
    """Detect technologies used by a project."""
    techs = []
    seen = set()

    def _add(name: str, category: str):
        key = (name.lower(), category)
        if key not in seen:
            seen.add(key)
            techs.append({"name": name, "category": category})

    # Language from project type
    type_lang_map = {
        "python": "Python",
        "node": "JavaScript",
        "rust": "Rust",
        "go": "Go",
        "java": "Java",
        "flutter": "Dart",
        "ruby": "Ruby",
        "dotnet": "C#",
        "c_cpp": "C/C++",
    }
    if project_type in type_lang_map:
        _add(type_lang_map[project_type], "language")

    # Detect from file extensions present
    lang_counts: dict[str, int] = {}
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not _should_ignore_dir(d)]
            for fname in files:
                if _should_ignore_file(fname):
                    continue
                lang = _detect_language(Path(fname))
                if lang and lang not in ("HTML", "CSS", "JSON", "YAML", "TOML", "Markdown", "XML"):
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
            # Limit scan depth for performance
            depth = Path(root).relative_to(project_path).parts
            if len(depth) > 4:
                dirs.clear()
    except PermissionError:
        pass

    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        _add(lang, "language")

    # Detect frameworks from files present
    framework_indicators = {
        "next.config": "Next.js",
        "nuxt.config": "Nuxt.js",
        "vite.config": "Vite",
        "webpack.config": "Webpack",
        "angular.json": "Angular",
        "svelte.config": "SvelteKit",
        "remix.config": "Remix",
        "astro.config": "Astro",
        "flutter": "Flutter",
        "dart": "Dart",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "express": "Express",
        "spring": "Spring",
        "rails": "Rails",
        "laravel": "Laravel",
    }

    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not _should_ignore_dir(d)]
            for fname in files:
                fname_lower = fname.lower()
                for indicator, framework in framework_indicators.items():
                    if indicator in fname_lower:
                        _add(framework, "framework")
            depth = Path(root).relative_to(project_path).parts
            if len(depth) > 3:
                dirs.clear()
    except PermissionError:
        pass

    # Detect dependencies from package.json / requirements
    try:
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            with open(pkg_json, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            for dep in list(data.get("dependencies", {}).keys()):
                _add(dep, "dependency")
            for dep in list(data.get("devDependencies", {}).keys()):
                _add(dep, "dependency")
    except Exception:
        pass

    try:
        req = project_path / "requirements.txt"
        if req.exists():
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    name = line.split("==")[0].split(">=")[0].split("<=")[0].split("!=")[0].strip()
                    if name:
                        _add(name, "dependency")
    except Exception:
        pass

    return techs


def discover_projects(root_path: Path) -> list[dict]:
    """
    Walk the root path and discover coding projects.
    Returns a list of project info dicts.
    """
    projects = []

    def _walk(path: Path, depth: int = 0):
        if depth > 10:
            return
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return

        # Check if current directory IS a project
        found_indicators = []
        for entry in entries:
            if entry.name in PROJECT_INDICATORS:
                found_indicators.append(entry.name)

        if found_indicators:
            # Determine primary project type
            project_type = None
            for indicator in found_indicators:
                if indicator in PROJECT_INDICATORS:
                    project_type = PROJECT_INDICATORS[indicator]
                    if indicator != ".git":  # Prefer non-.git indicators
                        break

            projects.append({
                "path": path,
                "indicators": found_indicators,
                "project_type": project_type,
            })
            # Don't recurse into this project's subdirectories looking for more projects
            # unless they have their own indicators (monorepo)
            for entry in entries:
                if entry.is_dir() and not _should_ignore_dir(entry.name):
                    # Only check one level deep for nested projects in monorepos
                    _walk(entry, depth + 1)
        else:
            # Not a project root, keep walking
            for entry in entries:
                if entry.is_dir() and not _should_ignore_dir(entry.name):
                    _walk(entry, depth + 1)

    _walk(root_path)
    return projects


def _collect_source_files(project_path: Path) -> list[Path]:
    """Collect all source files in a project, respecting ignore rules."""
    source_files = []
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not _should_ignore_dir(d)]
            for fname in files:
                if _should_ignore_file(fname):
                    continue
                fpath = Path(root) / fname
                if _is_source_file(fpath):
                    source_files.append(fpath)
            depth = Path(root).relative_to(project_path).parts
            if len(depth) > 8:
                dirs.clear()
    except PermissionError:
        pass
    return source_files


def scan_workspace(
    root_path: str | Path,
    db: Session,
    progress_callback=None,
    parse_callback=None,
) -> Workspace:
    """
    Main entry point: scan a folder, discover projects, index files,
    store everything in the database.
    """
    root_path = Path(root_path).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")

    init_db()

    # Create or get workspace
    synapse_dir = str(root_path / ".synapse")
    workspace = db.query(Workspace).filter(Workspace.root_path == str(root_path)).first()
    if workspace is None:
        workspace = Workspace(
            root_path=str(root_path),
            synapse_dir=synapse_dir,
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    else:
        workspace.last_scan = utcnow()
        db.commit()

    # Discover projects
    if progress_callback:
        progress_callback("Discovering projects...")

    raw_projects = discover_projects(root_path)
    total = len(raw_projects)

    for idx, proj_info in enumerate(raw_projects):
        proj_path: Path = proj_info["path"]
        proj_name = proj_path.name
        indicators = proj_info["indicators"]
        project_type = proj_info["project_type"]

        if progress_callback:
            progress_callback(f"Scanning project {idx+1}/{total}: {proj_name}")

        # Get or create project
        existing = db.query(Project).filter(
            Project.workspace_id == workspace.id,
            Project.path == str(proj_path),
        ).first()

        if existing:
            proj = existing
            proj.last_modified = utcnow()
        else:
            proj = Project(
                workspace_id=workspace.id,
                name=proj_name,
                path=str(proj_path),
                project_type=project_type,
                last_modified=utcnow(),
            )
            db.add(proj)
            db.commit()
            db.refresh(proj)

        # Read metadata
        meta = _read_project_metadata(proj_path, indicators)
        proj.metadata_ = meta
        if meta.get("description"):
            proj.description = meta["description"]
        if meta.get("name"):
            proj.name = meta["name"]
        db.commit()

        # Collect technologies
        db.query(Technology).filter(Technology.project_id == proj.id).delete()
        techs = _detect_technologies(proj_path, project_type, indicators)
        for tech in techs:
            db.add(Technology(
                project_id=proj.id,
                name=tech["name"],
                category=tech["category"],
            ))
        db.commit()

        # Collect source files
        source_files = _collect_source_files(proj_path)
        for fpath in source_files:
            rel_path = str(fpath.relative_to(proj_path))
            lang = _detect_language(fpath)
            try:
                stat = fpath.stat()
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                c_hash = file_content_hash(fpath)
            except (OSError, PermissionError):
                size = 0
                mtime = None
                c_hash = None

            existing_file = db.query(File).filter(
                File.project_id == proj.id,
                File.path == rel_path,
            ).first()

            if existing_file:
                if existing_file.content_hash != c_hash:
                    existing_file.size = size
                    existing_file.language = lang
                    existing_file.content_hash = c_hash
                    existing_file.last_modified = mtime
            else:
                db.add(File(
                    project_id=proj.id,
                    path=rel_path,
                    language=lang,
                    size=size,
                    content_hash=c_hash,
                    last_modified=mtime,
                ))
        db.commit()

    workspace.last_scan = utcnow()
    db.commit()

    # Run code intelligence parsing if callback provided
    if parse_callback:
        parse_callback(workspace)

    return workspace
