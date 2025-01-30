import streamlit as st
import plotly.express as px
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import pytz
from alpaca.data.timeframe import TimeFrame
from functions import *


st.set_page_config(layout="wide")  


position_tickers = fetch_alpaca_positions()

ticker = st.sidebar.selectbox(
    "Select a Stock",
    options=list(position_tickers.keys()) + (["SPY"] if not position_tickers else ["Search for another ticker..."]),
    index=0 if position_tickers else None
)

if not position_tickers:
    ticker = "SPY"
    show_trailing_stop = False
else:
    show_trailing_stop = ticker in position_tickers
if ticker == "Search for another ticker...":
    ticker = st.sidebar.text_input("Enter Stock Ticker", value="SPY")

query_params = st.query_params
saved_stop_loss = query_params.get("stop_loss", None)


if saved_stop_loss is not None:
    try:
        saved_stop_loss = float(saved_stop_loss)  
    except ValueError:
        saved_stop_loss = None

if "last_stop_loss" not in st.session_state:
    st.session_state.last_stop_loss = saved_stop_loss if saved_stop_loss is not None else 0.0

if "highest_price" not in st.session_state:
    st.session_state.highest_price = 0.0  

trailing_stop_pct = st.sidebar.slider(
    "Trailing Stop Loss Percentage",
    min_value=0.90, max_value=0.99, value=0.95, step=0.01,
    help="Select the percentage for the trailing stop loss."
)

timeframe_mapping = {
    "1D": TimeFrame.Minute,
    "1W": TimeFrame.Hour,
    "1M": TimeFrame.Day,
    "1Y": TimeFrame.Day,
    "YTD": TimeFrame.Day,
    "5Y": TimeFrame.Month
}
selected_period = st.sidebar.radio("Select Time Period", list(timeframe_mapping.keys()), index=0)

eastern = pytz.timezone("US/Eastern")
now = datetime.now(eastern)

if selected_period == "1D":
    start_date = now.replace(hour=9, minute=30, second=0, microsecond=0)
elif selected_period == "5Y":
    start_date = now - timedelta(days=5 * 365)
elif selected_period == "YTD":
    start_date = datetime(now.year, 1, 1)
else:
    start_date = now - timedelta(days={"1D": 1, "1W": 7, "1M": 30, "1Y": 365}[selected_period])

# Fetch stock data
data = fetch_stock_data(ticker, start_date, timeframe_mapping[selected_period])

# Initialize or update stop loss
avg_entry_price = position_tickers.get(ticker, None)
if avg_entry_price and not data.empty:
    latest_price = data["Close"].iloc[-1]  # Get the most recent price
    st.session_state.highest_price = max(st.session_state.highest_price, latest_price)  # Track highest price

    new_stop_loss = calculate_trailing_stop_loss(
        entry_price=avg_entry_price,
        latest_price=latest_price,
        highest_price=st.session_state.highest_price,
        trailing_stop_pct=trailing_stop_pct,
        last_stop_loss=st.session_state.last_stop_loss
    )

    if new_stop_loss > st.session_state.last_stop_loss:
        st.session_state.last_stop_loss = new_stop_loss
        st.query_params["stop_loss"] = new_stop_loss  # Persist in query params

    closed_positions = getattr(st.session_state, 'closed_positions', set())
    if check_and_close_position(trading_client, ticker, latest_price, st.session_state.last_stop_loss, position_tickers, closed_positions):
        show_trailing_stop = False
    st.session_state.closed_positions = closed_positions


# Create a new column for formatted hover text
if selected_period == "1D":
    data["Time Stamp"] = data["Date"].dt.strftime("%I:%M %p")  # Show exact time (e.g., 09:30 AM)
elif selected_period == "1W":
    data["Time Stamp"] = data["Date"].dt.strftime("%b - %d, %I:%M %p")  # Show date + hour (e.g., Jan - 05, 10:00 AM)
else:
    data["Time Stamp"] = data["Date"].dt.strftime("%Y-%m-%d")  # Show exact date (e.g., 2024-01-15)

# Create the plot with custom hover text
fig = px.line(
    data,
    x=data.index, 
    y="Close", 
    title=f"{ticker}",
    hover_data={"Time Stamp": True}  # Use new column instead of "Date"
)


# Hide default x-axis labels
fig.update_xaxes(showticklabels=True, title=None)

# If using 1D, only show unique timestamps at 9:30, 10:30, etc.
if selected_period == "1D":
    unique_hours = data[data["Date"].dt.strftime("%M") == "30"]["Date"].dt.strftime("%I:%M %p").unique()  
    unique_hour_indices = [data["Date"].dt.strftime("%I:%M %p").tolist().index(h) for h in unique_hours]

    fig.update_xaxes(
        tickvals=data.index[unique_hour_indices],  
        ticktext=unique_hours,
        tickangle=0  
    )

# If using 1W, only show unique date labels in "Jan - DD" format
elif selected_period == "1W":
    unique_dates = data["Date"].dt.strftime("%b - %d").unique()
    unique_date_indices = [data["Date"].dt.strftime("%b - %d").tolist().index(d) for d in unique_dates]

    fig.update_xaxes(
        tickvals=data.index[unique_date_indices],  
        ticktext=unique_dates  
    )

fig.update_layout(
    height=700, 
    width=2000,  
)

if show_trailing_stop and st.session_state.last_stop_loss is not None:
    fig.add_hline(y=st.session_state.last_stop_loss, line_dash="dash", line_color="red",
                  annotation_text=f"Stop Loss: {st.session_state.last_stop_loss:.2f}",
                  annotation_position="bottom right")

st.plotly_chart(fig, use_container_width=False)

st_autorefresh(interval=1000, key="refresh_data")
