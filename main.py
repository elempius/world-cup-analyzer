import os
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

app = typer.Typer(
    help="World Cup 2026 match analyzer powered by AI.",
    no_args_is_help=True,
)
console = Console()


def _get_api() -> tuple:
    football_key = os.getenv("FOOTBALL_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    league_id = int(os.getenv("WC_LEAGUE_ID", "1"))
    season = int(os.getenv("WC_SEASON", "2026"))

    missing = []
    if not football_key:
        missing.append("FOOTBALL_API_KEY")
    if not openrouter_key:
        missing.append("OPENROUTER_API_KEY")
    if missing:
        console.print(f"[red]Missing env vars: {', '.join(missing)}[/red]")
        console.print("Copy [bold].env.example[/bold] to [bold].env[/bold] and fill in your keys.")
        raise typer.Exit(1)

    from api.football import FootballAPI
    model = os.getenv("OPENROUTER_MODEL")
    if not model:
        missing.append("OPENROUTER_MODEL")
    return FootballAPI(football_key, league_id=league_id, season=season), openrouter_key, model


def _resolve_team(api, name: str) -> Optional[object]:
    from api.models import Team

    with console.status(f"Searching for [bold]{name}[/bold]..."):
        results = api.search_team(name)

    if not results:
        console.print(f"[red]No team found matching '{name}'.[/red]")
        console.print("Tip: try a shorter name or the official English name (e.g. 'Morocco', 'United States').")
        return None

    if len(results) == 1:
        console.print(f"  [green]✓[/green] Found: [bold]{results[0].name}[/bold] (ID {results[0].id})")
        return results[0]

    # Multiple results — show options and pick the first plausible national team
    national = [t for t in results if t.code and len(t.code) <= 3]
    if national:
        team = national[0]
        console.print(f"  [green]✓[/green] Found: [bold]{team.name}[/bold] (ID {team.id})")
        return team

    console.print(f"\n[yellow]Multiple matches for '{name}':[/yellow]")
    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim")
    table.add_column("Team")
    table.add_column("Code")
    table.add_column("ID", style="dim")
    for i, t in enumerate(results[:8], 1):
        table.add_row(str(i), t.name, t.code or "-", str(t.id))
    console.print(table)

    choice = typer.prompt("Pick number", default="1")
    try:
        idx = int(choice) - 1
        return results[idx]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice.[/red]")
        return None


@app.command()
def fixtures(
    days: int = typer.Option(14, "-d", "--days", help="How many days ahead to display"),
    all: bool = typer.Option(False, "-a", "--all", help="Show all fixtures including finished"),
):
    """List upcoming World Cup 2026 fixtures."""
    api, _, _model = _get_api()

    with console.status("Fetching World Cup fixtures..."):
        wc_fixtures = api.get_wc_fixtures()

    now = datetime.now(timezone.utc)

    filtered = []
    for f in wc_fixtures:
        try:
            dt = datetime.fromisoformat(f.date.replace("Z", "+00:00"))
        except ValueError:
            continue
        delta = (dt - now).total_seconds() / 86400
        if all or (-1 <= delta <= days):
            filtered.append((dt, f))

    filtered.sort(key=lambda x: x[0])

    if not filtered:
        console.print(f"[yellow]No fixtures found in the next {days} days.[/yellow]")
        return

    table = Table(
        title=f"[bold]World Cup 2026 Fixtures[/bold]",
        box=box.ROUNDED,
        show_lines=False,
    )
    table.add_column("Date", style="cyan", min_width=10)
    table.add_column("Time (UTC)", style="dim", min_width=9)
    table.add_column("Home", justify="right", min_width=18)
    table.add_column("Score", justify="center", min_width=7)
    table.add_column("Away", justify="left", min_width=18)
    table.add_column("Round", style="dim", min_width=20)

    status_style = {"FT": "dim", "LIVE": "bold green", "NS": "white", "1H": "bold green", "2H": "bold green"}

    for dt, f in filtered:
        date_str = dt.strftime("%b %d")
        time_str = dt.strftime("%H:%M")
        if f.home_goals is not None and f.away_goals is not None:
            score = f"[bold]{f.home_goals} - {f.away_goals}[/bold]"
        else:
            score = "[dim]vs[/dim]"
        style = status_style.get(f.status, "white")
        table.add_row(date_str, time_str, f.home_team.name, score, f.away_team.name, f.round, style=style if f.status == "LIVE" else None)

    console.print(table)
    console.print(f"[dim]Showing {len(filtered)} fixture(s). Use --all to include all matches.[/dim]")


@app.command()
def analyze(
    team1: str = typer.Argument(..., help="First team name"),
    team2: str = typer.Argument(..., help="Second team name"),
    form: int = typer.Option(5, "-f", "--form", help="Number of recent matches to fetch per team"),
    h2h_count: int = typer.Option(10, "--h2h", help="Number of H2H matches to fetch"),
):
    """Analyze a matchup and predict the outcome using AI."""
    api, openrouter_key, model = _get_api()

    from ai.analyzer import build_prompt, stream_analysis

    # Resolve teams
    console.print(Panel.fit("[bold cyan]World Cup 2026 — Match Analyzer[/bold cyan]"))
    console.print()

    t1 = _resolve_team(api, team1)
    if not t1:
        raise typer.Exit(1)
    t2 = _resolve_team(api, team2)
    if not t2:
        raise typer.Exit(1)

    console.print()

    # Fetch all data with status updates
    with console.status(f"Fetching {t1.name} recent form..."):
        t1_form = api.get_team_form(t1.id, last=form)
    console.print(f"  [green]✓[/green] {t1.name}: {len(t1_form)} recent matches")

    with console.status(f"Fetching {t2.name} recent form..."):
        t2_form = api.get_team_form(t2.id, last=form)
    console.print(f"  [green]✓[/green] {t2.name}: {len(t2_form)} recent matches")

    with console.status(f"Fetching {t1.name} tournament stats..."):
        t1_stats = api.get_team_stats(t1.id)
    console.print(f"  [green]✓[/green] {t1.name} stats: {'available' if t1_stats else 'not yet available'}")

    with console.status(f"Fetching {t2.name} tournament stats..."):
        t2_stats = api.get_team_stats(t2.id)
    console.print(f"  [green]✓[/green] {t2.name} stats: {'available' if t2_stats else 'not yet available'}")

    with console.status("Fetching head-to-head history..."):
        h2h = api.get_h2h(t1.id, t2.id, last=h2h_count)
    console.print(f"  [green]✓[/green] H2H: {len(h2h)} historical meetings found")

    with console.status("Fetching group standings..."):
        standings = api.get_standings()
    console.print(f"  [green]✓[/green] Standings: {len(standings)} entries" if standings else f"  [yellow]·[/yellow] Standings: not yet available")

    with console.status("Looking for scheduled WC fixture..."):
        fixture = api.find_wc_fixture(t1.id, t2.id)

    injuries = []
    lineups = []
    api_prediction = None

    if fixture:
        console.print(f"  [green]✓[/green] WC fixture found: {fixture.home_team.name} vs {fixture.away_team.name} — {fixture.round} ({fixture.date[:10]})")

        with console.status("Fetching injury report..."):
            injuries = api.get_injuries(fixture.fixture_id)
        console.print(f"  [green]✓[/green] Injuries: {len(injuries)} player(s) reported")

        with console.status("Fetching lineups..."):
            lineups = api.get_lineups(fixture.fixture_id)
        console.print(f"  [green]✓[/green] Lineups: confirmed" if lineups else f"  [yellow]·[/yellow] Lineups: not yet announced")

        with console.status("Fetching API prediction..."):
            api_prediction = api.get_predictions(fixture.fixture_id)
        console.print(f"  [green]✓[/green] API prediction: available" if api_prediction else f"  [yellow]·[/yellow] API prediction: not available")
    else:
        console.print(f"  [yellow]·[/yellow] No scheduled WC fixture found between these teams")

    console.print()

    prompt = build_prompt(
        t1, t2, t1_form, t2_form, h2h, injuries, lineups, fixture,
        team1_stats=t1_stats,
        team2_stats=t2_stats,
        standings=standings or None,
        api_prediction=api_prediction,
    )

    console.print(f"[dim]Sending data to {model} for analysis...[/dim]")
    console.print()
    ai_analysis = stream_analysis(openrouter_key, prompt, model=model)

    from export import save_report
    report_path = save_report(
        t1, t2, t1_form, t2_form, h2h, injuries, lineups, fixture,
        t1_stats, t2_stats, standings or None, api_prediction, ai_analysis, model,
    )
    console.print(f"\n[green]✓[/green] Report saved: [bold]{report_path}[/bold]")


@app.command()
def search(name: str = typer.Argument(..., help="Team name to search")):
    """Search for a team by name and show its ID."""
    api, _, _model = _get_api()

    with console.status(f"Searching for '{name}'..."):
        results = api.search_team(name)

    if not results:
        console.print(f"[red]No teams found for '{name}'.[/red]")
        return

    table = Table(title=f"Teams matching '{name}'", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Code")

    for t in results[:15]:
        table.add_row(str(t.id), t.name, t.code or "-")

    console.print(table)


if __name__ == "__main__":
    app()
