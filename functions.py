import streamlit as st
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
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

# Function to calculate trailing stop loss based on entry price & highest price
def calculate_trailing_stop_loss(entry_price, latest_price, highest_price, trailing_stop_pct, last_stop_loss):
    new_stop_loss = highest_price * trailing_stop_pct  # Compute new stop loss

    # Ensure the stop loss only moves up
    if last_stop_loss is None or new_stop_loss > last_stop_loss:
        return new_stop_loss  # Update if higher
    else:
        return last_stop_loss  # Keep previous value

# Function to check if price is below stop loss and send close order
def check_and_close_position(trading_client, ticker, current_price, stop_loss_price, position_tickers, closed_positions):
    if ticker in position_tickers and current_price < stop_loss_price and ticker not in closed_positions:
        positions = trading_client.get_all_positions()
        position_qty = next((float(pos.qty) for pos in positions if pos.symbol == ticker), None)
        if position_qty is None:
            return False
        order = MarketOrderRequest(
            symbol=ticker,
            qty=position_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        trading_client.submit_order(order)
        closed_positions.add(ticker)
        return True
