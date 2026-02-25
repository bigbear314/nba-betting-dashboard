import streamlit as st
import json
import pytz
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
game_date = st.date_input("Game Date", datetime.now(ZoneInfo("America/Chicago")).date())
today = game_date.strftime("%Y-%m-%d")
scoreboard = scoreboardv3.ScoreboardV3(game_date=today).get_dict()
try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today).get_dict()
except Exception as e:
    st.error(f"Could not load today's games: {e}")
    st.stop()

games = []
game_objects = scoreboard.get("scoreboard", {}).get("games", [])

for game in game_objects:
    home = game.get("homeTeam", {}).get("teamName")
    away = game.get("awayTeam", {}).get("teamName")
    status = game.get("gameStatusText", "")

    if home and away:
        games.append(f"{away} @ {home} ({status})")

if not games:
    st.warning("No games today.")
    st.stop()

selected_game = st.selectbox("Select Game", games)
away_team, home_team = selected_game.split(" @ ")
st.write(f"### {away_team} @ {home_team}")

# ---------------------------------------------------
# Team Mean Projections
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
# Players in this game
# ---------------------------------------------------
players_today = [
    p for p, d in player_ratings.items()
    if d.get("team") in [home_team, away_team]
]

if not players_today:
    st.error(f"No players found for {home_team} or {away_team}. Check player_ratings.json team names.")
    st.stop()

# ---------------------------------------------------
# Injury Manager (SAFE session_state usage)
# ---------------------------------------------------
st.subheader("Injury Manager (affects usage & projections)")

selected_injured = st.multiselect(
    "Select players to mark as Limited/Out:",
    options=players_today,
    default=st.session_state.get("injured_players", [])
)
st.session_state["injured_players"] = selected_injured

injury_settings = {}

for pname in selected_injured:
    status_key = f"status_{pname}"
    limited_key = f"limited_pct_{pname}"

    # Set defaults BEFORE widget creation
    if status_key not in st.session_state:
        st.session_state[status_key] = "Limited"
    if limited_key not in st.session_state:
        st.session_state[limited_key] = 15

    status = st.selectbox(
        f"Status for {pname}",
        ["Limited", "Out"],
        key=status_key
    )

    limited_pct = 0
    if status == "Limited":
        limited_pct = st.slider(
            f"Minutes/usage reduction % for {pname}",
            min_value=5,
            max_value=60,
            value=int(st.session_state[limited_key]),
            step=1,
            key=limited_key
        )

    injury_settings[pname] = {"status": status, "limited_pct": limited_pct}

st.caption("Out removes usage and redistributes to teammates. Limited reduces usage and redistributes the lost portion.")

# ---------------------------------------------------
# Usage adjustment + redistribution
# ---------------------------------------------------
usage_map = {p: float(player_ratings[p].get("usage", 0.0)) for p in players_today}
adjusted_usage = usage_map.copy()

team_players_map = {}
for p in players_today:
    team_players_map.setdefault(player_ratings[p]["team"], []).append(p)

def redistribute_lost_usage(team_players, usage_map_local, lost_usage):
    current = np.array([usage_map_local.get(p, 0.0) for p in team_players], dtype=float)
    total = float(current.sum())
    if total <= 0:
        per = lost_usage / max(1, len(team_players))
        for p in team_players:
            usage_map_local[p] = usage_map_local.get(p, 0.0) + per
        return usage_map_local

    shares = current / total
    for p, share in zip(team_players, shares):
        usage_map_local[p] = usage_map_local.get(p, 0.0) + lost_usage * float(share)
    return usage_map_local

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

usage_df = pd.DataFrame([{
    "Player": p,
    "Team": player_ratings[p]["team"],
    "Orig Usage": round(usage_map.get(p, 0.0), 3),
    "Adj Usage": round(adjusted_usage.get(p, 0.0), 3),
} for p in players_today])
st.write("### Usage adjustments (original → adjusted)")
st.dataframe(usage_df, width="stretch")

st.divider()

# ---------------------------------------------------
# Correlated Monte Carlo Game Simulation
# ---------------------------------------------------
st.subheader("Game Market Simulator (correlated scores)")

if "n_sims" not in st.session_state:
    st.session_state.n_sims = 15000

n_sims = st.slider("Simulation Runs", 5000, 50000, st.session_state.n_sims, step=5000, key="n_sims")

home_vol = float(home_data.get("volatility", 1.0))
away_vol = float(away_data.get("volatility", 1.0))

home_sd = get_team_sd(home_mean) * home_vol
away_sd = get_team_sd(away_mean) * away_vol
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

market_type = st.selectbox("Market Type", ["Moneyline", "Spread", "Total"], key="market_type")

# Persist odds/lines defaults BEFORE widgets
if "odds_input" not in st.session_state:
    st.session_state.odds_input = -110
if "spread_line" not in st.session_state:
    st.session_state.spread_line = -5.5
