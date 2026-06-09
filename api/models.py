from dataclasses import dataclass
from typing import Optional


@dataclass
class Team:
    id: int
    name: str
    code: Optional[str] = None
    logo: Optional[str] = None


@dataclass
class MatchResult:
    fixture_id: int
    date: str
    league: str
    round: str
    home_team: Team
    away_team: Team
    home_goals: Optional[int]
    away_goals: Optional[int]
    status: str

    def format_for_team(self, team_id: int) -> str:
        is_home = self.home_team.id == team_id
        opponent = self.away_team.name if is_home else self.home_team.name
        gf = self.home_goals if is_home else self.away_goals
        ga = self.away_goals if is_home else self.home_goals
        venue = "H" if is_home else "A"

        if gf is None:
            return f"vs {opponent} ({venue}) - {self.league} | {self.date[:10]}"

        if gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"

        return f"[{result}] {gf}-{ga} vs {opponent} ({venue}) - {self.league} | {self.date[:10]}"


@dataclass
class Injury:
    player: str
    team_name: str
    reason: str
    injury_type: str


@dataclass
class LineupPlayer:
    name: str
    number: int
    position: str


@dataclass
class TeamLineup:
    team: Team
    coach: str
    formation: str
    starting_xi: list
    substitutes: list


@dataclass
class WCFixture:
    fixture_id: int
    date: str
    round: str
    venue: str
    home_team: Team
    away_team: Team
    status: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None


@dataclass
class TeamStats:
    team: Team
    form: str                          # e.g. "WWDLW"
    played: int
    wins: int
    draws: int
    losses: int
    goals_for_avg: str                 # e.g. "2.1"
    goals_against_avg: str
    clean_sheets: int
    biggest_win: Optional[str]         # e.g. "3-0"
    biggest_loss: Optional[str]
    win_streak: int
    preferred_formation: Optional[str] # most-used formation this season


@dataclass
class StandingsEntry:
    rank: int
    team: Team
    group: str
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_diff: int
    form: str
    description: Optional[str]


@dataclass
class ApiPrediction:
    winner_name: Optional[str]
    winner_comment: Optional[str]
    advice: str
    home_percent: str
    draw_percent: str
    away_percent: str
    under_over: Optional[str]
    goals_home: Optional[str]
    goals_away: Optional[str]
    form_home: str
    form_away: str
    att_home: str
    att_away: str
    def_home: str
    def_away: str
    total_home: str
    total_away: str
