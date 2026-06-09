# World Cup Analyzer

AI-powered match analysis and prediction for the FIFA World Cup 2026.

Pulls live data from API-Football (form, head-to-head, standings, injuries, lineups) and streams a structured analysis via any model on OpenRouter.

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

# Analyze a match
uv run python main.py analyze "Mexico" "South Africa"

# Search for a team name / ID
uv run python main.py search "Korea"
```

### Options

```bash
uv run python main.py fixtures --days 3          # next 3 days only
uv run python main.py fixtures --all             # all fixtures including finished

uv run python main.py analyze "Brazil" "France" --form 8   # last 8 matches per team
uv run python main.py analyze "Brazil" "France" --h2h 15   # last 15 H2H matches
```

Each `analyze` run saves a self-contained HTML report to `results/`.

---

## Data sources

Each analysis includes:

- **Tournament statistics** — record, goals, clean sheets, form, preferred formation
- **Recent form** — last N matches across all competitions
- **Head-to-head** — historical record between the two sides
- **Group standings** — current table with GD and form
- **Injuries** — reported absences for the specific fixture
- **Lineups** — confirmed starting XIs (available ~40 min before kickoff)
- **API prediction** — win/draw/loss probabilities and comparison metrics from API-Football

---

## Caching

API responses are cached in `cache/` to avoid redundant requests. TTLs:

| Data | TTL |
|---|---|
| Fixtures / standings | 60 min |
| Recent form / team stats | 30 min |
| Injuries / lineups / predictions | 15 min |
| Teams / H2H | 24 h |

Clear the cache manually with `rm -rf cache/`.
