import streamlit as st
import plotly.express as px
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import pytz
import pandas as pd
import time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import GetCalendarRequest
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Alpaca API Keys (Stored in Streamlit Secrets)
API_KEY = st.secrets["ALPACA_API_KEY"]
SECRET_KEY = st.secrets["ALPACA_SECRET_KEY"]

# Initialize Alpaca clients once
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Function to fetch Alpaca positions dynamically
@st.cache_data(ttl=300)
def fetch_alpaca_positions():
    positions = trading_client.get_all_positions()
    return {pos.symbol: float(pos.avg_entry_price) for pos in positions}

# Function to fetch stock data
@st.cache_data(ttl=60)
def fetch_stock_data(ticker, start_date, _timeframe):
    request_params = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=_timeframe,
        start=start_date
    )
    bars = data_client.get_stock_bars(request_params)
    
    # Convert to a Pandas DataFrame
    data = pd.DataFrame.from_records(
        [{
            'Date': bar.timestamp,
            'Open': bar.open,
            'High': bar.high,
            'Low': bar.low,
            'Close': bar.close,
            'Volume': bar.volume
        } for bar in bars[ticker]]
    )
    
    # Convert 'Date' column to EST
    data["Date"] = pd.to_datetime(data["Date"])
    if data["Date"].dt.tz is None:
        data["Date"] = data["Date"].dt.tz_localize("UTC")
    data["Date"] = data["Date"].dt.tz_convert("US/Eastern")
    return data

# Function to calculate trailing stop loss with persistence
def calculate_trailing_stop_loss(data, trailing_stop_pct, last_stop_loss):
    if "Close" not in data or data.empty:
        return last_stop_loss  # Prevent errors if data is empty

    highest_price = data["Close"].cummax()  # Track highest closing price
    new_stop_loss = highest_price * trailing_stop_pct  # Compute new stop loss

    # Ensure the stop loss only moves up
    if last_stop_loss is None or new_stop_loss.iloc[-1] > last_stop_loss:
        return new_stop_loss.iloc[-1]  # Update if higher
    else:
        return last_stop_loss  # Keep previous value

# Function to check if price is below stop loss and send close order
def check_and_close_position(trading_client, ticker, current_price, stop_loss_price, position_tickers, closed_positions):
    st.write(f"Checking position for {ticker} - Current Price: {current_price}, Stop Loss: {stop_loss_price}")
    if ticker in position_tickers and current_price < stop_loss_price and ticker not in closed_positions:
        positions = trading_client.get_all_positions()
        position_qty = next((float(pos.qty) for pos in positions if pos.symbol == ticker), None)
        if position_qty is None:
            st.write(f"No open position found for {ticker}")
            return False
        order = MarketOrderRequest(
            symbol=ticker,
            qty=position_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        st.write(f"Submitting sell order for {ticker}, Quantity: {position_qty}")
        trading_client.submit_order(order)
        closed_positions.add(ticker)
        return True



# Sidebar: Fetch positions and allow manual search
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

# Add a slider in the sidebar for trailing stop loss percentage
trailing_stop_pct = st.sidebar.slider(
    "Trailing Stop Loss Percentage",
    min_value=0.01, max_value=0.99, value=0.95, step=0.01,
    help="Select the percentage for the trailing stop loss."
)

# Timeframe selection
timeframe_mapping = {
    "1D": TimeFrame.Minute,
    "1W": TimeFrame.Hour,
    "1M": TimeFrame.Day,
    "1Y": TimeFrame.Day,
    "YTD": TimeFrame.Day,
    "5Y": TimeFrame.Month
}
selected_period = st.sidebar.radio("Select Time Period", list(timeframe_mapping.keys()), index=0)

# Determine start date based on selection
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

query_params = st.experimental_get_query_params()
saved_stop_loss = query_params.get("stop_loss", [None])[0]

if "last_stop_loss" not in st.session_state:
    st.session_state.last_stop_loss = float(saved_stop_loss) if saved_stop_loss else 0.0  # Use stored value


avg_entry_price = position_tickers.get(ticker, None)
if avg_entry_price:
    new_stop_loss = calculate_trailing_stop_loss(data, trailing_stop_pct, st.session_state.last_stop_loss)

    # Only update if the new stop loss is greater
    if st.session_state.last_stop_loss == 0.0 or new_stop_loss > st.session_state.last_stop_loss:
        st.session_state.last_stop_loss = new_stop_loss

        # Store the new stop loss in the URL query parameters
        st.experimental_set_query_params(stop_loss=new_stop_loss)


    closed_positions = getattr(st.session_state, 'closed_positions', set())
    if check_and_close_position(trading_client, ticker, data["Close"].iloc[-1], st.session_state.last_stop_loss, position_tickers, closed_positions):
        show_trailing_stop = False
    st.session_state.closed_positions = closed_positions

# Plot Chart
fig = px.line(data, x="Date", y="Close", title=f"{ticker}")

# If trailing stop loss is enabled, add it as a horizontal line at the last stop price
if show_trailing_stop and st.session_state.last_stop_loss is not None:
    fig.add_hline(y=st.session_state.last_stop_loss, line_dash="dash", line_color="red",
                  annotation_text=f"Stop Loss: {st.session_state.last_stop_loss:.2f}",
                  annotation_position="bottom right")

# Format x-axis labels
fig.update_xaxes(showticklabels=False, title=None)

# Display the chart
st.plotly_chart(fig, use_container_width=True)

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh_data")
