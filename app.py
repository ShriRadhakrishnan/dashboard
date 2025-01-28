from flask import Flask, render_template, request, jsonify
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.common.exceptions import APIError
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import plotly.graph_objects as go


app = Flask(__name__)

# Alpaca API Keys
API_KEY = "PKK06B7318DK7TBA67MM"
SECRET_KEY = "uXQj0WhXnweBwE7iXQYhB0WlDmpteDDM3WpfPVbT"

# Fetch open positions from Alpaca
def get_open_positions(api_key, secret_key):
    trading_client = TradingClient(api_key, secret_key, paper=True)
    positions = trading_client.get_all_positions()
    return [
        {
            "symbol": position.symbol,
            "qty": float(position.qty),
            "current_price": float(position.current_price),
            "market_value": float(position.market_value),
        }
        for position in positions
    ]



from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed  # Import DataFeed for IEX/SIP specification
from datetime import datetime, timedelta

def fetch_stock_data(api_key, secret_key, symbol, days=30):
    # Initialize the historical data client
    data_client = StockHistoricalDataClient(api_key, secret_key)

    # Define the time range for historical data
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Request daily historical bars (using IEX feed explicitly)
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
    )

    try:
        # Fetch stock bars
        bars = dict(data_client.get_stock_bars(request_params))
        #print(len(bars))


        data = []
        for i in range(len(bars['data'][symbol])):
            new_dict = {'date': dict(bars['data'][symbol][i])['timestamp'].date(), 'price': dict(bars['data'][symbol][i])['close']}
            data.append(new_dict)

        return data

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None



@app.route("/")
def index():
    positions = get_open_positions(API_KEY, SECRET_KEY)
    if not positions:
        return render_template("index.html", message="No open positions in your Alpaca account.")
    
    # Use the first open position's ticker
    first_position_symbol = positions[0]["symbol"]
    return render_template("index.html", symbol=first_position_symbol)




@app.route("/get_stock_data", methods=["POST"])
def get_stock_data():
    symbol = request.json.get("symbol")
    historical_data = fetch_stock_data(API_KEY, SECRET_KEY, symbol)

    if not historical_data:
        return jsonify({"error": f"No data available for {symbol}."}), 404

    # Return raw data instead of HTML
    return jsonify({
        "dates": [record["date"].strftime('%Y-%m-%d') for record in historical_data],
        "prices": [record["price"] for record in historical_data],
        "symbol": symbol
    })








if __name__ == "__main__":
    app.run(debug=True)
