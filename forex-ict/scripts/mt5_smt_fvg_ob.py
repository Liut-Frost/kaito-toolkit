#!/usr/bin/env python3
"""
MT5 SMT / FVG / Order Block script for forex-ict
- Pulls H1 candles for EURUSDm, GBPUSDm, DXYm
- Detects FVGs and Order Blocks via smartmoneyconcepts
- Plots last 200 EURUSDm candles with FVGs/OBs
- Compares EURUSDm swing highs/lows vs DXYm for SMT divergence
"""

import os
from pathlib import Path
import pandas as pd
import MetaTrader5 as mt5

# ---- Config ----
CONFIG = {
    "symbols": ["EURUSDm", "GBPUSDm", "DXYm"],
    "timeframe": "H1",
    "bars": 500,
    "plot_last": 200,
    "output_dir": "C:/Users/HP/Documents/GitHub/kaito-toolkit/forex-ict/scripts/output",
    "plot_file": "eurusdm_h1_fvg_ob.png",
}

# ---- smartmoneyconcepts import with fallback ----
try:
    from smartmoneyconcepts import smc
    SMC_AVAILABLE = True
    print("Using smartmoneyconcepts for FVG/OB detection")
except Exception as e:
    SMC_AVAILABLE = False
    print(f"smartmoneyconcepts import failed: {e}")
    # fallback to ict_engine if needed
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from ict_engine import detect_fvgs, detect_swings, identify_order_block, detect_displacement_legs
    print("Falling back to ict_engine primitives")

def mt5_connect():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    # ensure symbols selected
    for sym in CONFIG["symbols"]:
        if not mt5.symbol_select(sym, True):
            print(f"Warning: could not select {sym}: {mt5.last_error()}")

def fetch_symbol(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, CONFIG["bars"])
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data for {symbol}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time").rename(columns={"tick_volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]].copy()
    # ensure lowercase columns
    df.columns = [c.lower() for c in df.columns]
    return df

def detect_with_smc(df):
    swings = smc.swing_highs_lows(df, swing_length=50)
    fvgs = smc.fvg(df, join_consecutive=False)
    obs  = smc.ob(df, swings)
    return swings, fvgs, obs

def plot_eurusd(df, fvgs, obs):
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import matplotlib.dates as mdates
    out_dir = Path(CONFIG["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    last_n = CONFIG["plot_last"]
    plot_df = df.tail(last_n).copy()
    # Prepare data for candlesticks
    dates = plot_df.index
    x = mdates.date2num(dates)
    opens = plot_df["open"].values
    highs = plot_df["high"].values
    lows = plot_df["low"].values
    closes = plot_df["close"].values

    fig, ax = plt.subplots(figsize=(16,8))

    # Draw candlesticks
    width = 0.6
    for i in range(len(plot_df)):
        color = 'green' if closes[i] >= opens[i] else 'red'
        # Wick
        ax.plot([x[i], x[i]], [lows[i], highs[i]], color='black', linewidth=0.8)
        # Body
        lower = min(opens[i], closes[i])
        height = abs(closes[i] - opens[i])
        rect = patches.Rectangle((x[i] - width/2, lower), width, max(height, 1e-8),
                                facecolor=color, edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)

    # FVGs
    fvg_plot = fvgs.tail(last_n)
    for idx, row in fvg_plot.iterrows():
        if pd.isna(row["FVG"]):
            continue
        top = row["Top"]
        bottom = row["Bottom"]
        color = "green" if row["FVG"] > 0 else "red"
        ax.axhspan(bottom, top, alpha=0.12, color=color)

    # Order blocks
    ob_plot = obs.tail(last_n)
    for idx, row in ob_plot.iterrows():
        if pd.isna(row["OB"]):
            continue
        top = row["Top"]
        bottom = row["Bottom"]
        color = "lime" if row["OB"] > 0 else "orange"
        # Draw OB zone as rectangle spanning from OB index to end
        try:
            ob_pos = plot_df.index.get_loc(idx)
            ax.axhspan(bottom, top, xmin=ob_pos/len(plot_df), xmax=1.0, alpha=0.18, color=color)
        except:
            ax.axhspan(bottom, top, alpha=0.18, color=color)

    ax.set_title("EURUSDm H1 - Candlesticks with FVGs and Order Blocks (last 200)")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    out_path = out_dir / CONFIG["plot_file"]
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Plot saved to {out_path}")

def smt_divergence_summary(primary_df, primary_swings, other_df, other_swings, primary_name, other_name, is_dxy=False):
    # simple swing comparison: look at last 3 swings
    def last_swings(swings_series):
        vals = []
        for i in range(len(swings_series)):
            hl = swings_series["HighLow"].iloc[i]
            if pd.isna(hl):
                continue
            vals.append((i, hl, swings_series["Level"].iloc[i]))
        return vals[-6:]  # last few

    p_sw = last_swings(primary_swings)
    o_sw = last_swings(other_swings)
    flags = []
    for (_, p_hl, p_lvl), (_, o_hl, o_lvl) in zip(p_sw, o_sw):
        # inverse for DXY
        if is_dxy:
            # expect opposite direction
            if p_hl > 0 and o_hl < 0:
                flags.append(f"SMT divergence CONFIRMED at {primary_name} high vs {other_name} low")
            elif p_hl < 0 and o_hl > 0:
                flags.append(f"SMT divergence CONFIRMED at {primary_name} low vs {other_name} high")
        else:
            if p_hl != o_hl:
                flags.append(f"SMT divergence possible: {primary_name} {p_hl} vs {other_name} {o_hl}")
    return flags

def main():
    mt5_connect()
    data = {}
    results = {}
    for sym in CONFIG["symbols"]:
        print(f"Fetching {sym}...")
        df = fetch_symbol(sym)
        data[sym] = df
        if SMC_AVAILABLE:
            swings, fvgs, obs = detect_with_smc(df)
        else:
            # fallback minimal
            swings = pd.DataFrame()
            fvgs = pd.DataFrame()
            obs = pd.DataFrame()
        results[sym] = {"swings": swings, "fvgs": fvgs, "obs": obs}
        fvg_count = int(fvgs["FVG"].notna().sum())
        ob_count = int(obs["OB"].notna().sum())
        print(f"{sym}: FVGs={fvg_count}, OBs={ob_count}")

    # Plot EURUSD
    eurusd_df = data["EURUSDm"]
    eurusd_res = results["EURUSDm"]
    plot_eurusd(eurusd_df, eurusd_res["fvgs"], eurusd_res["obs"])

    # SMT divergence EURUSD vs DXY
    flags = smt_divergence_summary(
        data["EURUSDm"], results["EURUSDm"]["swings"],
        data["DXYm"], results["DXYm"]["swings"],
        "EURUSDm", "DXYm", is_dxy=True
    )
    if flags:
        print("\nSMT divergence flags:")
        for f in flags:
            print(" -", f)
    else:
        print("\nNo clear SMT divergence flags in last swings")

    mt5.shutdown()

if __name__ == "__main__":
    main()
