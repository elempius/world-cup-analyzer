import functools
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from api.models import Team

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


def _handle_api_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        from api.football import FootballAPIError
        try:
            return fn(*args, **kwargs)
        except FootballAPIError as e:
            console.print(f"[red]API error: {e}[/red]")
            raise typer.Exit(1)
    return wrapper


def _safe(fetch, default):
    """Run a fetch, degrading to a default if the API call fails."""
    from api.football import FootballAPIError
    try:
        return fetch()
    except FootballAPIError as e:
        console.print(f"  [yellow]![/yellow] Skipped ({e})")
        return default


def _resolve_team(api, name_or_id: str) -> Optional[Team]:
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
@_handle_api_errors
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


def _run_analysis(
    api,
    openrouter_key: str,
    model: str,
    t1: Team,
    t2: Team,
    form: int,
    h2h_count: int,
    chat: bool = False,
):
    """Fetch all data for a matchup, compute the forecast, and stream the AI analysis."""
    from ai.analyzer import build_prompt, interactive_session, stream_analysis
    from model import forecast_match

    with console.status("Fetching team and tournament data (parallel)..."):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {
                "t1_form": pool.submit(_safe, lambda: api.get_team_form(t1.id, last=form), []),
                "t2_form": pool.submit(_safe, lambda: api.get_team_form(t2.id, last=form), []),
                "t1_stats": pool.submit(_safe, lambda: api.get_team_stats(t1.id), None),
                "t2_stats": pool.submit(_safe, lambda: api.get_team_stats(t2.id), None),
                "h2h": pool.submit(_safe, lambda: api.get_h2h(t1.id, t2.id, last=h2h_count), []),
                "standings": pool.submit(_safe, api.get_standings, []),
                "t1_players": pool.submit(_safe, lambda: api.get_player_stats(t1.id), []),
                "t2_players": pool.submit(_safe, lambda: api.get_player_stats(t2.id), []),
                "top_scorers": pool.submit(_safe, api.get_top_scorers, []),
                "top_assists": pool.submit(_safe, api.get_topassists, []),
                "top_yellowcards": pool.submit(_safe, api.get_top_yellowcards, []),
                "fixture": pool.submit(_safe, lambda: api.find_wc_fixture(t1.id, t2.id), None),
            }
            d = {name: job.result() for name, job in jobs.items()}

    t1_form, t2_form = d["t1_form"], d["t2_form"]
    t1_stats, t2_stats = d["t1_stats"], d["t2_stats"]
    h2h, standings = d["h2h"], d["standings"]
    t1_players, t2_players = d["t1_players"], d["t2_players"]
    top_scorers, top_assists, top_yellowcards = d["top_scorers"], d["top_assists"], d["top_yellowcards"]
    fixture = d["fixture"]

    console.print(f"  [green]✓[/green] {t1.name}: {len(t1_form)} recent matches")
    console.print(f"  [green]✓[/green] {t2.name}: {len(t2_form)} recent matches")
    console.print(f"  [green]✓[/green] {t1.name} stats: {'available' if t1_stats else 'not yet available'}")
    console.print(f"  [green]✓[/green] {t2.name} stats: {'available' if t2_stats else 'not yet available'}")
    console.print(f"  [green]✓[/green] H2H: {len(h2h)} historical meetings found")
    console.print(f"  [green]✓[/green] Standings: {len(standings)} entries" if standings else f"  [yellow]·[/yellow] Standings: not yet available")
    console.print(f"  [green]✓[/green] {t1.name} players: {len(t1_players)} with stats" if t1_players else f"  [yellow]·[/yellow] {t1.name} player stats: not yet available")
    console.print(f"  [green]✓[/green] {t2.name} players: {len(t2_players)} with stats" if t2_players else f"  [yellow]·[/yellow] {t2.name} player stats: not yet available")
    console.print(f"  [green]✓[/green] Top scorers: {len(top_scorers)} players" if top_scorers else f"  [yellow]·[/yellow] Top scorers: not yet available")
    console.print(f"  [green]✓[/green] Top assists: {len(top_assists)} players" if top_assists else f"  [yellow]·[/yellow] Top assists: not yet available")
    console.print(f"  [green]✓[/green] Yellow card leaders: {len(top_yellowcards)} players" if top_yellowcards else f"  [yellow]·[/yellow] Yellow card leaders: not yet available")

    if fixture:
        console.print(f"  [green]✓[/green] WC fixture found: {fixture.home_team.name} vs {fixture.away_team.name} — {fixture.round} ({fixture.date[:10]})")
    else:
        console.print(f"  [yellow]·[/yellow] No scheduled WC fixture found between these teams")

    finished = [m for m in t1_form + t2_form if m.home_goals is not None]
    with console.status("Fetching fixture details and form events (parallel)..."):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ev_jobs = {
                m.fixture_id: pool.submit(_safe, lambda fid=m.fixture_id: api.get_fixture_events(fid), None)
                for m in finished
            }
            fx_jobs = {}
            if fixture:
                fid = fixture.fixture_id
                fx_jobs["injuries"] = pool.submit(_safe, lambda: api.get_injuries(fid), [])
                fx_jobs["lineups"] = pool.submit(_safe, lambda: api.get_lineups(fid), [])
                fx_jobs["api_prediction"] = pool.submit(_safe, lambda: api.get_predictions(fid), None)
                fx_jobs["odds"] = pool.submit(_safe, lambda: api.get_odds(fid), [])
                fx_jobs["odds_markets"] = pool.submit(_safe, lambda: api.get_odds_markets(fid), {})
                fx_jobs["wc_events"] = pool.submit(_safe, lambda: api.get_fixture_events(fid), [])
                fx_jobs["fixture_players"] = pool.submit(_safe, lambda: api.get_fixture_players(fid), [])
                if fixture.status == "FT":
                    fx_jobs["fixture_stats"] = pool.submit(_safe, lambda: api.get_fixture_stats(fid), [])

            form_events: dict[int, list] = {}
            for mfid, job in ev_jobs.items():
                events = job.result()
                if events is not None:
                    form_events[mfid] = events
            fx = {name: job.result() for name, job in fx_jobs.items()}

    event_count = sum(len(v) for v in form_events.values())
    console.print(f"  [green]✓[/green] Form events: {event_count} events across {len(form_events)} matches")

    injuries, lineups, api_prediction = [], [], None
    odds, odds_markets, wc_events, fixture_players, fixture_stats = [], {}, [], [], []
    if fixture:
        injuries = fx["injuries"]
        lineups = fx["lineups"]
        api_prediction = fx["api_prediction"]
        odds = fx["odds"]
        odds_markets = fx["odds_markets"]
        wc_events = fx["wc_events"]
        fixture_players = fx["fixture_players"]
        fixture_stats = fx.get("fixture_stats", [])

        console.print(f"  [green]✓[/green] Injuries: {len(injuries)} player(s) reported")
        console.print(f"  [green]✓[/green] Lineups: confirmed" if lineups else f"  [yellow]·[/yellow] Lineups: not yet announced")
        console.print(f"  [green]✓[/green] API prediction: available" if api_prediction else f"  [yellow]·[/yellow] API prediction: not available")
        console.print(f"  [green]✓[/green] Odds: {len(odds)} bookmaker(s)" if odds else f"  [yellow]·[/yellow] Odds: not available")
        console.print(f"  [green]✓[/green] Fixture events: {len(wc_events)} events" if wc_events else f"  [yellow]·[/yellow] Fixture events: none yet")
        console.print(f"  [green]✓[/green] Fixture player stats: {len(fixture_players)} players" if fixture_players else f"  [yellow]·[/yellow] Fixture player stats: not available")
        if fixture.status == "FT":
            console.print(f"  [green]✓[/green] Match statistics: available" if fixture_stats else f"  [yellow]·[/yellow] Match statistics: not available")

    # Orient home/away for the statistical model (the schedule decides who is home).
    if fixture and t2.id == fixture.home_team.id:
        home_team, away_team = t2, t1
        home_form, away_form = t2_form, t1_form
        home_stats, away_stats = t2_stats, t1_stats
    else:
        home_team, away_team = t1, t2
        home_form, away_form = t1_form, t2_form
        home_stats, away_stats = t1_stats, t2_stats

    forecast = forecast_match(
        home_team, away_team, home_form, away_form, home_stats, away_stats, h2h,
        odds=odds,
    )
    console.print(
        f"  [green]✓[/green] In-house model: "
        f"{forecast.home_name} {forecast.p_home:.0%} / Draw {forecast.p_draw:.0%} / "
        f"{forecast.away_name} {forecast.p_away:.0%}  "
        f"(xG {forecast.exp_goals_home}-{forecast.exp_goals_away})"
    )
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
        forecast=forecast,
    )

    console.print(f"[dim]Sending data to {model} for analysis...[/dim]")
    console.print()
    ai_analysis, client, messages = stream_analysis(openrouter_key, prompt, model=model)

    from ledger import record_prediction
    record_prediction(
        t1, t2, fixture, ai_analysis, model,
        odds_markets=odds_markets, forecast=forecast,
    )
    console.print(f"\n[dim]Prediction recorded — run `record` to track results.[/dim]")

    if chat and sys.stdin.isatty():
        interactive_session(client, messages, model=model)
    return ai_analysis


