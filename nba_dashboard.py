import streamlit as st
import numpy as np
import json
from scipy.stats import norm
from nba_api.stats.endpoints import scoreboardv3
from nba_api.stats.static import teams
from datetime import datetime

from scipy.stats import norm

st.set_page_config(page_title="NBA Edge Engine", layout="centered")

st.title("NBA Auto Slate Betting Engine")

# ----------------------
# BASIC TEAM RATINGS
# ----------------------

league_avg_rating = 114
league_avg_pace = 100

team_off = {}
team_def = {}
team_pace = {}

# ----------------------
# GET TODAY'S GAMES
# ----------------------

from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime

today = datetime.today().strftime('%Y-%m-%d')

try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today)
    data = scoreboard.get_dict()
except:
    st.error("Could not load today's games.")
    st.stop()

games = []

if "scoreboard" in data and "games" in data["scoreboard"]:
    for game in data["scoreboard"]["games"]:
        home_team = game["homeTeam"]["teamName"]
        away_team = game["awayTeam"]["teamName"]
        games.append(f"{away_team} @ {home_team}")

if len(games) == 0:
    st.warning("No games today.")
    st.stop()

selected_game = st.selectbox("Select Game", games)

away_team, home_team = selected_game.split(" @ ")

# ----------------------
# SIMPLE MANUAL RATINGS INPUT
# ----------------------

st.subheader("Enter Team Ratings")

away_off = st.number_input(f"{away_team} Offensive Rating", value=115.0)
away_def = st.number_input(f"{away_team} Defensive Rating", value=112.0)
away_pace = st.number_input(f"{away_team} Pace", value=100.0)

home_off = st.number_input(f"{home_team} Offensive Rating", value=116.0)
home_def = st.number_input(f"{home_team} Defensive Rating", value=111.0)
home_pace = st.number_input(f"{home_team} Pace", value=100.0)

# ----------------------
# INJURY ADJUSTMENT
# ----------------------

st.subheader("Injury Adjustment")

injury_team = st.selectbox(
    "Apply Injury Impact To:",
    ["None", away_team, home_team]
)

injury_percent = st.slider("Offensive Reduction %", 0, 20, 5)

# ----------------------
# PROJECTION LOGIC
# ----------------------

avg_pace = (away_pace + home_pace) / 2

away_projection = (away_off / league_avg_rating) * (home_def / league_avg_rating) * 110
home_projection = (home_off / league_avg_rating) * (away_def / league_avg_rating) * 110

away_projection *= (avg_pace / league_avg_pace)
home_projection *= (avg_pace / league_avg_pace)

# home advantage
home_projection *= 1.02
away_projection *= 0.98

# injury impact
if injury_team == away_team:
    away_projection *= (1 - injury_percent / 100)

if injury_team == home_team:
    home_projection *= (1 - injury_percent / 100)

total_projection = away_projection + home_projection

# ----------------------
# MARKET INPUT
# ----------------------

st.subheader("Market Line")

line = st.number_input("Sportsbook Total", value=220.5)
odds = st.number_input("American Odds", value=-110)

std_dev = 12

prob_over = 1 - norm.cdf(line, total_projection, std_dev)
prob_under = norm.cdf(line, total_projection, std_dev)

if odds < 0:
    decimal_odds = 1 + (100 / abs(odds))
else:
    decimal_odds = 1 + (odds / 100)

implied_prob = 1 / decimal_odds
edge = prob_over - implied_prob
ev = (prob_over * (decimal_odds - 1)) - (1 - prob_over)

# ----------------------
# OUTPUT
# ----------------------

st.subheader("Model Output")

st.write(f"Projected Total: {round(total_projection, 2)}")

st.write(f"Over Probability: {round(prob_over * 100, 2)}%")
st.write(f"Under Probability: {round(prob_under * 100, 2)}%")

st.write(f"Edge vs Market: {round(edge * 100, 2)}%")
st.write(f"Expected Value: {round(ev, 3)} units")

# Load player ratings
with open("player_ratings.json") as f:
    players = json.load(f)

player_names = list(players.keys())
selected_player = st.selectbox("Select Player", player_names)

stat_choice = st.selectbox("Select Stat", ["pts", "reb", "ast", "PRA"])

player_data = players[selected_player]

# Load team ratings
with open("team_ratings.json") as f:
    team_ratings = json.load(f)

team = player_data["team"]
team_data = team_ratings.get(team, {"off": 114, "def": 114, "pace": 100, "volatility": 1.0})

# ----------------------
# Inputs
# ----------------------
line = st.number_input("Sportsbook Line", value=player_data[stat_choice])
odds = st.number_input("American Odds", value=-110)
injury_impact = st.slider("Star or teammate injury impact (%)", 0, 20, 0)
b2b = st.checkbox("Back-to-back game?")

# ----------------------
# Auto Projection Logic
# ----------------------
base = player_data[stat_choice]

# Usage scaling (simple hybrid)
projection = base * (1 + player_data["usage"])  # inflates high-usage players

# Team offensive adjustment
projection *= team_data["off"] / 114
projection *= team_data["pace"] / 100

# Home/away (for simplicity assume home)
projection *= 1.02

# Back-to-back
if b2b:
    projection *= 0.97

# Injury impact
projection *= 1 - injury_impact / 100

# Volatility
std_dev = 3 * team_data["volatility"]  # typical player game variance

# ----------------------
# Probabilities & EV
# ----------------------
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

# ----------------------
# Output
# ----------------------
st.subheader(f"{selected_player} - {stat_choice.upper()} Prop")

st.write(f"Projection: {projection:.2f} {stat_choice.upper()}")
st.write(f"Over Probability: {prob_over*100:.2f}% | Under Probability: {prob_under*100:.2f}%")
st.write(f"Edge Over: {edge_over*100:.2f}% | Edge Under: {edge_under*100:.2f}%")
st.write(f"EV Over: {ev_over:.3f} units | EV Under: {ev_under:.3f} units")

st.caption("Model simulation. Not financial advice.")