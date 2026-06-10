# World Cup Analyzer

AI-powered match analysis and prediction for the FIFA World Cup 2026.

Pulls live data from API-Football across multiple endpoints and streams a structured analysis via any model on OpenRouter, saving a self-contained HTML report per match.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [API-Football](https://www.api-football.com/) key — paid plan required for 2026 season data
- [OpenRouter](https://openrouter.ai/) key

---

## Setup

```bash
git clone <repo>
cd world-cup-analyzer

cp .env.example .env
# fill in your keys in .env

uv sync
```

---

## Configuration

`.env` variables:

| Variable | Description |
|---|---|
| `FOOTBALL_API_KEY` | API-Football key |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `OPENROUTER_MODEL` | Model to use, e.g. `anthropic/claude-sonnet-4-6` |
| `WC_LEAGUE_ID` | League ID (default: `1` — FIFA World Cup) |
| `WC_SEASON` | Season year (default: `2026`) |

---

## Usage

```bash
# List upcoming fixtures
uv run python main.py fixtures

# Analyze a match (team name or numeric ID)
uv run python main.py analyze "Mexico" "South Africa"
uv run python main.py analyze 16 1531

# Search for a team name / ID
uv run python main.py search "Korea"

# Analyze every fixture on a date (defaults to today, UTC)
uv run python main.py analyze-day
uv run python main.py analyze-day 2026-06-12

# Show recorded predictions and how they fared
uv run python main.py record
```

> The package also installs a `wca` entry point, so `uv run wca fixtures` works too.

> **Tip:** If a team name search resolves to a club instead of a national team, use the numeric ID directly. Run `search` to find it, or look it up from the `fixtures` output.

### Options

```bash
uv run python main.py fixtures --days 3          # next 3 days only
uv run python main.py fixtures --all             # all fixtures including finished

uv run python main.py analyze "Brazil" "France" --form 8   # last 8 matches per team
uv run python main.py analyze "Brazil" "France" --h2h 15   # last 15 H2H matches
```

Each `analyze` run saves a self-contained HTML report to `results/`. Data is fetched concurrently (4 workers) with automatic retry on transient failures and rate limits; sections whose endpoints fail are skipped rather than aborting the run.

---

## Prediction tracking

Every analysis appends its **Best Bet** and confidence to `results/predictions.jsonl`. Once fixtures finish, `record` shows each bet alongside the final score and auto-grades common markets (1X2, over/under, both teams to score, Asian handicap, double chance, draw no bet), with a running win/loss record. Unrecognized markets are listed but left ungraded. Re-analyzing a match supersedes its earlier ledger entry.

---

## Data sources

Each analysis pulls from the following API-Football endpoints:

| Data | What it provides |
|---|---|
| Tournament statistics | Record, goals, clean sheets, form string, preferred formation |
| Player statistics | Per-player goals, assists, shots on target, key passes, rating |
| Top scorers | Tournament goals leaderboard |
| Top assists | Tournament assists leaderboard |
| Disciplinary leaders | Yellow/red card counts — flags suspension risks |
| Recent form | Last N matches with inline goal scorers, minutes, and red cards |
| Head-to-head | Historical record between the two sides |
| Group standings | Current table with GD and rolling form |
| Injuries | Reported absences for the specific fixture |
| Lineups | Confirmed starting XIs (available ~40 min before kickoff) |
| Match events | Chronological goal/card timeline for the fixture |
| Fixture player ratings | Per-player ratings and stats from the specific match |
| Pre-match odds | 1X2 odds from up to 5 bookmakers |
| API prediction | Win/draw/loss probabilities and comparison metrics |

Sections are skipped entirely when data is unavailable — no placeholder output is generated.

---

## AI analysis

The AI receives all available data and produces a structured report covering:

- **Form & Momentum**
- **Head-to-Head**
- **Key Tactical Battle**
- **Players to Watch**
- **Injury Impact**
- **Prediction** — synthesizes the API-Football prediction with its own analysis, ending with a single high-conviction **Best Bet** recommendation and confidence rating

---

## Caching

API responses are cached in `cache/` to avoid redundant requests. TTLs:

| Data | TTL |
|---|---|
| Fixtures / standings | 60 min |
| Recent form / team stats / players | 30 min |
| Injuries / lineups / predictions / odds / events | 15–60 min |
| Teams / H2H | 24 h |

Error responses (rate limits, plan limits) are never cached. Clear the cache manually with `rm -rf cache/`.

---

## Development

```bash
uv run pytest
```
