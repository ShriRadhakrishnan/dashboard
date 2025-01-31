import streamlit as st
import plotly.express as px
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import pytz
from alpaca.data.timeframe import TimeFrame
from functions import *

st.set_page_config(layout="wide")

#Retrieve Positions

position_tickers = fetch_alpaca_positions()

monitor_and_close_positions()

#Set up Sidebar (Positions, Indicators, Orders)

position_dropdown = st.sidebar.selectbox(
    "Select a Position",
    options=list(position_tickers.keys()) if position_tickers else ["No Open Positions"],
    index=0 if position_tickers else None
)

visible_charts = st.sidebar.multiselect(
    "Select Charts to Display",
    options=["Volatility", "EMA", "SMA"],
    default=[]  
)

if position_dropdown and position_dropdown != "No Open Positions":
    ticker = position_dropdown  
    show_trailing_stop = True  


with st.sidebar.expander("➕ Place Order", expanded=False) as order_expander:

    order_form_key = f"order_form_{ticker}"

    order_ticker = st.text_input("Stock Ticker", value=ticker, key=f"{order_form_key}_ticker")

    order_type = st.selectbox("Order Type", ["Market", "Limit", "Stop"], key=f"{order_form_key}_type")

    order_side = st.radio("Side", ["Buy", "Sell"], horizontal=True, key=f"{order_form_key}_side")

    quantity_type = st.radio("Quantity Type", ["Shares", "Dollars"], horizontal=True, key=f"{order_form_key}_qty_type")
    
    if quantity_type == "Shares":
        order_quantity = st.number_input("Quantity (Shares)", min_value=1, value=1, step=1, key=f"{order_form_key}_qty")
    else:
        order_quantity = st.number_input("Amount ($)", min_value=1, value=100, step=10, key=f"{order_form_key}_amount")

    order_price = None
    if order_type in ["Limit", "Stop"]:
        order_price = st.number_input("Limit/Stop Price ($)", min_value=0.01, step=0.01, format="%.2f", key=f"{order_form_key}_price")

    if st.button("Submit Order", key=f"{order_form_key}_submit"):
        success, message = place_order(
            ticker=order_ticker,
            order_type=order_type,
            order_side=order_side,
            quantity=order_quantity,
            quantity_type=quantity_type,
            limit_price=order_price
        )

        if success:
            st.toast(f"✅ Order placed: {order_side} {order_quantity} {order_ticker} as {order_type}", icon="✅")

            for key in [f"{order_form_key}_ticker", f"{order_form_key}_type", f"{order_form_key}_side", 
                        f"{order_form_key}_qty_type", f"{order_form_key}_qty", f"{order_form_key}_amount", 
                        f"{order_form_key}_price"]:
                if key in st.session_state:
                    del st.session_state[key]

            st.rerun()

        else:
            st.error(f"❌ Order failed: {message}")


#Chart Data Setup

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


data = fetch_stock_data(ticker, start_date, timeframe_mapping[selected_period])
data = calculate_rolling_volatility(data, window=20)
data = calculate_moving_averages(data, ema_window=20, sma_window=50)


#Stop Loss Setup

stop_losses = load_stop_losses()

current_stop_loss_pct = get_stop_loss_pct(ticker) 

new_stop_loss_pct = st.sidebar.slider(
    "Trailing Stop Loss Percentage",
    min_value=0.90, max_value=0.99, value=current_stop_loss_pct, step=0.01,
    help="Select the percentage for the trailing stop loss."
)

if new_stop_loss_pct > current_stop_loss_pct:
    update_stop_loss_pct(ticker, new_stop_loss_pct)  # ✅ Save to JSON
    current_stop_loss_pct = new_stop_loss_pct  # ✅ Update local variable to reflect new change

last_stop_loss = get_stop_loss(ticker)

#Stop Loss Computation

avg_entry_price = position_tickers.get(ticker, None)
if avg_entry_price and not data.empty:
    latest_price = data["Close"].iloc[-1]  
    
    new_stop_loss = calculate_trailing_stop_loss(
        latest_price=latest_price,
        trailing_stop_pct=current_stop_loss_pct, 
        last_stop_loss=last_stop_loss
    )

    if new_stop_loss > last_stop_loss:
        update_stop_loss(ticker, new_stop_loss)  

    


if selected_period == "1D":
    data["Time Stamp"] = data["Date"].dt.strftime("%I:%M %p")
elif selected_period == "1W":
    data["Time Stamp"] = data["Date"].dt.strftime("%b - %d, %I:%M %p")
else:
    data["Time Stamp"] = data["Date"].dt.strftime("%Y-%m-%d")

#Chart Display


fig = px.line(
    data,
    x=data.index, 
    y="Close", 
    title=f"{ticker}",
    hover_data={"Time Stamp": True}
)

if "EMA" in visible_charts and "EMA" in data.columns:
    fig.add_scatter(
        x=data.index,
        y=data["EMA"],
        mode="lines",
        name="EMA",
        line=dict(color="blue")
    )

if "SMA" in visible_charts and "SMA" in data.columns:
    fig.add_scatter(
        x=data.index,
        y=data["SMA"],
        mode="lines",
        name="SMA",
        line=dict(color="orange")
    )


#Chart Formatting

if selected_period == "1D":
    unique_hours = data[data["Date"].dt.strftime("%M") == "30"]["Date"].dt.strftime("%I:%M %p").unique()  
    unique_hour_indices = [data["Date"].dt.strftime("%I:%M %p").tolist().index(h) for h in unique_hours]

    fig.update_xaxes(
        tickvals=data.index[unique_hour_indices],  
        ticktext=unique_hours
    )

elif selected_period == "1W":
    unique_dates = data["Date"].dt.strftime("%b - %d").unique()
    unique_date_indices = [data["Date"].dt.strftime("%b - %d").tolist().index(d) for d in unique_dates]

    fig.update_xaxes(
        tickvals=data.index[unique_date_indices],  
        ticktext=unique_dates  
    )

fig.update_layout(height=700, width=2000)

if show_trailing_stop and get_stop_loss(ticker) is not None:
    fig.add_hline(y=get_stop_loss(ticker), line_dash="dash", line_color="red",
                  annotation_text=f"Stop Loss: {get_stop_loss(ticker):.2f}",
                  annotation_position="bottom right")

st.plotly_chart(fig, use_container_width=False)



if "Volatility" in visible_charts:
    fig_volatility = px.line(
        data,
        x=data.index,
        y="Volatility",
        title=f"{ticker} - Rolling Volatility",
        labels={"Volatility": "Rolling Volatility"}
    )

    fig_volatility.update_layout(height=400, width=2000)
    st.plotly_chart(fig_volatility, use_container_width=False)


#Refresh every second
st_autorefresh(interval=10000, key="refresh_data")