@app.command()
@_handle_api_errors
def analyze(
    team1: str = typer.Argument(..., help="First team name"),
    team2: str = typer.Argument(..., help="Second team name"),
    form: int = typer.Option(5, "-f", "--form", help="Number of recent matches to fetch per team"),
    h2h_count: int = typer.Option(10, "--h2h", help="Number of H2H matches to fetch"),
    chat: bool = typer.Option(True, "--chat/--no-chat", help="Open an interactive Q&A session after the analysis"),
):
    """Analyze a matchup and predict the outcome using AI."""
    api, openrouter_key, model = _get_api()

    console.print(Panel.fit("[bold cyan]World Cup 2026 — Match Analyzer[/bold cyan]"))
    console.print()

    t1 = _resolve_team(api, team1)
    if not t1:
        raise typer.Exit(1)
    t2 = _resolve_team(api, team2)
    if not t2:
        raise typer.Exit(1)

    console.print()
    _run_analysis(api, openrouter_key, model, t1, t2, form, h2h_count, chat=chat)


@app.command(name="analyze-day")
@_handle_api_errors
def analyze_day(
    date: Optional[str] = typer.Argument(None, help="Date (YYYY-MM-DD), defaults to today (UTC)"),
    form: int = typer.Option(5, "-f", "--form", help="Number of recent matches to fetch per team"),
    h2h_count: int = typer.Option(10, "--h2h", help="Number of H2H matches to fetch"),
    chat: bool = typer.Option(False, "--chat/--no-chat", help="Open an interactive Q&A session after each analysis"),
):
    """Analyze every World Cup fixture on a given date."""
    api, openrouter_key, model = _get_api()
    target = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with console.status("Fetching World Cup fixtures..."):
        day_fixtures = [f for f in api.get_wc_fixtures() if f.date[:10] == target]

    if not day_fixtures:
        console.print(f"[yellow]No fixtures on {target}.[/yellow]")
        return

    day_fixtures.sort(key=lambda f: f.date)
    console.print(Panel.fit(f"[bold cyan]World Cup 2026 — {len(day_fixtures)} fixture(s) on {target}[/bold cyan]"))

    for i, f in enumerate(day_fixtures, 1):
        console.print()
        console.print(Panel.fit(f"[bold]{i}/{len(day_fixtures)} — {f.home_team.name} vs {f.away_team.name}[/bold] ({f.round})"))
        _run_analysis(api, openrouter_key, model, f.home_team, f.away_team, form, h2h_count, chat=chat)


