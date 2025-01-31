import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

API_KEY = st.secrets["ALPACA_API_KEY"]
SECRET_KEY = st.secrets["ALPACA_SECRET_KEY"]
STOP_LOSS_FILE = "stop_losses.json"

#Json Functions

def load_stop_losses():
    try:
        with open(STOP_LOSS_FILE, "r") as file:
            content = file.read().strip()
            return json.loads(content) if content else {}  
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  

def save_stop_losses(stop_losses):
    with open(STOP_LOSS_FILE, "w") as file:
        json.dump(stop_losses, file, indent=4)

def get_stop_loss(ticker):
    stop_losses = load_stop_losses()
    return stop_losses.get(ticker, {}).get("stop_loss", 0.0)

def get_stop_loss_pct(ticker):
    stop_losses = load_stop_losses()
    return stop_losses.get(ticker, {}).get("stop_loss_pct", 0.90)

def update_stop_loss(ticker, stop_loss_price):
    stop_losses = load_stop_losses()
    if ticker not in stop_losses:
        stop_losses[ticker] = {}

    stop_losses[ticker]["stop_loss"] = stop_loss_price
    save_stop_losses(stop_losses)

def update_stop_loss_pct(ticker, stop_loss_pct):
    stop_losses = load_stop_losses()
    if ticker not in stop_losses:
        stop_losses[ticker] = {}

    stop_losses[ticker]["stop_loss_pct"] = stop_loss_pct
    save_stop_losses(stop_losses)


#Alpaca Functions

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)


@st.cache_data(ttl=300)
def fetch_alpaca_positions():
    positions = trading_client.get_all_positions()
    return {pos.symbol: float(pos.avg_entry_price) for pos in positions}

@st.cache_data(ttl=60)
def fetch_stock_data(ticker, start_date, _timeframe):
    request_params = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=_timeframe,
        start=start_date
    )

    bars = data_client.get_stock_bars(request_params)

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

    data["Date"] = pd.to_datetime(data["Date"])
    if data["Date"].dt.tz is None:
        data["Date"] = data["Date"].dt.tz_localize("UTC")
    data["Date"] = data["Date"].dt.tz_convert("US/Eastern")

    return data

def calculate_trailing_stop_loss(latest_price, trailing_stop_pct, last_stop_loss):
    new_stop_loss = latest_price * trailing_stop_pct  # ✅ Compute new stop loss

    if last_stop_loss is None or new_stop_loss > last_stop_loss:
        return new_stop_loss 
    else:
        return last_stop_loss



def monitor_and_close_positions():

    positions = fetch_alpaca_positions()  
    stop_losses = load_stop_losses() 

    closed_positions = set()

    for ticker, entry_price in positions.items():

        stop_loss_price = stop_losses.get(ticker, {}).get("stop_loss", None)

        if stop_loss_price is None:
            continue

        stock_data = fetch_stock_data(ticker, datetime.now() - timedelta(days=1), TimeFrame.Minute)
        if stock_data.empty:
            continue  

        latest_price = stock_data["Close"].iloc[-1]

        if latest_price < stop_loss_price and ticker not in closed_positions:
            close_position(ticker)
            closed_positions.add(ticker) 

    return closed_positions


def close_position(ticker):
    try:
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
        return True
    except Exception as e:
        return False





def place_order(ticker, order_type, order_side, quantity, quantity_type, limit_price=None):

    try:

        side = OrderSide.BUY if order_side == "Buy" else OrderSide.SELL
        tif = TimeInForce.GTC

        if quantity_type == "Dollars":
            qty_field = {"notional": quantity}
        else:
            qty_field = {"qty": int(quantity)}

        if order_type == "Market":
            order = MarketOrderRequest(symbol=ticker, side=side, time_in_force=tif, **qty_field)

        elif order_type == "Limit":
            if not limit_price:
                return False, "Limit price is required for a Limit Order."
            order = LimitOrderRequest(symbol=ticker, side=side, time_in_force=tif, limit_price=limit_price, **qty_field)

        elif order_type == "Stop":
            if not limit_price:
                return False, "Stop price is required for a Stop Order."
            order = StopOrderRequest(symbol=ticker, side=side, time_in_force=tif, stop_price=limit_price, **qty_field)

        trading_client.submit_order(order)
        return True, f"Order placed: {order_side} {quantity} {ticker} as {order_type}."

    except Exception as e:
        return False, f"Error placing order: {str(e)}"

#Indicators

def calculate_rolling_volatility(data, window=20):
    if "Close" not in data or data.empty:
        return data
    data["Returns"] = data["Close"].pct_change()
    data["Volatility"] = data["Returns"].rolling(window=window, min_periods=1).std()
    
    return data

def calculate_moving_averages(data, ema_window=20, sma_window=50):
    
    if "Close" not in data or data.empty:
        return data
    
    data["EMA"] = data["Close"].ewm(span=ema_window, adjust=False).mean()
    data["SMA"] = data["Close"].rolling(window=sma_window, min_periods=1).mean()

    return data