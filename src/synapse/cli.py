"""Synapse CLI — entry point for all commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import __version__
from .database.models import (
    init_db, get_db, Workspace, Project, File, Symbol, Technology, Relationship,
)
from .scanner.project_scanner import scan_workspace

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

            workspace = scan_workspace(target, db, progress_callback=on_progress)
            progress.update(task, description="Done!")

        # Summary
        project_count = db.query(Project).filter(Project.workspace_id == workspace.id).count()
        file_count = db.query(File).join(Project).filter(Project.workspace_id == workspace.id).count()
        tech_count = db.query(Technology).join(Project).filter(Project.workspace_id == workspace.id).count()

        console.print()
        console.print(Panel(
            f"[bold green]Scan complete![/]\n\n"
            f"Projects found:   [cyan]{project_count}[/]\n"
            f"Source files:     [cyan]{file_count}[/]\n"
            f"Technologies:     [cyan]{tech_count}[/]\n"
            f"Database:         [dim]~/.synapse/synapse.db[/]",
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
        symbol_count = db.query(Symbol).join(File).join(Project).filter(
            Project.workspace_id == workspace.id
        ).count()
        tech_count = db.query(Technology).join(Project).filter(
            Project.workspace_id == workspace.id
        ).count()
        rel_count = db.query(Relationship).count()

        # Language breakdown
        from sqlalchemy import func
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
        table.add_row("Symbols", str(symbol_count))
        table.add_row("Technologies", str(tech_count))
        table.add_row("Relationships", str(rel_count))
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
    """Incrementally update changed files in the workspace (Phase 2+)."""
    db = get_db()
    try:
        workspace = db.query(Workspace).order_by(Workspace.last_scan.desc()).first()
        if not workspace:
            console.print("[yellow]No workspace found.[/] Run [bold]synapse scan PATH[/] first.")
            raise typer.Exit(0)
        console.print(f"[cyan]Updating workspace:[/] {workspace.root_path}")
        console.print("[dim]Incremental update not yet implemented — coming in Phase 2.[/]")
    finally:
        db.close()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Synapse — Local Semantic Coding Universe."""
    if ctx.invoked_subcommand is None:
        # No subcommand: try to open the most recent workspace
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
