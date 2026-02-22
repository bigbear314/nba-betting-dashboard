import streamlit as st
import json
import numpy as np
from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime
from scipy.stats import norm

# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(page_title="NBA Edge Engine", layout="centered")
st.title("🏀 NBA Edge Engine with Monte Carlo Player Props")

# -----------------------------
# Load team ratings safely
# -----------------------------
try:
    with open("team_ratings.json") as f:
        team_ratings = json.load(f)
except Exception as e:
    st.error(f"Error loading team_ratings.json: {e}")
    st.stop()

default_team = {"off": 114, "def": 114, "pace": 100, "volatility": 1.0}

# -----------------------------
# Load player ratings safely
# -----------------------------
try:
    with open("player_ratings.json") as f:
        player_ratings = json.load(f)
except Exception as e:
    st.error(f"Error loading player_ratings.json: {e}")
    st.stop()

# -----------------------------
# Auto-detect today's slate
# -----------------------------
today = datetime.today().strftime('%Y-%m-%d')

try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today)
    data = scoreboard.get_dict()
except Exception as e:
    st.error(f"Could not load today's games: {e}")
    st.stop()

games = []
for game in data.get("scoreboard", {}).get("games", []):
    home_team = game["homeTeam"]["teamName"]
    away_team = game["awayTeam"]["teamName"]
    games.append(f"{away_team} @ {home_team}")

if not games:
    st.warning("No games today.")
    st.stop()

selected_game = st.selectbox("Select Game", games)
away_team, home_team = selected_game.split(" @ ")
st.write(f"Selected matchup: **{away_team} @ {home_team}**")

# -----------------------------
# Team total projection & EV
# -----------------------------
away_data = team_ratings.get(away_team, default_team)
home_data = team_ratings.get(home_team, default_team)

avg_pace = (away_data["pace"] + home_data["pace"]) / 2

away_proj = (away_data["off"] / 114) * (home_data["def"] / 114) * 112
home_proj = (home_data["off"] / 114) * (away_data["def"] / 114) * 112

away_proj *= avg_pace / 100
home_proj *= avg_pace / 100

# Home court baked in
home_proj *= 1.025
away_proj *= 0.975

std_dev_team = 12 * ((away_data["volatility"] + home_data["volatility"]) / 2)
total_projection = away_proj + home_proj

st.subheader("Game Total Projection")
line_total = st.number_input("Sportsbook Total Line", value=total_projection)
odds_total = st.number_input("American Odds", value=-110)

prob_over_total = 1 - norm.cdf(line_total, total_projection, std_dev_team)
prob_under_total = 1 - prob_over_total

decimal_odds_total = 1 + (100 / abs(odds_total) if odds_total < 0 else odds_total / 100)
implied_prob_total = 1 / decimal_odds_total
edge_total = prob_over_total - implied_prob_total
ev_total = (prob_over_total * (decimal_odds_total - 1)) - (1 - prob_over_total)

st.write(f"Projected Total: {total_projection:.2f}")
st.write(f"Over Probability: {prob_over_total*100:.2f}% | Under Probability: {prob_under_total*100:.2f}%")
st.write(f"Edge vs Market: {edge_total*100:.2f}% | EV: {ev_total:.3f} units")

st.divider()

# -----------------------------
# Player prop Monte Carlo module
# -----------------------------
st.subheader("Player Prop Edge Engine")

player_names = list(player_ratings.keys())
selected_player = st.selectbox("Select Player", player_names)
stat_choice = st.selectbox("Select Stat", ["pts", "reb", "ast", "PRA"])

player = player_ratings[selected_player]
team = player["team"]
team_data = team_ratings.get(team, default_team)

# Inputs
line_player = st.number_input(f"{selected_player} {stat_choice.upper()} Line", value=player[stat_choice])
odds_player = st.number_input("American Odds", value=-110, key="player_odds")
injury_impact = st.slider("Star or teammate injury impact (%)", 0, 20, 0)
b2b = st.checkbox("Back-to-back game?")

n_sim = st.number_input("Number of Simulations", min_value=1000, max_value=100000, value=10000, step=1000)

# Base projection
proj = player[stat_choice] * (1 + player["usage"])
proj *= team_data["off"] / 114
proj *= team_data["pace"] / 100
proj *= 1.02  # home court
if b2b:
    proj *= 0.97
proj *= 1 - injury_impact / 100

std_dev = 3 * team_data["volatility"]

# Monte Carlo simulation
sim_results = np.random.normal(proj, std_dev, n_sim)
prob_over = np.mean(sim_results >= line_player)
prob_under = np.mean(sim_results < line_player)

decimal_odds_player = 1 + (100 / abs(odds_player) if odds_player < 0 else odds_player / 100)
implied_prob_player = 1 / decimal_odds_player

edge_over = prob_over - implied_prob_player
edge_under = prob_under - implied_prob_player
ev_over = (prob_over * (decimal_odds_player - 1)) - (1 - prob_over)
ev_under = (prob_under * (decimal_odds_player - 1)) - (1 - prob_under)

st.subheader(f"{selected_player} - {stat_choice.upper()} Prop Monte Carlo")
st.write(f"Projection (mean): {proj:.2f} {stat_choice.upper()}")
st.write(f"Over Probability: {prob_over*100:.2f}% | Under Probability: {prob_under*100:.2f}%")
st.write(f"Edge Over: {edge_over*100:.2f}% | Edge Under: {edge_under*100:.2f}%")
st.write(f"EV Over: {ev_over:.3f} units | EV Under: {ev_under:.3f} units")
st.write(f"Simulated {n_sim} games")
st.caption("Projections include usage, pace, home/away, B2B, and injury adjustments.")