import json
import time
from pathlib import Path
from typing import Optional

import httpx

from api.models import (
    ApiPrediction,
    Injury,
    LineupPlayer,
    MatchResult,
    StandingsEntry,
    Team,
    TeamLineup,
    TeamStats,
    WCFixture,
)

CACHE_DIR = Path("cache")

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
        resp = self.client.get(endpoint, params=params)
        resp.raise_for_status()
        data = resp.json().get("response", [])
        self._set_cache(key, data)
        return data

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
        results = self._get("/lineups", {"fixture": fixture_id}, "lineups")
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
        for f in self.get_wc_fixtures():
            ids = {f.home_team.id, f.away_team.id}
            if ids == {team1_id, team2_id}:
                return f
        return None

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

        return ApiPrediction(
            winner_name=winner.get("name"),
            winner_comment=winner.get("comment"),
            advice=preds.get("advice") or "",
            home_percent=percent.get("home") or "?",
            draw_percent=percent.get("draw") or "?",
            away_percent=percent.get("away") or "?",
            under_over=preds.get("under_over"),
            goals_home=goals.get("home"),
            goals_away=goals.get("away"),
            form_home=comp.get("form", {}).get("home") or "?",
            form_away=comp.get("form", {}).get("away") or "?",
            att_home=comp.get("att", {}).get("home") or "?",
            att_away=comp.get("att", {}).get("away") or "?",
            def_home=comp.get("def", {}).get("home") or "?",
            def_away=comp.get("def", {}).get("away") or "?",
            total_home=comp.get("total", {}).get("home") or "?",
            total_away=comp.get("total", {}).get("away") or "?",
        )
