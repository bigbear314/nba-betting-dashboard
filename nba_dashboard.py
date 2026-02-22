import streamlit as st
import json
import numpy as np
from scipy.stats import norm
from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime

st.set_page_config(page_title="NBA Player & Team Edge Engine", layout="centered")
st.title("🏀 NBA Edge Engine (v3 Compatible)")

# -----------------------------
# Load team ratings safely
# -----------------------------
with open("team_ratings.json") as f:
    team_ratings = json.load(f)

default_team = {"off": 114, "def": 114, "pace": 100, "volatility": 1.0}

# -----------------------------
# Load player ratings safely
# -----------------------------
with open("player_ratings.json") as f:
    player_ratings = json.load(f)

# -----------------------------
# Auto-detect today's slate
# -----------------------------
today = datetime.today().strftime('%Y-%m-%d')

try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today)
    data = scoreboard.get_dict()
except:
    st.error("Could not load today's games.")
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
# Team Projections
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

# Volatility (for std dev)
std_dev_team = 12 * ((away_data["volatility"] + home_data["volatility"]) / 2)
total_projection = away_proj + home_proj

# -----------------------------
# Market input
# -----------------------------
st.subheader("Game Total Line")
line = st.number_input("Sportsbook Total Line", value=total_projection)
odds = st.number_input("American Odds", value=-110)

prob_over = 1 - norm.cdf(line, total_projection, std_dev_team)
prob_under = norm.cdf(line, total_projection, std_dev_team)

if odds < 0:
    decimal_odds = 1 + 100 / abs(odds)
else:
    decimal_odds = 1 + odds / 100

implied_prob = 1 / decimal_odds
edge = prob_over - implied_prob
ev = (prob_over * (decimal_odds - 1)) - (1 - prob_over)

st.subheader("Team Total Projection")
st.write(f"Projected Total: {total_projection:.2f}")
st.write(f"Over Probability: {prob_over*100:.2f}% | Under Probability: {prob_under*100:.2f}%")
st.write(f"Edge vs Market: {edge*100:.2f}% | EV: {ev:.3f} units")

# -----------------------------
# Player Prop Module
# -----------------------------
st.divider()
st.subheader("Player Prop Edge Engine")

player_names = list(player_ratings.keys())
selected_player = st.selectbox("Select Player", player_names)
stat_choice = st.selectbox("Select Stat", ["pts", "reb", "ast", "PRA"])

player_data = player_ratings[selected_player]
team = player_data["team"]
team_data = team_ratings.get(team, default_team)

# Inputs
line = st.number_input(f"{selected_player} {stat_choice.upper()} Line", value=player_data[stat_choice])
odds = st.number_input("American Odds", value=-110, key="player_odds")
injury_impact = st.slider("Star or teammate injury impact (%)", 0, 20, 0)
b2b = st.checkbox("Back-to-back game?")

# Projection logic
base = player_data[stat_choice]
projection = base * (1 + player_data["usage"])        # usage scaling
projection *= team_data["off"] / 114                  # team offense adjustment
projection *= team_data["pace"] / 100                 # pace adjustment
projection *= 1.02                                    # assume home court
if b2b:
    projection *= 0.97
projection *= 1 - injury_impact / 100                # injury impact

std_dev = 3 * team_data["volatility"]               # typical player variance

# Probabilities & EV
prob_over = 1 - norm.cdf(line, projection, std_dev)
prob_under = norm.cdf(line, projection, std_dev)

if odds < 0:
    decimal_odds = 1 + 100 / abs(odds)
else:
    decimal_odds = 1 + odds / 100

implied_prob = 1 / decimal_odds
edge_over = prob_over - implied_prob
edge_under = prob_under - implied_prob
ev_over = (prob_over * (decimal_odds - 1)) - (1 - prob_over)
ev_under = (prob_under * (decimal_odds - 1)) - (1 - prob_under)

st.subheader(f"{selected_player} - {stat_choice.upper()} Prop")
st.write(f"Projection: {projection:.2f} {stat_choice.upper()}")
st.write(f"Over Probability: {prob_over*100:.2f}% | Under Probability: {prob_under*100:.2f}%")
st.write(f"Edge Over: {edge_over*100:.2f}% | Edge Under: {edge_under*100:.2f}%")
st.write(f"EV Over: {ev_over:.3f} units | EV Under: {ev_under:.3f} units")
st.caption("All projections include usage, pace, home/away, B2B, and injury adjustments.")