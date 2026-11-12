
import os
import time
import requests
import pandas as pd
from datetime import datetime

# --------------------------------------------------------------
# 1️⃣  Load the API key (environment variable or .env file)
# --------------------------------------------------------------
# If you use python‑dotenv, create a .env file in the same folder:
#   ALPHAVANTAGE_KEY=your_key_here
# Then uncomment the next two lines:
# from dotenv import load_dotenv
# load_dotenv()

API_KEY = os.getenv("ALPHAVANTAGE_KEY")
if not API_KEY:
    raise ValueError("Alpha Vantage API key not found. Set ALPHAVANTAGE_KEY env var or put it in a .env file.")

# --------------------------------------------------------------
# 2️⃣  Core helper – fetch one symbol
# --------------------------------------------------------------
def get_alpha_vantage(symbol: str, interval: str = "5min", outputsize: str = "full") -> pd.DataFrame:
    """
    Pulls historic OHLCV data from Alpha Vantage.

    Parameters
    ----------
    symbol : str
        Alpha Vantage symbol, e.g. "EURUSD", "GBPUSD", "DXY".
    interval : str, optional
        Trading interval. Common values: "1min", "5min", "15min", "60min", "daily".
        Default = "5min" (the same interval the original model expects).
    outputsize : str, optional
        "full" (all available history) or "compact" (last ~100 days). Default = "full".

    Returns
    -------
    pandas.DataFrame
        Index = datetime (UTC). Columns: open, high, low, close, volume.
    """
    base_url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "apikey": API_KEY,
        "outputsize": outputsize,
    }

    # Respect the free‑tier rate limit (5 calls / minute)
    time.sleep(15)   # simple sleep; for production you may want a smarter queue

    response = requests.get(base_url, params=params)
    response.raise_for_status()               # will raise if HTTP error
    data = response.json()

    # The actual data lives under the "Time Series (5min)" key
    time_series = response.get("Time Series (5min)")
    if not time_series:
        raise ValueError(f"API response missing 'Time Series (5min)' for symbol {symbol}")

    # Build a DataFrame
    raw = time_series
    df = pd.DataFrame.from_dict(time_series, orient="index")
    # Convert column names from strings like "1. open" to plain names
    df = df.rename(columns=lambda x: x.split(". ")[1])   # "1. open" → "open"
    # Cast to proper dtypes
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert the index (which is a string like "2024-01-01 09:35:00") to pandas Timestamp (UTC)
    df.index = pd.to_datetime(df.index, format="%Y-%m-%d %H:%M:%S")
    # Ensure the index is sorted ascending (oldest → newest)
    df = df.sort_index()

    return df

# How to call it

# Example: pull 5‑minute EURUSD data for the last 2 years
eurusd_df = get_alpha_vantage("EURUSD", interval="5min", outputsize="full")
print(eurusd_df.head())