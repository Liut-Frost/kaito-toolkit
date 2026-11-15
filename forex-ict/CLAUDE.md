# ICT Forex Trading Model

## Stack
- Python, pandas, smartmoneyconcepts (from smartmoneyconcepts import smc)
- Data: OHLC DataFrames, lowercase columns: open, high, low, close, volume

## Rules
- ICT definitions live in docs/. Read the relevant file before writing strategy logic. Never invent definitions.
- Data source: MetaTrader5 Python package (terminal must be running), broker Exness demo account.
- Symbols have an "m" suffix: EURUSDm, GBPUSDm, DXYm (dollar index). Use these exact names in all MT5 calls and keep them in one config at the top of each script.
- Backtest before calling any strategy usable. Report win rate, drawdown, number of trades.
- Scripts in /scripts, data in /data.
- Environment is Windows with PowerShell: use Windows-style commands and paths.