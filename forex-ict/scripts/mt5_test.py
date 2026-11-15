import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "EURUSD.s"

if not mt5.initialize():
    print("initialize failed:", mt5.last_error())
    quit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"could not select {SYMBOL}:", mt5.last_error())
    mt5.shutdown()
    quit()

rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 500)
mt5.shutdown()

if rates is None or len(rates) == 0:
    print("no data returned")
    quit()

df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df = df.set_index("time").rename(columns={"tick_volume": "volume"})
df = df[["open", "high", "low", "close", "volume"]]
print(df.tail())