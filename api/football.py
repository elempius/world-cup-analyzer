import json
import time
from pathlib import Path
from typing import Optional

import httpx

from api.models import (
    ApiPrediction,
    BookmakerOdds,
    FixtureEvent,
    FixturePlayerStat,
    FixtureTeamStat,
    Injury,
    Last5,
    LineupPlayer,
    MatchResult,
    PlayerStat,
    StandingsEntry,
    Team,
    TeamLineup,
    TeamStats,
    UnderOver,
    WCFixture,
)

CACHE_DIR = Path("cache")

# Statuses meaning the match has been played to completion
FINISHED_STATUSES = {"FT", "AET", "PEN"}


class FootballAPIError(Exception):
    """Request failure or an in-band error reported by API-Football."""

CACHE_TTL = {
    "fixtures": 3600,
    "form": 1800,
    "h2h": 86400,
    "injuries": 900,
    "lineups": 900,
    "teams": 86400,
    "leagues": 86400,
    "stats": 1800,
    "standings": 1800,
    "predictions": 900,
    "players": 1800,
    "topscorers": 1800,
    "fixture_stats": 900,
    "fixture_events": 3600,
    "fixture_players": 3600,
    "odds": 3600,
    "topassists": 1800,
    "topyellowcards": 1800,
}


