"""Synapse CLI — entry point for all commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree as RichTree

from . import __version__
from .database.models import (
    init_db, get_db, Workspace, Project, File, Symbol, Technology,
    Relationship, FileImport,
)
from .scanner.project_scanner import scan_workspace
from .parser.manager import parse_all_files, ParserManager

app = typer.Typer(
    name="synapse",
    help="Synapse — Local Semantic Coding Universe",
    no_args_is_help=False,
)
console = Console()


@app.command()
def scan(
    path: str = typer.Argument(..., help="Root folder path to scan"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
) -> None:
    """Scan a folder and index coding projects into the Synapse workspace."""
    target = Path(path).resolve()
    if not target.exists():
        console.print(f"[red]Error:[/] Path does not exist: {target}")
        raise typer.Exit(1)
    if not target.is_dir():
        console.print(f"[red]Error:[/] Path is not a directory: {target}")
        raise typer.Exit(1)

    console.print(Panel(f"[bold cyan]Synapse Scan[/]\nPath: {target}", border_style="cyan"))

    db = get_db()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning...", total=None)

            def on_progress(msg: str):
                progress.update(task, description=msg)

            def on_parse(workspace):
                progress.update(task, description="Analyzing code structure...")
                parse_all_files(db, workspace.id, progress_callback=on_progress)

            workspace = scan_workspace(target, db, progress_callback=on_progress, parse_callback=on_parse)
            progress.update(task, description="Done!")

        # Summary
        project_count = db.query(Project).filter(Project.workspace_id == workspace.id).count()
        file_count = db.query(File).join(Project).filter(Project.workspace_id == workspace.id).count()
        tech_count = db.query(Technology).join(Project).filter(Project.workspace_id == workspace.id).count()

        # Symbol stats
        from sqlalchemy import func
        sym_stats = (
            db.query(Symbol.symbol_type, func.count(Symbol.id))
            .join(File)
            .join(Project)
            .filter(Project.workspace_id == workspace.id)
            .group_by(Symbol.symbol_type)
            .all()
        )
        import_count = (
            db.query(func.count(FileImport.id))
            .join(File)
            .join(Project)
            .filter(Project.workspace_id == workspace.id)
            .scalar()
        )

        sym_dict = {s: c for s, c in sym_stats}

        console.print()
        lines = []
        lines.append(f"Projects found:   [cyan]{project_count}[/]")
        lines.append(f"Source files:     [cyan]{file_count}[/]")
        lines.append(f"Technologies:     [cyan]{tech_count}[/]")
        lines.append("")
        lines.append("[bold]Code Intelligence:[/]")
        lines.append(f"  Classes:        [cyan]{sym_dict.get('class', 0)}[/]")
        lines.append(f"  Functions:      [cyan]{sym_dict.get('function', 0)}[/]")
        lines.append(f"  Methods:        [cyan]{sym_dict.get('method', 0)}[/]")
        lines.append(f"  Components:     [cyan]{sym_dict.get('component', 0)}[/]")
        lines.append(f"  Interfaces:     [cyan]{sym_dict.get('interface', 0)}[/]")
        lines.append(f"  Enums:          [cyan]{sym_dict.get('enum', 0)}[/]")
        lines.append(f"  Imports:        [cyan]{import_count}[/]")
        lines.append("")
        lines.append(f"Database:         [dim]~/.synapse/synapse.db[/]")

        console.print(Panel(
            "\n".join(lines),
            title="Summary",
            border_style="green",
        ))
    finally:
        db.close()


@app.command()
def info() -> None:
    """Display statistics about the current Synapse workspace."""
    db = get_db()
    try:
        workspace = db.query(Workspace).order_by(Workspace.last_scan.desc()).first()
        if not workspace:
            console.print("[yellow]No workspace found.[/] Run [bold]synapse scan PATH[/] first.")
            raise typer.Exit(0)

        project_count = db.query(Project).filter(Project.workspace_id == workspace.id).count()
        file_count = db.query(File).join(Project).filter(Project.workspace_id == workspace.id).count()

        # Symbol breakdown
        from sqlalchemy import func
        sym_stats = (
            db.query(Symbol.symbol_type, func.count(Symbol.id))
            .join(File)
            .join(Project)
            .filter(Project.workspace_id == workspace.id)
            .group_by(Symbol.symbol_type)
            .all()
        )
        sym_dict = {s: c for s, c in sym_stats}
        total_symbols = sum(sym_dict.values())

        import_count = (
            db.query(func.count(FileImport.id))
            .join(File)
            .join(Project)
            .filter(Project.workspace_id == workspace.id)
            .scalar()
        )

        tech_count = db.query(Technology).join(Project).filter(
            Project.workspace_id == workspace.id
        ).count()
        rel_count = db.query(Relationship).count()

        # Language breakdown
        lang_stats = (
            db.query(File.language, func.count(File.id))
            .join(Project)
            .filter(Project.workspace_id == workspace.id, File.language.isnot(None))
            .group_by(File.language)
            .order_by(func.count(File.id).desc())
            .all()
        )

        table = Table(title="Synapse Workspace Info", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="cyan")

        table.add_row("Workspace path", workspace.root_path)
        table.add_row("Created", str(workspace.created_at))
        table.add_row("Last scan", str(workspace.last_scan))
        table.add_row("Projects", str(project_count))
        table.add_row("Source files", str(file_count))
        table.add_row("Languages detected", str(len(lang_stats)))
        table.add_row("Technologies", str(tech_count))
        table.add_row("Relationships", str(rel_count))
        table.add_row("", "")
        table.add_row("[bold]Code Intelligence", "")
        table.add_row("  Total symbols", str(total_symbols))
        table.add_row("  Classes", str(sym_dict.get("class", 0)))
        table.add_row("  Functions", str(sym_dict.get("function", 0)))
        table.add_row("  Methods", str(sym_dict.get("method", 0)))
        table.add_row("  Components", str(sym_dict.get("component", 0)))
        table.add_row("  Interfaces", str(sym_dict.get("interface", 0)))
        table.add_row("  Enums", str(sym_dict.get("enum", 0)))
        table.add_row("  Imports / dependencies", str(import_count))
        table.add_row("", "")
        table.add_row("Database", "~/.synapse/synapse.db")

        console.print(table)

        if lang_stats:
            lang_table = Table(title="Languages", border_style="dim")
            lang_table.add_column("Language", style="bold")
            lang_table.add_column("Files", justify="right", style="cyan")
            for lang, count in lang_stats:
                lang_table.add_row(lang, str(count))
            console.print(lang_table)

    finally:
        db.close()


@app.command()
def inspect(
    file_path: str = typer.Argument(..., help="Path to a source file to inspect"),
) -> None:
    """Inspect parsed symbols and imports for a specific file."""
    target = Path(file_path).resolve()
    if not target.exists():
        console.print(f"[red]Error:[/] File does not exist: {target}")
        raise typer.Exit(1)
    if not target.is_dir():
        if not target.is_file():
            console.print(f"[red]Error:[/] Not a file: {target}")
            raise typer.Exit(1)

    # Detect language
    from .config.defaults import EXTENSION_LANGUAGE_MAP
    _, ext = os.path.splitext(target.name)
    language = EXTENSION_LANGUAGE_MAP.get(ext.lower())

    if not language:
        console.print(f"[yellow]Warning:[/] No language detected for extension '{ext}'")
        console.print("[dim]Attempting parse anyway...[/]")

    # Parse the file
    manager = ParserManager()
    parsed = manager.parse_file(target, language or "Unknown")

    # Display results
    console.print(Panel(f"[bold cyan]File:[/] {target.name}", border_style="cyan"))

    if language:
        console.print(f"\n[bold]Language:[/] [cyan]{language}[/]")

    # Imports
    if parsed.imports:
        console.print("\n[bold]Imports:[/]")
        for imp in parsed.imports:
            alias_str = f" as {imp.alias}" if imp.alias else ""
            rel_str = " [dim](relative)[/]" if imp.is_relative else ""
            console.print(f"  - [green]{imp.module_name}[/]{alias_str}{rel_str}")

    # Symbols as tree
    if parsed.symbols:
        console.print("\n[bold]Symbols:[/]")
        # Build tree structure: top-level symbols first, then children
        top_level = [s for s in parsed.symbols if s.parent_name is None]
        children_map: dict[str, list] = {}
        for s in parsed.symbols:
            if s.parent_name:
                children_map.setdefault(s.parent_name, []).append(s)

        for sym in top_level:
            _print_symbol_tree(console, sym, children_map, depth=1)

    # Errors
    if parsed.errors:
        console.print("\n[bold red]Errors:[/]")
        for err in parsed.errors:
            console.print(f"  [red]{err}[/]")

    if not parsed.symbols and not parsed.imports and not parsed.errors:
        console.print("\n[dim]No symbols or imports found.[/]")


def _print_symbol_tree(console, sym, children_map: dict, depth: int = 0):
    """Print a symbol and its children as a tree."""
    type_colors = {
        "class": "yellow",
        "function": "green",
        "method": "cyan",
        "component": "magenta",
        "interface": "blue",
        "enum": "red",
    }
    color = type_colors.get(sym.symbol_type, "white")
    type_label = f"[{color}]{sym.symbol_type}[/{color}]"
    sig_str = f" [dim]{sym.signature}[/]" if sym.signature else ""
    line_range = f" [dim]L{sym.start_line}-{sym.end_line}[/]"

    prefix = "  " * depth
    connector = "├── " if depth > 0 else ""
    console.print(f"{prefix}{connector}[bold]{sym.name}[/] {type_label}{sig_str}{line_range}")

    children = children_map.get(sym.name, [])
    for child in children:
        _print_symbol_tree(console, child, children_map, depth + 1)


@app.command()
def open(
    port: int = typer.Option(8420, "--port", "-p", help="Port for the local server"),
) -> None:
    """Open the Synapse workspace in the browser (Phase 4+)."""
    db = get_db()
    try:
        workspace = db.query(Workspace).order_by(Workspace.last_scan.desc()).first()
        if not workspace:
            console.print("[yellow]No workspace found.[/] Run [bold]synapse scan PATH[/] first.")
            raise typer.Exit(0)
        console.print(f"[cyan]Opening workspace:[/] {workspace.root_path}")
        console.print("[dim]Server not yet implemented — coming in Phase 4.[/]")
    finally:
        db.close()


@app.command()
def update() -> None:
    """Incrementally update changed files in the workspace."""
    db = get_db()
    try:
        workspace = db.query(Workspace).order_by(Workspace.last_scan.desc()).first()
        if not workspace:
            console.print("[yellow]No workspace found.[/] Run [bold]synapse scan PATH[/] first.")
            raise typer.Exit(0)

        console.print(f"[cyan]Updating workspace:[/] {workspace.root_path}")

        # Re-scan with parsing
        root_path = Path(workspace.root_path).resolve()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Updating...", total=None)

            def on_progress(msg: str):
                progress.update(task, description=msg)

            def on_parse(ws):
                progress.update(task, description="Re-analyzing changed files...")
                parse_all_files(db, ws.id, progress_callback=on_progress)

            scan_workspace(root_path, db, progress_callback=on_progress, parse_callback=on_parse)
            progress.update(task, description="Done!")

        console.print("[bold green]Update complete![/]")
    finally:
        db.close()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Synapse — Local Semantic Coding Universe."""
    if ctx.invoked_subcommand is None:
        db = get_db()
        try:
            workspace = db.query(Workspace).order_by(Workspace.last_scan.desc()).first()
            if workspace:
                console.print(f"[cyan]Found workspace:[/] {workspace.root_path}")
                console.print("[dim]Run [bold]synapse open[/bold] to launch the server.[/]")
            else:
                console.print(
                    "[yellow]No workspace found.[/]\n\n"
                    "Get started by scanning a folder:\n"
                    "  [bold]synapse scan /path/to/your/projects[/]"
                )
        finally:
            db.close()


if __name__ == "__main__":
    app()
