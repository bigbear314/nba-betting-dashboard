import streamlit as st
import numpy as np
from scipy.stats import norm
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams
from datetime import datetime

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

today = datetime.today().strftime('%m/%d/%Y')

try:
    scoreboard = scoreboardv2.ScoreboardV2(game_date=today)
    games_df = scoreboard.get_data_frames()[0]
except:
    st.error("Could not load today's games.")
    st.stop()

games = []

for _, row in games_df.iterrows():
    home_id = row["HOME_TEAM_ID"]
    away_id = row["VISITOR_TEAM_ID"]

    home_team = teams.find_team_name_by_id(home_id)["full_name"]
    away_team = teams.find_team_name_by_id(away_id)["full_name"]

    games.append(f"{away_team} @ {home_team}")

if len(games) == 0:
    st.warning("No games today.")
    st.stop()

selected_game = st.selectbox("Select Game", games)

away_team, home_team = selected_game.split(" @ ")

st.write(f"Selected: {away_team} @ {home_team}")

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

st.caption("Model simulation. Not financial advice.")