@app.command()
@_handle_api_errors
def record():
    """Show recorded predictions and how they fared."""
    import config
    from ledger import brier_score, grade_bet, kelly_fraction, load_predictions

    preds = load_predictions()
    if not preds:
        console.print("[yellow]No predictions recorded yet — run `analyze` first.[/yellow]")
        return

    # Re-analyzing a match supersedes the earlier prediction
    latest: dict = {}
    unscheduled = []
    for p in preds:
        if p.get("fixture_id"):
            latest[p["fixture_id"]] = p
        else:
            unscheduled.append(p)
    preds = sorted(
        list(latest.values()) + unscheduled,
        key=lambda p: p.get("fixture_date") or p["recorded_at"],
    )

    api, _, _model = _get_api()
    from api.football import FINISHED_STATUSES
    with console.status("Fetching results..."):
        fixtures_by_id = {f.fixture_id: f for f in api.get_wc_fixtures()}

    table = Table(title="Prediction record", box=box.ROUNDED)
    table.add_column("Date", style="cyan")
    table.add_column("Match")
    table.add_column("Best Bet")
    table.add_column("Conf", justify="center")
    table.add_column("Odds", justify="right")
    table.add_column("Score", justify="center")
    table.add_column("Result", justify="center")

    wins = losses = 0
    profit = 0.0
    priced = 0
    kelly_profit = 0.0
    kelly_staked = 0.0
    brier_samples: list[tuple[Optional[float], bool]] = []
    by_conf: dict[str, list[int]] = {}
    for p in preds:
        f = fixtures_by_id.get(p["fixture_id"])
        odds = p.get("odds")
        model_prob = p.get("model_prob")
        if f and f.status in FINISHED_STATUSES and f.home_goals is not None:
            score = f"{f.home_goals}-{f.away_goals}"
            graded = grade_bet(p["best_bet"], p["home"], p["away"], f.home_goals, f.away_goals)
            if graded is True:
                result = "[green]WIN[/green]"
                wins += 1
            elif graded is False:
                result = "[red]LOSS[/red]"
                losses += 1
            else:
                result = "[dim]ungraded[/dim]"
            if graded is not None:
                if odds:
                    profit += (odds - 1) if graded else -1
                    priced += 1
                    stake = config.KELLY_FRACTION * kelly_fraction(model_prob, odds)
                    if stake > 0:
                        kelly_profit += stake * (odds - 1) if graded else -stake
                        kelly_staked += stake
                brier_samples.append((model_prob, graded))
                conf = p.get("confidence") or "?"
                by_conf.setdefault(conf, [0, 0])[0 if graded else 1] += 1
        else:
            score, result = "—", "[dim]pending[/dim]"
        table.add_row(
            (p.get("fixture_date") or p["recorded_at"])[:10],
            f"{p['home']} vs {p['away']}",
            p["best_bet"] or "—",
            f"{p['confidence']}/10" if p.get("confidence") else "—",
            f"{odds:.2f}" if odds else "—",
            score,
            result,
        )

    console.print(table)
    graded_total = wins + losses
    if graded_total:
        console.print(f"Record: [bold]{wins}W-{losses}L[/bold] ({wins / graded_total:.0%}) over {graded_total} auto-graded bets")
        if priced:
            color = "green" if profit >= 0 else "red"
            console.print(
                f"Flat 1u stakes at best available odds: [{color}]{profit:+.2f}u[/{color}] "
                f"over {priced} priced bets (ROI {profit / priced:+.1%})"
            )
        if kelly_staked > 0:
            kcolor = "green" if kelly_profit >= 0 else "red"
            console.print(
                f"{config.KELLY_FRACTION:g}-Kelly staking (model edge vs odds): "
                f"[{kcolor}]{kelly_profit:+.2f}u[/{kcolor}] on {kelly_staked:.2f}u staked "
                f"(ROI {kelly_profit / kelly_staked:+.1%})"
            )
        brier = brier_score(brier_samples)
        if brier is not None:
            n_cal = len([s for s in brier_samples if s[0] is not None])
            console.print(
                f"Model calibration (Brier score): [bold]{brier:.3f}[/bold] over {n_cal} graded bets "
                f"[dim](0=perfect, 0.25=coin flip, lower is better)[/dim]"
            )
        if len(by_conf) > 1:
            parts = [
                f"{conf}/10: {w}W-{l}L"
                for conf, (w, l) in sorted(by_conf.items(), key=lambda kv: kv[0], reverse=True)
            ]
            console.print(f"By confidence: {'  |  '.join(parts)}")


@app.command()
@_handle_api_errors
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
