import streamlit as st
import json
import numpy as np
import pandas as pd
from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime

st.set_page_config(page_title="NBA Pro Monte Carlo Dashboard", layout="centered")
st.title("🏀 NBA Pro Monte Carlo Betting Dashboard")

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def american_to_profit(odds: int) -> float:
    """Profit per 1 unit stake (excludes stake)."""
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)

def calculate_ev(prob: float, odds: int) -> float:
    """EV in units per 1 unit stake."""
    profit = american_to_profit(odds)
    return (prob * profit) - (1 - prob)

def get_team_sd(mean_points: float) -> float:
    """Calibrated NBA-ish team score SD."""
    base_sd = 11.0
    return base_sd * (mean_points / 110.0)

# ---------------------------------------------------
# Load JSON Data
# ---------------------------------------------------
try:
    with open("team_ratings.json") as f:
        team_ratings = json.load(f)
except Exception as e:
    st.error(f"Error loading team_ratings.json: {e}")
    st.stop()

try:
    with open("player_ratings.json") as f:
        player_ratings = json.load(f)
except Exception as e:
    st.error(f"Error loading player_ratings.json: {e}")
    st.stop()

default_team = {"off": 114, "def": 114, "pace": 100, "volatility": 1.0}

# ---------------------------------------------------
# Detect Today's Slate
# ---------------------------------------------------
today = datetime.today().strftime("%Y-%m-%d")
try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today).get_dict()
except Exception as e:
    st.error(f"Could not load today's games: {e}")
    st.stop()

games = []
for game in scoreboard.get("scoreboard", {}).get("games", []):
    home = game["homeTeam"]["teamName"]
    away = game["awayTeam"]["teamName"]
    games.append(f"{away} @ {home}")

if not games:
    st.warning("No games today.")
    st.stop()

selected_game = st.selectbox("Select Game", games)
away_team, home_team = selected_game.split(" @ ")
st.write(f"### {away_team} @ {home_team}")

# ---------------------------------------------------
# Team Mean Projections (inputs to game simulation)
# ---------------------------------------------------
away_data = team_ratings.get(away_team, default_team)
home_data = team_ratings.get(home_team, default_team)

avg_pace = (away_data["pace"] + home_data["pace"]) / 2.0

away_mean = (away_data["off"] / 114.0) * (home_data["def"] / 114.0) * 112.0
home_mean = (home_data["off"] / 114.0) * (away_data["def"] / 114.0) * 112.0

away_mean *= avg_pace / 100.0
home_mean *= avg_pace / 100.0

# Home court
home_mean *= 1.025
away_mean *= 0.975

# ---------------------------------------------------
# Correlated Monte Carlo Game Simulation
# ---------------------------------------------------
st.subheader("Game Market Simulator")

if "n_sims" not in st.session_state:
    st.session_state.n_sims = 15000

n_sims = st.slider("Simulation Runs", 5000, 50000, st.session_state.n_sims, step=5000, key="n_sims")

home_sd = get_team_sd(home_mean)
away_sd = get_team_sd(away_mean)

# Correlation between team scores (pace/tempo/game script)
rho = 0.30
cov = [
    [home_sd**2, rho * home_sd * away_sd],
    [rho * home_sd * away_sd, away_sd**2]
]

samples = np.random.multivariate_normal([home_mean, away_mean], cov, n_sims)
home_scores = samples[:, 0]
away_scores = samples[:, 1]

margins = home_scores - away_scores
totals = home_scores + away_scores

st.subheader("Game Market Simulator")

market_type = st.selectbox(
    "Market Type",
    ["Moneyline", "Spread", "Total"]
)

# Persist odds
if "odds_input" not in st.session_state:
    st.session_state.odds_input = -110

odds_input = st.number_input(
    "American Odds",
    value=int(st.session_state.odds_input),
    key="odds_input"
)

ev = 0.0

# -------------------
# MONEYLINE
# -------------------
if market_type == "Moneyline":

    side = st.radio("Select Side", ["Home", "Away"])

    home_prob = float(np.mean(margins > 0))
    away_prob = 1.0 - home_prob

    if side == "Home":
        prob = home_prob
        st.write(f"Home Win Probability: **{prob*100:.2f}%**")
    else:
        prob = away_prob
        st.write(f"Away Win Probability: **{prob*100:.2f}%**")

    ev = calculate_ev(prob, odds_input)

