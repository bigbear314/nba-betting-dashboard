import streamlit as st
import json
import numpy as np
import pandas as pd
from nba_api.stats.endpoints import scoreboardv3
from datetime import datetime
from scipy.stats import norm

st.set_page_config(page_title="NBA Dashboard with Monte Carlo Props", layout="centered")
st.title("🏀 NBA Dashboard + Monte Carlo Player Prop Simulator")

# -----------------------------
# Load JSON ratings
# -----------------------------
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

# -----------------------------
# Detect today's slate
# -----------------------------
today = datetime.today().strftime('%Y-%m-%d')
try:
    scoreboard = scoreboardv3.ScoreboardV3(game_date=today).get_dict()
except Exception as e:
    st.error(f"Could not load today's games: {e}")
    st.stop()

games = []
for game in scoreboard.get("scoreboard", {}).get("games", []):
    home_team = game["homeTeam"]["teamName"]
    away_team = game["awayTeam"]["teamName"]
    games.append(f"{away_team} @ {home_team}")

if not games:
    st.warning("No games today")
    st.stop()

selected_game = st.selectbox("Select Game", games)
away_team, home_team = selected_game.split(" @ ")
st.write(f"Selected matchup: **{away_team} @ {home_team}**")

# -----------------------------
# Team total projection + EV
# -----------------------------
away_data = team_ratings.get(away_team, default_team)
home_data = team_ratings.get(home_team, default_team)

avg_pace = (away_data["pace"] + home_data["pace"]) / 2
away_proj = (away_data["off"] / 114) * (home_data["def"] / 114) * 112
home_proj = (home_data["off"] / 114) * (away_data["def"] / 114) * 112
away_proj *= avg_pace / 100
home_proj *= avg_pace / 100
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
# Player prop Monte Carlo for all starters
# -----------------------------
st.subheader("Player Prop Batch Monte Carlo")
stat_choice = st.selectbox("Select Stat", ["pts", "reb", "ast", "PRA"])
line_adjust = st.number_input("Optional Line Adjustment", value=0.0)
injury_impact = st.slider("Star or Teammate Injury Impact (%)", 0, 20, 0)
b2b = st.checkbox("Back-to-Back Game?")
n_sim = st.number_input("Number of Simulations per Player", min_value=1000, max_value=100000, value=10000, step=1000)

# Filter players for selected game
players_today = [p for p, data in player_ratings.items() if data["team"] in [home_team, away_team]]
results = []

for player_name in players_today:
    player = player_ratings[player_name]
    team = player["team"]
    team_data = team_ratings.get(team, default_team)

    # Base projection
    proj = player[stat_choice] * (1 + player["usage"])
    proj *= team_data["off"] / 114
    proj *= team_data["pace"] / 100
    proj *= 1.02
    if b2b:
        proj *= 0.97
    proj *= 1 - injury_impact / 100
    proj += line_adjust

    std_dev = 3 * team_data["volatility"]

    # Monte Carlo
    sim_results = np.random.normal(proj, std_dev, n_sim)
    prob_over = np.mean(sim_results >= proj)
    prob_under = np.mean(sim_results < proj)

    decimal_odds = 1 + 100 / 110
    implied_prob = 1 / decimal_odds

    edge_over = prob_over - implied_prob
    edge_under = prob_under - implied_prob
    ev_over = (prob_over * (decimal_odds - 1)) - (1 - prob_over)
    ev_under = (prob_under * (decimal_odds - 1)) - (1 - prob_under)

    results.append({
        "Player": player_name,
        "Team": team,
        "Stat": stat_choice.upper(),
        "Projection": round(proj, 2),
        "Over Prob %": round(prob_over*100, 2),
        "Under Prob %": round(prob_under*100, 2),
        "Edge Over %": round(edge_over*100, 2),
        "Edge Under %": round(edge_under*100, 2),
        "EV Over": round(ev_over, 3),
        "EV Under": round(ev_under, 3)
    })

# Show results as sortable table
df = pd.DataFrame(results).sort_values(by="EV Over", ascending=False)
st.dataframe(df, use_container_width=True)
st.caption("Monte Carlo simulations include usage, pace, home/away, B2B, and injury adjustments.")