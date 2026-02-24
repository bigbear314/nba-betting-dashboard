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

def american_to_profit(odds):
    if odds > 0:
        return odds / 100
    return 100 / abs(odds)

def calculate_ev(prob, odds):
    profit = american_to_profit(odds)
    return (prob * profit) - (1 - prob)

def get_team_sd(mean):
    base_sd = 11
    return base_sd * (mean / 110)

# ---------------------------------------------------
# Load JSON Data
# ---------------------------------------------------

try:
    with open("team_ratings.json") as f:
        team_ratings = json.load(f)
except:
    st.error("Error loading team_ratings.json")
    st.stop()

try:
    with open("player_ratings.json") as f:
        player_ratings = json.load(f)
except:
    st.error("Error loading player_ratings.json")
    st.stop()

default_team = {"off": 114, "def": 114, "pace": 100, "volatility": 1.0}

# ---------------------------------------------------
# Get Today's Games
# ---------------------------------------------------

today = datetime.today().strftime('%Y-%m-%d')
scoreboard = scoreboardv3.ScoreboardV3(game_date=today).get_dict()

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
# Team Projections
# ---------------------------------------------------

away_data = team_ratings.get(away_team, default_team)
home_data = team_ratings.get(home_team, default_team)

avg_pace = (away_data["pace"] + home_data["pace"]) / 2

away_proj = (away_data["off"]/114)*(home_data["def"]/114)*112
home_proj = (home_data["off"]/114)*(away_data["def"]/114)*112

away_proj *= avg_pace/100
home_proj *= avg_pace/100

home_proj *= 1.025
away_proj *= 0.975

# ---------------------------------------------------
# Monte Carlo Simulation (Correlated)
# ---------------------------------------------------

n_sims = st.slider("Simulation Runs", 5000, 50000, 15000, step=5000)

home_sd = get_team_sd(home_proj)
away_sd = get_team_sd(away_proj)

correlation = 0.30

cov_matrix = [
    [home_sd**2, correlation * home_sd * away_sd],
    [correlation * home_sd * away_sd, away_sd**2]
]

means = [home_proj, away_proj]

samples = np.random.multivariate_normal(means, cov_matrix, n_sims)

home_scores = samples[:,0]
away_scores = samples[:,1]

margins = home_scores - away_scores
totals = home_scores + away_scores

# ---------------------------------------------------
# Market Selection
# ---------------------------------------------------

st.subheader("Game Market Simulator")

market_type = st.selectbox("Market Type", ["Moneyline", "Spread", "Total"])
odds_input = st.number_input("American Odds", value=-110)

if market_type == "Moneyline":

    home_prob = np.mean(margins > 0)
    away_prob = 1 - home_prob

    st.write(f"Home Win Probability: {home_prob*100:.2f}%")
    ev = calculate_ev(home_prob, odds_input)

elif market_type == "Spread":

    spread_line = st.number_input("Spread Line (Home perspective)", value=-5.5)
    home_cover = np.mean(margins > spread_line)

    st.write(f"Home Cover Probability: {home_cover*100:.2f}%")
    ev = calculate_ev(home_cover, odds_input)

elif market_type == "Total":

    total_line = st.number_input("Total Line", value=round(np.mean(totals),1))
    over_prob = np.mean(totals > total_line)

    st.write(f"Over Probability: {over_prob*100:.2f}%")
    ev = calculate_ev(over_prob, odds_input)

st.write(f"### EV: {ev:.3f} units")

st.divider()

# ---------------------------------------------------
# Player Prop Monte Carlo
# ---------------------------------------------------

st.subheader("Player Prop Monte Carlo")

stat_choice = st.selectbox("Stat", ["pts", "reb", "ast", "PRA"])
prop_line = st.number_input("Sportsbook Line", value=20.5)
prop_odds = st.number_input("American Odds (Prop)", value=-110)

injury_impact = st.slider("Injury Impact (%)", 0, 20, 0)
b2b = st.checkbox("Back-to-Back Game?")

players_today = [
    p for p, data in player_ratings.items()
    if data["team"] in [home_team, away_team]
]

if not players_today:
    st.error("No players found for selected teams.")
    st.stop()

results = []

for player_name in players_today:
    player = player_ratings[player_name]
    team = player["team"]
    team_data = team_ratings.get(team, default_team)

    base = player.get(stat_choice, 0)
    usage_boost = base * player.get("usage", 0)

    proj = base + usage_boost
    proj *= team_data["off"]/114
    proj *= team_data["pace"]/100

    if b2b:
        proj *= 0.97

    proj *= 1 - injury_impact/100

    sd = 3 * team_data.get("volatility",1)

    sims = np.random.normal(proj, sd, n_sims)

    prob_over = np.mean(sims >= prop_line)
    prob_under = 1 - prob_over

    ev_over = calculate_ev(prob_over, prop_odds)
    ev_under = calculate_ev(prob_under, prop_odds)

    results.append({
        "Player": player_name,
        "Team": team,
        "Projection": round(proj,2),
        "Over %": round(prob_over*100,2),
        "Under %": round(prob_under*100,2),
        "EV Over": round(ev_over,3),
        "EV Under": round(ev_under,3)
    })

df = pd.DataFrame(results).sort_values(by="EV Over", ascending=False)

st.dataframe(df, use_container_width=True)
st.caption("Model includes pace, usage, volatility, injury adjustments, and correlated scoring.")