# -------------------
# SPREAD
# -------------------
elif market_type == "Spread":

    if "spread_line" not in st.session_state:
        st.session_state.spread_line = -5.5

    spread_line = st.number_input(
        "Spread Line (Home perspective)",
        value=float(st.session_state.spread_line),
        key="spread_line"
    )

    side = st.radio("Select Side", ["Home", "Away"])

    home_cover_prob = float(np.mean(margins > spread_line))
    away_cover_prob = 1.0 - home_cover_prob

    if side == "Home":
        prob = home_cover_prob
        st.write(f"Home Cover Probability: **{prob*100:.2f}%**")
    else:
        prob = away_cover_prob
        st.write(f"Away Cover Probability: **{prob*100:.2f}%**")

    ev = calculate_ev(prob, odds_input)

# -------------------
# TOTAL
# -------------------
elif market_type == "Total":

    default_total = round(float(np.mean(totals)), 1)

    if "total_line" not in st.session_state:
        st.session_state.total_line = default_total

    total_line = st.number_input(
        "Total Line",
        value=float(st.session_state.total_line),
        key="total_line"
    )

    side = st.radio("Select Side", ["Over", "Under"])

    over_prob = float(np.mean(totals > total_line))
    under_prob = 1.0 - over_prob

    if side == "Over":
        prob = over_prob
        st.write(f"Over Probability: **{prob*100:.2f}%**")
    else:
        prob = under_prob
        st.write(f"Under Probability: **{prob*100:.2f}%**")

    ev = calculate_ev(prob, odds_input)

st.write(f"### EV: **{ev:.3f} units**")

st.divider()

# ---------------------------------------------------
# Player Prop Batch Monte Carlo
# ---------------------------------------------------
st.subheader("Player Prop Batch Monte Carlo")

stat_choice = st.selectbox("Stat", ["pts", "reb", "ast", "3pm", "PRA"], key="stat_choice")

# Persist prop inputs
if "prop_line" not in st.session_state:
    st.session_state.prop_line = 20.5
if "prop_odds" not in st.session_state:
    st.session_state.prop_odds = -110

prop_line = st.number_input("Sportsbook Line", value=float(st.session_state.prop_line), key="prop_line")
prop_odds = st.number_input("American Odds (Prop)", value=int(st.session_state.prop_odds), key="prop_odds")

injury_impact = st.slider("Injury Impact (%)", 0, 20, 0, key="injury_impact")
b2b = st.checkbox("Back-to-Back Game?", key="b2b")

players_today = [
    p for p, data in player_ratings.items()
    if data.get("team") in [home_team, away_team]
]

if not players_today:
    st.error(f"No players found for {home_team} or {away_team}. Check player_ratings.json team names.")
    st.stop()

results = []

for player_name in players_today:
    player = player_ratings[player_name]
    team = player.get("team", "")
    team_data = team_ratings.get(team, default_team)

    base = float(player.get(stat_choice, 0))

    # Usage scaling by stat type (more realistic)
    usage = float(player.get("usage", 0))

    if stat_choice == "pts":
        proj = base * (1 + usage)
    elif stat_choice == "ast":
        proj = base * (1 + usage * 0.7)
    elif stat_choice == "reb":
        proj = base * (1 + usage * 0.25)
    elif stat_choice == "3pm":
        proj = base * (1 + usage * 0.4)
    elif stat_choice == "PRA":
        proj = base * (1 + usage * 0.6)
    else:
        proj = base

    proj *= float(team_data.get("off", 114)) / 114.0
    proj *= float(team_data.get("pace", 100)) / 100.0

    if b2b:
        proj *= 0.97

    proj *= (1 - injury_impact / 100.0)

    # Stat-specific SD
    vol = float(team_data.get("volatility", 1.0))
    if stat_choice == "3pm":
        sd = 1.2 * vol
    elif stat_choice == "ast":
        sd = 2.2 * vol
    elif stat_choice == "reb":
        sd = 2.6 * vol
    else:  # pts or PRA
        sd = 3.2 * vol

    sims = np.random.normal(proj, sd, n_sims)

    # ✅ Correct probability vs sportsbook line
    prob_over = float(np.mean(sims >= prop_line))
    prob_under = 1.0 - prob_over

    ev_over = calculate_ev(prob_over, int(prop_odds))
    ev_under = calculate_ev(prob_under, int(prop_odds))

    results.append({
        "Player": player_name,
        "Team": team,
        "Projection": round(proj, 2),
        "Over %": round(prob_over * 100, 2),
        "Under %": round(prob_under * 100, 2),
        "EV Over": round(ev_over, 3),
        "EV Under": round(ev_under, 3)
    })

df = pd.DataFrame(results)
df = df.sort_values(by="EV Over", ascending=False)

st.dataframe(df, width="stretch")
st.caption("Game sim uses correlated scoring; props include usage, pace, volatility, injury, and B2B adjustments.")