class FootballAPI:
    def __init__(self, api_key: str, league_id: int = 1, season: int = 2026):
        self.league_id = league_id
        self.season = season
        self.client = httpx.Client(
            base_url="https://v3.football.api-sports.io",
            headers={"x-apisports-key": api_key},
            timeout=30.0,
        )
        CACHE_DIR.mkdir(exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
        return CACHE_DIR / f"{safe}.json"

    def _get_cached(self, key: str, ttl: int) -> Optional[list | dict]:
        path = self._cache_path(key)
        if path.exists():
            data = json.loads(path.read_text())
            if time.time() - data["ts"] < ttl:
                return data["body"]
        return None

    def _set_cache(self, key: str, body) -> None:
        self._cache_path(key).write_text(json.dumps({"ts": time.time(), "body": body}))

    def _get(self, endpoint: str, params: dict, ttl_key: str):
        key = endpoint + "_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
        cached = self._get_cached(key, CACHE_TTL[ttl_key])
        if cached is not None:
            return cached
        data = self._fetch(endpoint, params)
        self._set_cache(key, data)
        return data

    def _fetch(self, endpoint: str, params: dict, attempts: int = 3):
        last_error: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                time.sleep(2 ** attempt)
            try:
                resp = self.client.get(endpoint, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                last_error = e
                continue
            body = resp.json()
            # API-Football reports failures (rate limit, plan limits, bad
            # params) with HTTP 200 and a non-empty "errors" field.
            errors = body.get("errors")
            if errors:
                if isinstance(errors, dict):
                    msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
                else:
                    msg = "; ".join(str(e) for e in errors)
                if "ratelimit" in msg.lower() or "too many requests" in msg.lower():
                    # Per-minute quota; wait it out and retry
                    last_error = FootballAPIError(f"{endpoint}: {msg}")
                    time.sleep(8)
                    continue
                raise FootballAPIError(f"{endpoint}: {msg}")
            return body.get("response", [])
        raise FootballAPIError(
            f"{endpoint}: request failed after {attempts} attempts ({last_error})"
        )

    # --- Public methods ---

    def search_team(self, name: str) -> list[Team]:
        results = self._get("/teams", {"search": name}, "teams")
        return [
            Team(
                id=r["team"]["id"],
                name=r["team"]["name"],
                code=r["team"].get("code"),
                logo=r["team"].get("logo"),
            )
            for r in results
        ]

    def get_wc_fixtures(self) -> list[WCFixture]:
        results = self._get(
            "/fixtures", {"league": self.league_id, "season": self.season}, "fixtures"
        )
        fixtures = []
        for r in results:
            f = r["fixture"]
            teams = r["teams"]
            goals = r["goals"]
            venue = f.get("venue", {}) or {}
            fixtures.append(
                WCFixture(
                    fixture_id=f["id"],
                    date=f["date"],
                    round=r["league"].get("round", ""),
                    venue=venue.get("name") or venue.get("city") or "TBD",
                    home_team=Team(id=teams["home"]["id"], name=teams["home"]["name"]),
                    away_team=Team(id=teams["away"]["id"], name=teams["away"]["name"]),
                    status=f["status"]["short"],
                    home_goals=goals.get("home"),
                    away_goals=goals.get("away"),
                )
            )
        return fixtures

    def get_team_form(self, team_id: int, last: int = 5) -> list[MatchResult]:
        results = self._get(
            "/fixtures",
            {"team": team_id, "last": last},
            "form",
        )
        matches = []
        for r in results:
            f = r["fixture"]
            teams = r["teams"]
            goals = r["goals"]
            matches.append(
                MatchResult(
                    fixture_id=f["id"],
                    date=f["date"],
                    league=r["league"]["name"],
                    round=r["league"].get("round", ""),
                    home_team=Team(id=teams["home"]["id"], name=teams["home"]["name"]),
                    away_team=Team(id=teams["away"]["id"], name=teams["away"]["name"]),
                    home_goals=goals.get("home"),
                    away_goals=goals.get("away"),
                    status=f["status"]["short"],
                )
            )
        return matches

    def get_h2h(self, team1_id: int, team2_id: int, last: int = 10) -> list[MatchResult]:
        results = self._get(
            "/fixtures/headtohead",
            {"h2h": f"{team1_id}-{team2_id}", "last": last},
            "h2h",
        )
        matches = []
        for r in results:
            f = r["fixture"]
            teams = r["teams"]
            goals = r["goals"]
            matches.append(
                MatchResult(
                    fixture_id=f["id"],
                    date=f["date"],
                    league=r["league"]["name"],
                    round=r["league"].get("round", ""),
                    home_team=Team(id=teams["home"]["id"], name=teams["home"]["name"]),
                    away_team=Team(id=teams["away"]["id"], name=teams["away"]["name"]),
                    home_goals=goals.get("home"),
                    away_goals=goals.get("away"),
                    status=f["status"]["short"],
                )
            )
        return sorted(matches, key=lambda m: m.date, reverse=True)

    def get_injuries(self, fixture_id: int) -> list[Injury]:
        results = self._get("/injuries", {"fixture": fixture_id}, "injuries")
        return [
            Injury(
                player=r["player"]["name"],
                team_name=r["team"]["name"],
                reason=r.get("reason") or r.get("player", {}).get("reason") or "Unknown",
                injury_type=r["player"].get("type") or "Unknown",
            )
            for r in results
        ]

    def get_lineups(self, fixture_id: int) -> list[TeamLineup]:
        results = self._get("/fixtures/lineups", {"fixture": fixture_id}, "lineups")
        lineups = []
        for r in results:
            coach = r.get("coach", {}) or {}
            starting = [
                LineupPlayer(
                    name=p["player"]["name"],
                    number=p["player"].get("number") or 0,
                    position=p["player"].get("pos") or "?",
                )
                for p in r.get("startXI", [])
            ]
            subs = [
                LineupPlayer(
                    name=p["player"]["name"],
                    number=p["player"].get("number") or 0,
                    position=p["player"].get("pos") or "?",
                )
                for p in r.get("substitutes", [])
            ]
            lineups.append(
                TeamLineup(
                    team=Team(id=r["team"]["id"], name=r["team"]["name"]),
                    coach=coach.get("name") or "Unknown",
                    formation=r.get("formation") or "Unknown",
                    starting_xi=starting,
                    substitutes=subs,
                )
            )
        return lineups

    def find_wc_fixture(self, team1_id: int, team2_id: int) -> Optional[WCFixture]:
        matches = [
            f for f in self.get_wc_fixtures()
            if {f.home_team.id, f.away_team.id} == {team1_id, team2_id}
        ]
        if not matches:
            return None
        # Teams can meet twice in a tournament: prefer the nearest unplayed
        # fixture, otherwise the most recently played one.
        unplayed = [f for f in matches if f.status not in FINISHED_STATUSES]
        if unplayed:
            return min(unplayed, key=lambda f: f.date)
        return max(matches, key=lambda f: f.date)

    def get_team_stats(self, team_id: int) -> Optional[TeamStats]:
        results = self._get(
            "/teams/statistics",
            {"league": self.league_id, "season": self.season, "team": team_id},
            "stats",
        )
        # /teams/statistics returns a single object, not an array
        if not results:
            return None
        r = results if isinstance(results, dict) else (results[0] if results else None)
        if not r:
            return None

        team = r.get("team", {})
        fixtures = r.get("fixtures", {})
        goals = r.get("goals", {})
        biggest = r.get("biggest", {})
        lineups = r.get("lineups", [])

        preferred = max(lineups, key=lambda x: x.get("played", 0))["formation"] if lineups else None

        return TeamStats(
            team=Team(id=team.get("id", team_id), name=team.get("name", "")),
            form=r.get("form") or "",
            played=fixtures.get("played", {}).get("total", 0),
            wins=fixtures.get("wins", {}).get("total", 0),
            draws=fixtures.get("draws", {}).get("total", 0),
            losses=fixtures.get("loses", {}).get("total", 0),
            goals_for_avg=goals.get("for", {}).get("average", {}).get("total") or "0",
            goals_against_avg=goals.get("against", {}).get("average", {}).get("total") or "0",
            clean_sheets=r.get("clean_sheet", {}).get("total", 0),
            biggest_win=biggest.get("wins", {}).get("total"),
            biggest_loss=biggest.get("loses", {}).get("total"),
            win_streak=biggest.get("streak", {}).get("wins", 0),
            preferred_formation=preferred,
        )

    def get_standings(self) -> list[StandingsEntry]:
        results = self._get(
            "/standings",
            {"league": self.league_id, "season": self.season},
            "standings",
        )
        entries = []
        for item in results:
            for group in item.get("league", {}).get("standings", []):
                for s in group:
                    team = s.get("team", {})
                    all_stats = s.get("all", {})
                    entries.append(
                        StandingsEntry(
                            rank=s.get("rank", 0),
                            team=Team(id=team.get("id", 0), name=team.get("name", "")),
                            group=s.get("group", ""),
                            points=s.get("points", 0),
                            played=all_stats.get("played", 0),
                            won=all_stats.get("win", 0),
                            drawn=all_stats.get("draw", 0),
                            lost=all_stats.get("lose", 0),
                            goals_for=all_stats.get("goals", {}).get("for", 0),
                            goals_against=all_stats.get("goals", {}).get("against", 0),
                            goal_diff=s.get("goalsDiff", 0),
                            form=s.get("form") or "",
                            description=s.get("description"),
                        )
                    )
        return entries

    def get_team_by_id(self, team_id: int) -> Optional[Team]:
        results = self._get("/teams", {"id": team_id}, "teams")
        if not results:
            return None
        r = results[0]
        return Team(
            id=r["team"]["id"],
            name=r["team"]["name"],
            code=r["team"].get("code"),
            logo=r["team"].get("logo"),
        )

    def get_player_stats(self, team_id: int) -> list[PlayerStat]:
        results = self._get(
            "/players",
            {"league": self.league_id, "season": self.season, "team": team_id},
            "players",
        )
        players = []
        for r in results:
            p = r.get("player", {})
            stats = (r.get("statistics") or [{}])[0]
            games = stats.get("games", {})
            goals = stats.get("goals", {})
            shots = stats.get("shots", {})
            passes = stats.get("passes", {})
            cards = stats.get("cards", {})
            players.append(PlayerStat(
                player_id=p.get("id", 0),
                name=p.get("name", ""),
                appearances=games.get("appearences") or 0,
                minutes=games.get("minutes") or 0,
                goals=goals.get("total") or 0,
                assists=goals.get("assists") or 0,
                shots_on=shots.get("on") or 0,
                key_passes=passes.get("key") or 0,
                rating=games.get("rating"),
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0,
            ))
        return sorted(players, key=lambda p: (p.goals + p.assists, p.appearances), reverse=True)

    def get_top_scorers(self, limit: int = 10) -> list[PlayerStat]:
        results = self._get(
            "/players/topscorers",
            {"league": self.league_id, "season": self.season},
            "topscorers",
        )
        players = []
        for r in results[:limit]:
            p = r.get("player", {})
            stats = (r.get("statistics") or [{}])[0]
            games = stats.get("games", {})
            goals = stats.get("goals", {})
            shots = stats.get("shots", {})
            passes = stats.get("passes", {})
            cards = stats.get("cards", {})
            players.append(PlayerStat(
                player_id=p.get("id", 0),
                name=p.get("name", ""),
                appearances=games.get("appearences") or 0,
                minutes=games.get("minutes") or 0,
                goals=goals.get("total") or 0,
                assists=goals.get("assists") or 0,
                shots_on=shots.get("on") or 0,
                key_passes=passes.get("key") or 0,
                rating=games.get("rating"),
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0,
            ))
        return players

    def get_fixture_stats(self, fixture_id: int) -> list[FixtureTeamStat]:
        results = self._get("/fixtures/statistics", {"fixture": fixture_id}, "fixture_stats")
        team_stats = []
        for r in results:
            stats = {s["type"]: s["value"] for s in r.get("statistics", [])}
            team_stats.append(FixtureTeamStat(
                team=Team(id=r["team"]["id"], name=r["team"]["name"]),
                possession=stats.get("Ball Possession"),
                shots_total=stats.get("Total Shots"),
                shots_on=stats.get("Shots on Goal"),
                corners=stats.get("Corner Kicks"),
                passes_total=stats.get("Total passes"),
                pass_accuracy=stats.get("Passes %"),
                fouls=stats.get("Fouls"),
                offsides=stats.get("Offsides"),
                saves=stats.get("Goalkeeper Saves"),
            ))
        return team_stats

    def get_fixture_events(self, fixture_id: int) -> list[FixtureEvent]:
        results = self._get("/fixtures/events", {"fixture": fixture_id}, "fixture_events")
        events = []
        for r in results:
            t = r.get("time", {})
            team = r.get("team", {})
            player = r.get("player", {})
            assist = r.get("assist", {}) or {}
            events.append(FixtureEvent(
                minute=t.get("elapsed") or 0,
                extra_minute=t.get("extra"),
                team=Team(id=team.get("id", 0), name=team.get("name", "")),
                player=player.get("name") or "Unknown",
                assist=assist.get("name") or None,
                type=r.get("type") or "",
                detail=r.get("detail") or "",
                comments=r.get("comments"),
            ))
        return events

    def get_fixture_players(self, fixture_id: int) -> list[FixturePlayerStat]:
        results = self._get("/fixtures/players", {"fixture": fixture_id}, "fixture_players")
        players = []
        for team_block in results:
            team_data = team_block.get("team", {})
            t = Team(id=team_data.get("id", 0), name=team_data.get("name", ""))
            for p_data in team_block.get("players", []):
                p = p_data.get("player", {})
                stats = (p_data.get("statistics") or [{}])[0]
                games = stats.get("games", {})
                goals_s = stats.get("goals", {})
                shots_s = stats.get("shots", {})
                passes_s = stats.get("passes", {})
                tackles_s = stats.get("tackles", {})
                cards_s = stats.get("cards", {})
                gk = stats.get("goalkeeper", {})
                players.append(FixturePlayerStat(
                    player_id=p.get("id", 0),
                    name=p.get("name", ""),
                    team=t,
                    minutes=games.get("minutes") or 0,
                    rating=games.get("rating"),
                    goals=goals_s.get("total") or 0,
                    assists=goals_s.get("assists") or 0,
                    shots_on=shots_s.get("on") or 0,
                    key_passes=passes_s.get("key") or 0,
                    tackles=tackles_s.get("total") or 0,
                    saves=gk.get("saves") or 0,
                    yellow_cards=cards_s.get("yellow") or 0,
                    red_cards=cards_s.get("red") or 0,
                ))
        return players

    def get_odds(self, fixture_id: int) -> list[BookmakerOdds]:
        results = self._get("/odds", {"fixture": fixture_id, "bet": 1}, "odds")
        bookmakers = []
        for r in results:
            for bm in r.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    if bet.get("name") == "Match Winner":
                        vals = {v["value"]: v["odd"] for v in bet.get("values", [])}
                        bookmakers.append(BookmakerOdds(
                            bookmaker=bm.get("name", ""),
                            home=vals.get("Home", "?"),
                            draw=vals.get("Draw", "?"),
                            away=vals.get("Away", "?"),
                        ))
        return bookmakers[:5]

    def get_topassists(self, limit: int = 10) -> list[PlayerStat]:
        results = self._get(
            "/players/topassists",
            {"league": self.league_id, "season": self.season},
            "topassists",
        )
        players = []
        for r in results[:limit]:
            p = r.get("player", {})
            stats = (r.get("statistics") or [{}])[0]
            games = stats.get("games", {})
            goals = stats.get("goals", {})
            shots = stats.get("shots", {})
            passes = stats.get("passes", {})
            cards = stats.get("cards", {})
            players.append(PlayerStat(
                player_id=p.get("id", 0),
                name=p.get("name", ""),
                appearances=games.get("appearences") or 0,
                minutes=games.get("minutes") or 0,
                goals=goals.get("total") or 0,
                assists=goals.get("assists") or 0,
                shots_on=shots.get("on") or 0,
                key_passes=passes.get("key") or 0,
                rating=games.get("rating"),
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0,
            ))
        return players

    def get_top_yellowcards(self, limit: int = 10) -> list[PlayerStat]:
        results = self._get(
            "/players/topyellowcards",
            {"league": self.league_id, "season": self.season},
            "topyellowcards",
        )
        players = []
        for r in results[:limit]:
            p = r.get("player", {})
            stats = (r.get("statistics") or [{}])[0]
            games = stats.get("games", {})
            goals = stats.get("goals", {})
            shots = stats.get("shots", {})
            passes = stats.get("passes", {})
            cards = stats.get("cards", {})
            players.append(PlayerStat(
                player_id=p.get("id", 0),
                name=p.get("name", ""),
                appearances=games.get("appearences") or 0,
                minutes=games.get("minutes") or 0,
                goals=goals.get("total") or 0,
                assists=goals.get("assists") or 0,
                shots_on=shots.get("on") or 0,
                key_passes=passes.get("key") or 0,
                rating=games.get("rating"),
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0,
            ))
        return players

    def get_predictions(self, fixture_id: int) -> Optional[ApiPrediction]:
        results = self._get("/predictions", {"fixture": fixture_id}, "predictions")
        if not results:
            return None
        r = results[0]
        preds = r.get("predictions", {})
        comp = r.get("comparison", {})
        winner = preds.get("winner") or {}
        percent = preds.get("percent") or {}
        goals = preds.get("goals") or {}
        teams = r.get("teams", {})

        def parse_last5(t: dict) -> Optional[Last5]:
            l5 = t.get("last_5") or {}
            if not l5:
                return None
            gf = l5.get("goals", {}).get("for", {})
            ga = l5.get("goals", {}).get("against", {})
            return Last5(
                form_pct=l5.get("form") or "?",
                att_pct=l5.get("att") or "?",
                def_pct=l5.get("def") or "?",
                goals_for_avg=gf.get("average") or "?",
                goals_against_avg=ga.get("average") or "?",
                goals_for_total=gf.get("total") or 0,
                goals_against_total=ga.get("total") or 0,
            )

        def parse_uo(t: dict) -> Optional[UnderOver]:
            uo = (t.get("league") or {}).get("goals", {}).get("for", {}).get("under_over") or {}
            if not uo:
                return None
            def g(line, key): return (uo.get(line) or {}).get(key) or 0
            return UnderOver(
                over_0_5=g("0.5","over"), under_0_5=g("0.5","under"),
                over_1_5=g("1.5","over"), under_1_5=g("1.5","under"),
                over_2_5=g("2.5","over"), under_2_5=g("2.5","under"),
                over_3_5=g("3.5","over"), under_3_5=g("3.5","under"),
                over_4_5=g("4.5","over"), under_4_5=g("4.5","under"),
            )

        def c(key, side): return comp.get(key, {}).get(side) or "?"

        return ApiPrediction(
            winner_name=winner.get("name"),
            winner_comment=winner.get("comment"),
            win_or_draw=preds.get("win_or_draw") or False,
            advice=preds.get("advice") or "",
            home_percent=percent.get("home") or "?",
            draw_percent=percent.get("draw") or "?",
            away_percent=percent.get("away") or "?",
            under_over=preds.get("under_over"),
            goals_home=goals.get("home"),
            goals_away=goals.get("away"),
            form_home=c("form","home"),
            form_away=c("form","away"),
            att_home=c("att","home"),
            att_away=c("att","away"),
            def_home=c("def","home"),
            def_away=c("def","away"),
            poisson_home=c("poisson_distribution","home"),
            poisson_away=c("poisson_distribution","away"),
            h2h_home=c("h2h","home"),
            h2h_away=c("h2h","away"),
            goals_comp_home=c("goals","home"),
            goals_comp_away=c("goals","away"),
            total_home=c("total","home"),
            total_away=c("total","away"),
            last_5_home=parse_last5(teams.get("home") or {}),
            last_5_away=parse_last5(teams.get("away") or {}),
            home_under_over=parse_uo(teams.get("home") or {}),
            away_under_over=parse_uo(teams.get("away") or {}),
        )
