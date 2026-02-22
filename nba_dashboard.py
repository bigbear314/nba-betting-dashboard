import streamlit as st
import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")

# ----------------------------
# TITLE
# ----------------------------
st.title("🏀 NBA Betting Edge Engine")

# ----------------------------
# SIDEBAR INPUTS
# ----------------------------
st.sidebar.header("Player Profile")

player_name = st.sidebar.text_input("Player Name", "James Harden")
base_points = st.sidebar.number_input("Base Points Avg", 10.0, 40.0, 25.0)
std_dev = st.sidebar.number_input("Volatility (Std Dev)", 2.0, 15.0, 6.0)

st.sidebar.header("Game Context")

opp_def_rating = st.sidebar.number_input("Opponent Defensive Rating", 100.0, 125.0, 118.0)
drop_pct = st.sidebar.slider("Drop Coverage %", 0.0, 1.0, 0.55)
switch_pct = st.sidebar.slider("Switch Coverage %", 0.0, 1.0, 0.30)
back_to_back = st.sidebar.checkbox("Back-to-Back Game")

st.sidebar.header("Bet Info")

line = st.sidebar.number_input("Sportsbook Line", 5.0, 50.0, 24.5)
odds = st.sidebar.number_input("American Odds", -200, 300, -110)

# ----------------------------
# PROJECTION ENGINE
# ----------------------------
projection = base_points

coverage_boost = (drop_pct * 0.04) + (switch_pct * -0.05)
projection *= (1 + coverage_boost)

league_avg_def = 113
def_adjustment = (opp_def_rating - league_avg_def) * 0.002
projection *= (1 + def_adjustment)

if back_to_back:
    projection *= 0.96

projection = round(projection, 2)

# ----------------------------
# MONTE CARLO SIMULATION
# ----------------------------
simulations = np.random.normal(projection, std_dev, 10000)
prob_over = np.mean(simulations > line)

# Convert odds
if odds > 0:
    decimal_odds = 1 + odds / 100
else:
    decimal_odds = 1 + 100 / abs(odds)

expected_value = (prob_over * decimal_odds) - 1

# ----------------------------
# DISPLAY RESULTS
# ----------------------------
col1, col2, col3 = st.columns(3)

col1.metric("Projected Points", projection)
col2.metric("Probability Over", f"{prob_over:.2%}")
col3.metric("Expected Value", f"{expected_value:.3f}")

# ----------------------------
# DISTRIBUTION PLOT
# ----------------------------
fig, ax = plt.subplots()
ax.hist(simulations, bins=50)
ax.axvline(line)
ax.set_title(f"{player_name} Points Distribution")
st.pyplot(fig)

# ----------------------------
# EDGE INTERPRETATION
# ----------------------------
st.subheader("Model Interpretation")

if expected_value > 0:
    st.success("Positive Expected Value Bet")
else:
    st.warning("No Positive Edge Detected")