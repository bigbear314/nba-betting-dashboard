import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

st.set_page_config(page_title="NBA Prop Edge Engine", layout="centered")

st.title("🏀 NBA Betting Edge Engine v2")
st.write("Evaluate player props, team totals, or full game totals.")

st.divider()

# ------------------------
# INPUT SECTION
# ------------------------

st.subheader("Bet Details")

bet_type = st.selectbox(
    "Select Bet Type",
    ["Player Prop", "Team Total", "Full Game Total"]
)

name_input = st.text_input("Enter Player or Team Name")

stat_type = st.selectbox(
    "Stat Category",
    ["Points", "Rebounds", "Assists", "PRA", "3PT Made", "Team Total Points", "Game Total Points"]
)

line = st.number_input("Sportsbook Line", value=221.5)
odds = st.number_input("American Odds (ex: -110)", value=-110)

st.divider()

st.subheader("Model Projection Inputs")

model_mean = st.number_input("Your Projected Mean Outcome", value=222.0)
std_dev = st.number_input("Expected Standard Deviation", value=12.0)

st.divider()

# ------------------------
# CALCULATIONS
# ------------------------

prob_over = 1 - norm.cdf(line, model_mean, std_dev)
prob_under = norm.cdf(line, model_mean, std_dev)

if odds < 0:
    decimal_odds = 1 + (100 / abs(odds))
else:
    decimal_odds = 1 + (odds / 100)

implied_prob = 1 / decimal_odds

edge_over = prob_over - implied_prob
edge_under = prob_under - implied_prob

ev_over = (prob_over * (decimal_odds - 1)) - (1 - prob_over)
ev_under = (prob_under * (decimal_odds - 1)) - (1 - prob_under)

# ------------------------
# OUTPUT
# ------------------------

st.subheader("📊 Probability Results")

col1, col2 = st.columns(2)

with col1:
    st.metric("Over Probability", f"{prob_over*100:.2f}%")
    st.metric("Over Edge", f"{edge_over*100:.2f}%")
    st.metric("Over EV (Units)", f"{ev_over:.3f}")

with col2:
    st.metric("Under Probability", f"{prob_under*100:.2f}%")
    st.metric("Under Edge", f"{edge_under*100:.2f}%")
    st.metric("Under EV (Units)", f"{ev_under:.3f}")

st.divider()

# ------------------------
# DISTRIBUTION CHART
# ------------------------

st.subheader("Distribution Projection")

x = np.linspace(model_mean - 4*std_dev, model_mean + 4*std_dev, 1000)
y = norm.pdf(x, model_mean, std_dev)

fig, ax = plt.subplots()
ax.plot(x, y)
ax.axvline(line, linestyle='--')
ax.set_title(f"{name_input} - {stat_type} Projection")
ax.set_xlabel("Outcome")
ax.set_ylabel("Probability Density")

st.pyplot(fig)

st.divider()

st.caption("Model-based probability simulator. Not financial advice.")