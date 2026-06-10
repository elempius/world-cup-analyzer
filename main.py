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

    model = os.getenv("OPENROUTER_MODEL")
    missing = []
    if not football_key:
        missing.append("FOOTBALL_API_KEY")
    if not openrouter_key:
        missing.append("OPENROUTER_API_KEY")
    if not model:
        missing.append("OPENROUTER_MODEL")
    if missing:
        console.print(f"[red]Missing env vars: {', '.join(missing)}[/red]")
        console.print("Copy [bold].env.example[/bold] to [bold].env[/bold] and fill in your keys.")
        raise typer.Exit(1)

    from api.football import FootballAPI
    return FootballAPI(football_key, league_id=league_id, season=season), openrouter_key, model


def _resolve_team(api, name_or_id: str) -> Optional[object]:
    # Numeric input → treat as team ID directly
    if name_or_id.isdigit():
        team_id = int(name_or_id)
        with console.status(f"Fetching team ID {team_id}..."):
            team = api.get_team_by_id(team_id)
        if not team:
            console.print(f"[red]No team found with ID {team_id}.[/red]")
            return None
        console.print(f"  [green]✓[/green] Found: [bold]{team.name}[/bold] (ID {team.id})")
        return team

    with console.status(f"Searching for [bold]{name_or_id}[/bold]..."):
        results = api.search_team(name_or_id)

    if not results:
        console.print(f"[red]No team found matching '{name_or_id}'.[/red]")
        console.print("Tip: pass the numeric team ID directly, or try a shorter/official name.")
        return None

    if len(results) == 1:
        console.print(f"  [green]✓[/green] Found: [bold]{results[0].name}[/bold] (ID {results[0].id})")
        return results[0]

    # Multiple results — prefer national teams (short code)
    national = [t for t in results if t.code and len(t.code) <= 3]
    if national:
        team = national[0]
        console.print(f"  [green]✓[/green] Found: [bold]{team.name}[/bold] (ID {team.id})")
        return team

    console.print(f"\n[yellow]Multiple matches for '{name_or_id}' — pick one or re-run with the ID:[/yellow]")
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

    with console.status(f"Fetching {t1.name} player stats..."):
        t1_players = api.get_player_stats(t1.id)
    console.print(f"  [green]✓[/green] {t1.name} players: {len(t1_players)} with stats" if t1_players else f"  [yellow]·[/yellow] {t1.name} player stats: not yet available")

    with console.status(f"Fetching {t2.name} player stats..."):
        t2_players = api.get_player_stats(t2.id)
    console.print(f"  [green]✓[/green] {t2.name} players: {len(t2_players)} with stats" if t2_players else f"  [yellow]·[/yellow] {t2.name} player stats: not yet available")

    with console.status("Fetching tournament top scorers..."):
        top_scorers = api.get_top_scorers()
    console.print(f"  [green]✓[/green] Top scorers: {len(top_scorers)} players" if top_scorers else f"  [yellow]·[/yellow] Top scorers: not yet available")

    with console.status("Looking for scheduled WC fixture..."):
        fixture = api.find_wc_fixture(t1.id, t2.id)

    injuries = []
    lineups = []
    api_prediction = None
    fixture_stats = []

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

        if fixture.status == "FT":
            with console.status("Fetching match statistics..."):
                fixture_stats = api.get_fixture_stats(fixture.fixture_id)
            console.print(f"  [green]✓[/green] Match statistics: available" if fixture_stats else f"  [yellow]·[/yellow] Match statistics: not available")
    else:
        console.print(f"  [yellow]·[/yellow] No scheduled WC fixture found between these teams")

    with console.status("Fetching match events for form analysis..."):
        form_events: dict[int, list] = {}
        for m in t1_form + t2_form:
            if m.home_goals is not None:
                form_events[m.fixture_id] = api.get_fixture_events(m.fixture_id)
    event_count = sum(len(v) for v in form_events.values())
    console.print(f"  [green]✓[/green] Form events: {event_count} events across {len(form_events)} matches")

    with console.status("Fetching tournament top assists..."):
        top_assists = api.get_topassists()
    console.print(f"  [green]✓[/green] Top assists: {len(top_assists)} players" if top_assists else f"  [yellow]·[/yellow] Top assists: not yet available")

    with console.status("Fetching disciplinary leaders..."):
        top_yellowcards = api.get_top_yellowcards()
    console.print(f"  [green]✓[/green] Yellow card leaders: {len(top_yellowcards)} players" if top_yellowcards else f"  [yellow]·[/yellow] Yellow card leaders: not yet available")

    odds = []
    wc_events = []
    fixture_players = []
    if fixture:
        with console.status("Fetching pre-match odds..."):
            odds = api.get_odds(fixture.fixture_id)
        console.print(f"  [green]✓[/green] Odds: {len(odds)} bookmaker(s)" if odds else f"  [yellow]·[/yellow] Odds: not available")

        with console.status("Fetching fixture events..."):
            wc_events = api.get_fixture_events(fixture.fixture_id)
        console.print(f"  [green]✓[/green] Fixture events: {len(wc_events)} events" if wc_events else f"  [yellow]·[/yellow] Fixture events: none yet")

        with console.status("Fetching fixture player stats..."):
            fixture_players = api.get_fixture_players(fixture.fixture_id)
        console.print(f"  [green]✓[/green] Fixture player stats: {len(fixture_players)} players" if fixture_players else f"  [yellow]·[/yellow] Fixture player stats: not available")

    console.print()

    prompt = build_prompt(
        t1, t2, t1_form, t2_form, h2h, injuries, lineups, fixture,
        team1_stats=t1_stats,
        team2_stats=t2_stats,
        standings=standings or None,
        api_prediction=api_prediction,
        team1_players=t1_players or None,
        team2_players=t2_players or None,
        top_scorers=top_scorers or None,
        fixture_stats=fixture_stats or None,
        form_events=form_events or None,
        odds=odds or None,
        top_assists=top_assists or None,
        top_yellowcards=top_yellowcards or None,
        wc_events=wc_events or None,
        fixture_players=fixture_players or None,
    )

    console.print(f"[dim]Sending data to {model} for analysis...[/dim]")
    console.print()
    ai_analysis = stream_analysis(openrouter_key, prompt, model=model)

    from export import save_report
    report_path = save_report(
        t1, t2, t1_form, t2_form, h2h, injuries, lineups, fixture,
        t1_stats, t2_stats, standings or None, api_prediction, ai_analysis, model,
        t1_players or None, t2_players or None, top_scorers or None, fixture_stats or None,
        form_events=form_events or None,
        odds=odds or None,
        top_assists=top_assists or None,
        top_yellowcards=top_yellowcards or None,
        wc_events=wc_events or None,
        fixture_players=fixture_players or None,
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
