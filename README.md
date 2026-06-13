# World Cup Analyzer

AI-powered match analysis and prediction for the FIFA World Cup 2026.

Pulls live data from API-Football across multiple endpoints, computes an in-house statistical forecast, and streams a structured, data-grounded analysis via any reasoning model on OpenRouter — then lets you interrogate the result in an interactive Q&A session.

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

Optional tuning (all have sensible defaults — see `config.py`):

| Variable | Description |
|---|---|
| `WCA_REASONING_EFFORT` | Thinking effort for reasoning models: `low` / `medium` / `high` (default `high`) |
| `WCA_MAX_TOKENS` | Response token budget (default `8000`) |
| `WCA_FORM_WEIGHT` | Weight of recent form vs. season averages in the model (default `0.5`) |
| `WCA_HOME_ADVANTAGE` | Home expected-goals multiplier (default `1.10`) |
| `WCA_MARKET_WEIGHT` | How strongly to anchor the model to de-vigged bookmaker odds, 0–1 (default `0.65`) |
| `WCA_MAX_MATCH_GOALS` | Cap on one match's goal contribution, to curb minnow stat-padding (default `4`) |
| `WCA_SHRINK_GAMES` | Phantom average-games added for small-sample shrinkage (default `4`) |
| `WCA_KELLY_FRACTION` | Fractional-Kelly multiplier used in `record` (default `0.25`) |

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
uv run python main.py analyze "Brazil" "France" --no-chat  # skip the interactive Q&A
```

Data is fetched concurrently with automatic retry on transient failures and rate limits; sections whose endpoints fail are skipped rather than aborting the run.

### Interactive Q&A

After the analysis streams, `analyze` drops into an interactive session where you can keep reasoning with the model and ask follow-up questions ("how would a back three change this?", "which under bet has the most edge?"). The full data dossier and the analysis stay in context. Press Enter on an empty line or type `exit` to finish. Use `--no-chat` to disable it; `analyze-day` runs without chat by default (`--chat` to enable per match).

---

## Prediction tracking

Every analysis appends its **Best Bet**, confidence, the best available bookmaker odds for that bet, and the in-house model's probability for it to `results/predictions.jsonl`. Once fixtures finish, `record` shows each bet alongside the final score and auto-grades common markets (1X2, over/under, both teams to score, Asian handicap, double chance, draw no bet). It reports:

- a running **win/loss record** and per-confidence breakdown;
- **flat 1-unit ROI** at best available odds;
- **fractional-Kelly ROI**, sizing each stake by the model's edge over the odds (`f = edge / (odds − 1)`, scaled by `WCA_KELLY_FRACTION`) — rewarding bets where the model genuinely disagreed with the market;
- a **Brier score** measuring how well-calibrated the model's probabilities were (0 = perfect, 0.25 = coin flip).

Unrecognized markets are listed but left ungraded. Re-analyzing a match supersedes its earlier ledger entry.

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
| API prediction | Win/draw/loss probabilities (often empty for these fixtures — used only when populated) |

Sections are skipped entirely when data is unavailable — no placeholder output is generated.

---

## In-house statistical model

Because API-Football's own `/predictions` endpoint returns mostly empty placeholders for World Cup 2026 fixtures, the tool computes its own forecast (`model.py`) from data it *can* fetch reliably — recent form, tournament goal averages, and the head-to-head record. It is a transparent bivariate-Poisson goals model:

1. Estimate each team's attacking and defensive goal rates from recent form (capped per match) and season averages, then **shrink** toward the league mean — so a small, noisy sample of thrashings against weak opposition can't run away with the estimate.
2. Convert those into expected goals for this matchup, adjusting for home advantage and nudging toward the head-to-head goal pattern.
3. **Anchor to the market:** when bookmaker odds are present, de-vig them into fair probabilities and blend the model toward them, then refit the goal rates to the blended probabilities. The market already prices in squad quality and strength of schedule that a raw goals-per-game number is blind to — without this, a minnow that beat even weaker teams looks like a world-beater.
4. Build the Poisson score grid and read every market off it: 1X2 probabilities, expected goals, over/under, both-teams-to-score, most likely scorelines, and fair odds.

This forecast is fed to the AI as its primary quantitative anchor and stored with each prediction for calibration scoring. Tune the market pull with `WCA_MARKET_WEIGHT` (set it to `0` for a pure, schedule-blind goals model).

---

## AI analysis

The model receives the full data dossier and produces a structured report covering:

- **Form & Momentum**
- **Head-to-Head**
- **Key Tactical Battle**
- **Players to Watch**
- **Injury Impact**
- **Prediction** — built around the in-house statistical forecast, ending with a single high-conviction **Best Bet** recommendation, a confidence rating, and a value argument against the bookmaker odds

Two things make the analysis trustworthy for a tournament that postdates the model's training data:

- **Reasoning** — reasoning/thinking models are run with configurable effort; their deliberation streams (dimmed) ahead of the answer.
- **Data grounding** — the system prompt forbids relying on the model's own memory of squads, form, or results. Every claim must trace to a line in the dossier, and the model is instructed to say "not available in the provided data" rather than guess.

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
