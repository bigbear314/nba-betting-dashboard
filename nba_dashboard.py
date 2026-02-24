# app_with_injury_redistribution.py
import streamlit as st
import json
import numpy as np
import pandas as pd
from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime

st.set_page_config(page_title="NBA Pro Monte Carlo Dashboard (Injury-aware)", layout="centered")
st.title("🏀 NBA Pro Monte Carlo Betting Dashboard (Injury-aware)")

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def american_to_profit(odds: int) -> float:
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)

def calculate_ev(prob: float, odds: int) -> float:
    profit = american_to_profit(odds)
    return (prob * profit) - (1 - prob)

def get_team_sd(mean_points: float) -> float:
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

home_mean *= 1.025
away_mean *= 0.975

# ---------------------------------------------------
# Build players_today list (rotation players in data)
# ---------------------------------------------------
players_today = [
    p for p, d in player_ratings.items()
    if d.get("team") in [home_team, away_team]
]

if not players_today:
    st.error(f"No players found for {home_team} or {away_team}. Check player_ratings.json team names.")
    st.stop()

# Create a small helper map for quick lookup
players_info = {p: player_ratings[p] for p in players_today}

# ---------------------------------------------------
# Injury Manager UI
# ---------------------------------------------------
st.subheader("Injury Manager (affects usage & projections)")

# Persist injured players selection in session_state to avoid reset
if "injured_players" not in st.session_state:
    st.session_state.injured_players = []

# Multiselect to pick injured/limited players from today's rotation
selected_injured = st.multiselect(
    "Select players to mark as Limited/Out (choose any number):",
    options=players_today,
    default=st.session_state.injured_players
)

st.session_state.injured_players = selected_injured

# For each selected injured player, capture a status and a limited % (if limited)
injury_settings = {}
for pname in selected_injured:
    # unique keys for each player's controls
    status_key = f"status_{pname}"
    limited_pct_key = f"limited_pct_{pname}"

    # default status stored
    if status_key not in st.session_state:
        st.session_state[status_key] = "Limited"  # default to limited for convenience

    status = st.selectbox(
        f"Status for {pname}",
        options=["Limited", "Out"],
        index=0 if st.session_state[status_key] == "Limited" else 1,
        key=status_key
    )
    st.session_state[status_key] = status

    limited_pct = 0
    if status == "Limited":
        if limited_pct_key not in st.session_state:
            st.session_state[limited_pct_key] = 15  # default 15% reduction
        limited_pct = st.slider(
            f"Minutes/usage reduction % for {pname}",
            min_value=5,
            max_value=60,
            value=int(st.session_state[limited_pct_key]),
            step=1,
            key=limited_pct_key
        )
        st.session_state[limited_pct_key] = limited_pct

    injury_settings[pname] = {"status": status, "limited_pct": limited_pct}

st.caption("When a player is 'Out' their usage is removed and redistributed proportionally to teammates. 'Limited' reduces their usage and redistributes the lost portion to teammates.")

# ---------------------------------------------------
# Apply injury adjustments: compute adjusted_usage_map
# ---------------------------------------------------
# Start from base usages
usage_map = {p: float(player_ratings[p].get("usage", 0.0)) for p in players_today}

# Helper function to redistribute lost usage for a team
def redistribute_lost_usage(team_players, usage_map_local, lost_usage):
    """
    Distribute lost_usage among the provided team_players (list of names),
    proportionally to their current usage values. If all usages are zero,
    split equally.
    """
    # compute current usages for eligible teammates
    current_usages = np.array([usage_map_local.get(p, 0.0) for p in team_players], dtype=float)
    total = current_usages.sum()
    if total <= 0:
        # equal split
        per = lost_usage / max(1, len(team_players))
        for p in team_players:
            usage_map_local[p] = usage_map_local.get(p, 0.0) + per
        return usage_map_local

    shares = current_usages / total
    for p, share in zip(team_players, shares):
        usage_map_local[p] = usage_map_local.get(p, 0.0) + lost_usage * float(share)

    return usage_map_local

# Apply injuries per team
# Group players by team
team_players_map = {}
for p in players_today:
    team_players_map.setdefault(player_ratings[p]["team"], []).append(p)

# We'll modify a local copy of usage_map
adjusted_usage = usage_map.copy()

# Iterate selected injured players, compute lost usage, and redistribute to teammates
for pname, settings in injury_settings.items():
    if pname not in adjusted_usage:
        continue
    team = player_ratings[pname]["team"]
    teammates = [x for x in team_players_map.get(team, []) if x != pname]
    if settings["status"] == "Out":
        lost = adjusted_usage.get(pname, 0.0)
        adjusted_usage[pname] = 0.0
        if teammates and lost > 0:
            adjusted_usage = redistribute_lost_usage(teammates, adjusted_usage, lost)
    elif settings["status"] == "Limited":
        pct = float(settings.get("limited_pct", 0.0)) / 100.0
        orig = adjusted_usage.get(pname, 0.0)
        lost = orig * pct
        adjusted_usage[pname] = orig * (1.0 - pct)
        if teammates and lost > 0:
            adjusted_usage = redistribute_lost_usage(teammates, adjusted_usage, lost)

# For clarity show a small table of usage adjustments
usage_df = pd.DataFrame([{
    "Player": p,
    "Team": player_ratings[p]["team"],
    "Orig Usage": round(usage_map.get(p, 0.0), 3),
    "Adj Usage": round(adjusted_usage.get(p, 0.0), 3)
} for p in players_today])
st.write("### Usage adjustments (original → adjusted)")
st.dataframe(usage_df, width="stretch")

# ---------------------------------------------------
# Correlated Monte Carlo Game Simulation
# ---------------------------------------------------
st.subheader("Game Simulation (correlated scores)")

if "n_sims" not in st.session_state:
    st.session_state.n_sims = 15000

n_sims = st.slider("Simulation Runs", 5000, 50000, st.session_state.n_sims, step=5000, key="n_sims")

home_sd = get_team_sd(home_mean)
away_sd = get_team_sd(away_mean)
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

# ---------------------------------------------------
# Market selector (with side toggles)
# ---------------------------------------------------
market_type = st.selectbox("Market Type", ["Moneyline", "Spread", "Total"], key="market_type")

# Persist odds and lines
if "odds_input" not in st.session_state:
    st.session_state.odds_input = -110
if "spread_line" not in st.session_state:
    st.session_state.spread_line = -5.5
if "total_line" not in st.session_state:
    st.session_state.total_line = round(float(np.mean(totals)), 1)