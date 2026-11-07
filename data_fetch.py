"""
data_fetch.py
Pulls OHLC candle data from TwelveData for EURUSD, GBPUSD, DXY across
configured timeframes.

Note on data provider: OANDA was evaluated as an alternative (to match the
trader's TradingView "OANDA" chart feed exactly) but OANDA doesn't accept
Kenyan accounts, so its API is unavailable here. TwelveData is a pure data
aggregator (no brokerage KYC), so it works globally -- but as a tradeoff,
its forex quotes won't perfectly match any single broker's feed. Forex is
decentralized/OTC, so a few pips of difference on wicks between TwelveData
and your own chart is expected and not a bug. See README for how this is
handled (price_tolerance_pips in config).
"""

import requests
import pandas as pd
import time


class DataFetchError(Exception):
    pass


class TwelveDataClient:
    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key: str, request_delay: float = 8.0, display_tz: str = "UTC"):
        self.api_key = api_key
        # TwelveData free tier allows 8 API credits/minute. 8.0s between
        # calls keeps you safely under that. If you're on a paid plan with
        # a higher limit, lower this in config via api_delay_seconds.
        self.request_delay = request_delay
        # Timezone to convert all candle timestamps into, so reasoning-trail
        # times match what your charting platform displays. Use IANA tz
        # names (e.g. "America/New_York"), not raw offsets, so daylight
        # saving is handled automatically.
        self.display_tz = display_tz

    def get_candles(self, symbol: str, interval: str, outputsize: int = 300) -> pd.DataFrame:
        """
        Fetch OHLC candles for a symbol/interval.
        Returns a DataFrame sorted ascending by time (converted to
        display_tz), columns: open, high, low, close.
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
            "order": "ASC",
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=20)
        data = resp.json()

        if "values" not in data:
            msg = data.get("message") or data.get("status") or str(data)
            raise DataFetchError(f"Failed to fetch {symbol} [{interval}]: {msg}")

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        if df["datetime"].dt.tz is None:
            df["datetime"] = df["datetime"].dt.tz_localize("UTC")
        df["datetime"] = df["datetime"].dt.tz_convert(self.display_tz)
        df = df.sort_values("datetime").reset_index(drop=True)

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        df = df.set_index("datetime")
        time.sleep(self.request_delay)
        return df[["open", "high", "low", "close"]]

    def get_all_timeframes(self, symbol: str, timeframes: dict, outputsize: int = 300) -> dict:
        result = {}
        for label, interval in timeframes.items():
            result[label] = self.get_candles(symbol, interval, outputsize)
        return result


def compute_synthetic_dxy(components: dict) -> pd.DataFrame:
    """
    Builds a synthetic US Dollar Index from its constituent forex pairs,
    using the real ICE DXY weighting formula:

        DXY = 50.14348112 x EURUSD^-0.576 x USDJPY^0.136 x GBPUSD^-0.119
                           x USDCAD^0.091  x USDSEK^0.042 x USDCHF^0.036

    `components` is a dict of {label: DataFrame} for EURUSD, USDJPY, GBPUSD,
    USDCAD, USDSEK, USDCHF -- all already aligned to the same timeframe.
    """
    required = ["EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"]
    missing = [r for r in required if r not in components]
    if missing:
        raise DataFetchError(f"Missing components for synthetic DXY: {missing}")

    dfs = {k: components[k] for k in required}
    common_index = dfs["EURUSD"].index
    for df in dfs.values():
        common_index = common_index.intersection(df.index)

    aligned = {k: df.loc[common_index] for k, df in dfs.items()}

    result = pd.DataFrame(index=common_index)
    for col in ["open", "high", "low", "close"]:
        result[col] = (
            50.14348112
            * aligned["EURUSD"][col] ** -0.576
            * aligned["USDJPY"][col] ** 0.136
            * aligned["GBPUSD"][col] ** -0.119
            * aligned["USDCAD"][col] ** 0.091
            * aligned["USDSEK"][col] ** 0.042
            * aligned["USDCHF"][col] ** 0.036
        )

    return result.sort_index()


def fetch_full_dataset(config: dict) -> dict:
    """
    Fetches all symbols across all configured timeframes.
    Returns: { "EURUSD": {"monthly": df, ...}, "GBPUSD": {...}, "DXY": {...} }
    """
    client = TwelveDataClient(
        config["twelvedata_api_key"],
        request_delay=config.get("api_delay_seconds", 8.0),
        display_tz=config.get("display_timezone", "UTC"),
    )
    dataset = {}

    for label, symbol in config["symbols"].items():
        dataset[label] = client.get_all_timeframes(symbol, config["timeframes"])

    if config.get("use_synthetic_dxy", True):
        component_symbols = config["synthetic_dxy_components"]
        dxy_tfs = config.get("dxy_timeframes", ["h4"])
        needed_tfs = {tf: config["timeframes"][tf] for tf in dxy_tfs if tf in config["timeframes"]}
        component_data = {}
        for label, symbol in component_symbols.items():
            if label in dataset:
                component_data[label] = dataset[label]
            else:
                component_data[label] = client.get_all_timeframes(symbol, needed_tfs)

        dxy_by_tf = {}
        for tf_label in needed_tfs.keys():
            components_at_tf = {label: dfs[tf_label] for label, dfs in component_data.items()}
            dxy_by_tf[tf_label] = compute_synthetic_dxy(components_at_tf)
        dataset["DXY"] = dxy_by_tf
    else:
        dxy_symbol = config["symbols"].get("DXY", "DXY")
        dataset["DXY"] = client.get_all_timeframes(dxy_symbol, config["timeframes"])

    return dataset