if "total_line" not in st.session_state:
    st.session_state.total_line = round(float(np.mean(totals)), 1)

odds_input = st.number_input("American Odds", value=int(st.session_state.odds_input), key="odds_input")

ev = 0.0

if market_type == "Moneyline":
    side = st.radio("Select Side", ["Home", "Away"], key="ml_side")
    home_prob = float(np.mean(margins > 0))
    away_prob = 1.0 - home_prob
    prob = home_prob if side == "Home" else away_prob
    st.write(f"{side} Win Probability: **{prob*100:.2f}%**")
    ev = calculate_ev(prob, int(odds_input))

elif market_type == "Spread":
    spread_line = st.number_input("Spread Line (Home perspective)", value=float(st.session_state.spread_line), key="spread_line")
    side = st.radio("Select Side", ["Home", "Away"], key="spread_side")
    home_cover_prob = float(np.mean(margins > spread_line))
    away_cover_prob = 1.0 - home_cover_prob
    prob = home_cover_prob if side == "Home" else away_cover_prob
    st.write(f"{side} Cover Probability: **{prob*100:.2f}%**")
    ev = calculate_ev(prob, int(odds_input))

elif market_type == "Total":
    total_line = st.number_input("Total Line", value=float(st.session_state.total_line), key="total_line")
    side = st.radio("Select Side", ["Over", "Under"], key="total_side")
    over_prob = float(np.mean(totals > total_line))
    under_prob = 1.0 - over_prob
    prob = over_prob if side == "Over" else under_prob
    st.write(f"{side} Probability: **{prob*100:.2f}%**")
    ev = calculate_ev(prob, int(odds_input))

st.write(f"### EV: **{ev:.3f} units**")
st.write(f"Projected Means — Home: {home_mean:.1f} | Away: {away_mean:.1f} | Total: {(home_mean+away_mean):.1f}")

st.divider()

# ---------------------------------------------------
# Player Prop Batch Monte Carlo (injury-aware usage)
# ---------------------------------------------------
st.subheader("Player Prop Batch Monte Carlo (injury-aware)")

stat_choice = st.selectbox("Stat", ["pts", "reb", "ast", "3pm", "PRA"], key="stat_choice")

if "prop_line" not in st.session_state:
    st.session_state.prop_line = 20.5
if "prop_odds" not in st.session_state:
    st.session_state.prop_odds = -110

prop_line = st.number_input("Sportsbook Line", value=float(st.session_state.prop_line), key="prop_line")
prop_odds = st.number_input("American Odds (Prop)", value=int(st.session_state.prop_odds), key="prop_odds")

b2b = st.checkbox("Back-to-Back Game?", key="b2b")

results = []

for player_name in players_today:
    player = player_ratings[player_name]
    team = player.get("team", "")
    team_data = team_ratings.get(team, default_team)

    base = float(player.get(stat_choice, 0))
    u = float(adjusted_usage.get(player_name, float(player.get("usage", 0.0))))

    if stat_choice == "pts":
        proj = base * (1 + u)
    elif stat_choice == "ast":
        proj = base * (1 + u * 0.7)
    elif stat_choice == "reb":
        proj = base * (1 + u * 0.25)
    elif stat_choice == "3pm":
        proj = base * (1 + u * 0.4)
    elif stat_choice == "PRA":
        proj = base * (1 + u * 0.6)
    else:
        proj = base

    proj *= float(team_data.get("off", 114)) / 114.0
    proj *= float(team_data.get("pace", 100)) / 100.0

    if b2b:
        proj *= 0.97

    vol = float(team_data.get("volatility", 1.0))
    if stat_choice == "3pm":
        sd = 1.2 * vol
    elif stat_choice == "ast":
        sd = 2.2 * vol
    elif stat_choice == "reb":
        sd = 2.6 * vol
    else:
        sd = 3.2 * vol

    sims = np.random.normal(proj, sd, n_sims)

    prob_over = float(np.mean(sims >= prop_line))
    prob_under = 1.0 - prob_over

    ev_over = calculate_ev(prob_over, int(prop_odds))
    ev_under = calculate_ev(prob_under, int(prop_odds))

    results.append({
        "Player": player_name,
        "Team": team,
        "Orig Usage": round(usage_map.get(player_name, 0.0), 3),
        "Adj Usage": round(adjusted_usage.get(player_name, 0.0), 3),
        "Projection": round(proj, 2),
        "Over %": round(prob_over * 100, 2),
        "Under %": round(prob_under * 100, 2),
        "EV Over": round(ev_over, 3),
        "EV Under": round(ev_under, 3)
    })

df = pd.DataFrame(results).sort_values(by="EV Over", ascending=False)
st.dataframe(df, width="stretch")
st.caption("Model includes injury-aware usage redistribution, correlated scoring, B2B, and volatility adjustments.")