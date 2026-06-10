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
class PlayerStat:
    player_id: int
    name: str
    appearances: int
    minutes: int
    goals: int
    assists: int
    shots_on: int
    key_passes: int
    rating: Optional[str]
    yellow_cards: int
    red_cards: int


@dataclass
class FixtureTeamStat:
    team: Team
    possession: Optional[str]
    shots_total: Optional[int]
    shots_on: Optional[int]
    corners: Optional[int]
    passes_total: Optional[int]
    pass_accuracy: Optional[str]
    fouls: Optional[int]
    offsides: Optional[int]
    saves: Optional[int]


@dataclass
class Last5:
    form_pct: str        # e.g. "87%"
    att_pct: str         # e.g. "92%"
    def_pct: str         # e.g. "75%"
    goals_for_avg: str   # e.g. "2.2"
    goals_against_avg: str
    goals_for_total: int
    goals_against_total: int


@dataclass
class UnderOver:
    over_0_5: int
    under_0_5: int
    over_1_5: int
    under_1_5: int
    over_2_5: int
    under_2_5: int
    over_3_5: int
    under_3_5: int
    over_4_5: int
    under_4_5: int


@dataclass
class ApiPrediction:
    winner_name: Optional[str]
    winner_comment: Optional[str]
    win_or_draw: bool
    advice: str
    home_percent: str
    draw_percent: str
    away_percent: str
    under_over: Optional[str]
    goals_home: Optional[str]
    goals_away: Optional[str]
    # comparison
    form_home: str
    form_away: str
    att_home: str
    att_away: str
    def_home: str
    def_away: str
    poisson_home: str
    poisson_away: str
    h2h_home: str
    h2h_away: str
    goals_comp_home: str
    goals_comp_away: str
    total_home: str
    total_away: str
    # last 5 match ratings per team
    last_5_home: Optional[Last5]
    last_5_away: Optional[Last5]
    # under/over counts from league stats
    home_under_over: Optional[UnderOver]
    away_under_over: Optional[UnderOver]


@dataclass
class FixtureEvent:
    minute: int
    extra_minute: Optional[int]
    team: Team
    player: str
    assist: Optional[str]
    type: str      # "Goal", "Card", "subst", "Var"
    detail: str    # "Normal Goal", "Own Goal", "Penalty", "Yellow Card", "Red Card"
    comments: Optional[str]


@dataclass
class BookmakerOdds:
    bookmaker: str
    home: str
    draw: str
    away: str


@dataclass
class FixturePlayerStat:
    player_id: int
    name: str
    team: Team
    minutes: int
    rating: Optional[str]
    goals: int
    assists: int
    shots_on: int
    key_passes: int
    tackles: int
    saves: int
    yellow_cards: int
    red_cards: int
