API_KEY = "PKMFWU2Q18X0517MG6OZ"
SECRET_KEY = "OXm0NF2p0llB1Rs7N4xgpheOSw4XwQRT34MJSDKz"


from datetime import datetime, timedelta
import pytz
from alpaca.data.requests import StockBarsRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.timeframe import TimeFrame


eastern = pytz.timezone("US/Eastern")
now = datetime.now(eastern)

data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)



tf = TimeFrame.Minute
extra_days_mapping = {
        TimeFrame.Minute: 7,   # 1D chart (Intraday) → Fetch past 7 days
        TimeFrame.Hour: 30,    # 1W chart (Hourly data) → Fetch past 30 days
        TimeFrame.Day: 365,    # 1M, 1Y, YTD → Fetch past 1 year
        TimeFrame.Month: 1800  # 5Y chart → Fetch past 5 years
    }

extra_days = extra_days_mapping.get(tf, 365)

    # Adjust start date to fetch more data
extended_start_date = now - timedelta(days=extra_days)

request_params = StockBarsRequest(
        symbol_or_symbols="SPY",
        timeframe=TimeFrame.Minute,
        start=extended_start_date,
        feed='iex'
    )


bars = data_client.get_stock_bars(request_params)

print(bars)

