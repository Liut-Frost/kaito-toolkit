# Kaito Toolkit

> Institutional ICT/SMC Trading Automation & Analysis Toolkit.

Kaito Toolkit is an end-to-end framework implementing Inner Circle Trader (ICT) / Smart Money Concepts (SMC) for Forex and Indices. The project originated as modular Pine Script indicators and evolved into a full Python algorithmic trading engine with Telegram alerting for manual execution.

---

## Architecture & Roadmap

- [x] **Project Setup & Version Control**
- [x] **Pine Script Engines (TradingView)**
  - `MarketTimeEngine.pine` — New York session boundaries, days, weeks, months
  - `DailyRangeEngine.pine` — Current/Previous Day High & Low (PDH/PDL) tracking and rendering
  - `WeeklyRangeEngine.pine` — Current/Previous Week High & Low (PWH/PWL)
  - `combinedModule.pine` — Unified Pine indicator
- [x] **Python ICT Algorithmic Engine**
  - **Domain 1 (Swings & Structure):** ICT 3-candle plateau rule, BOS, CHOCH, and MSS (Market Structure Shift)
  - **Domain 2 (Order Flow & CISD):** Change in State of Delivery (CISD) run detection, Order Blocks anchored to run origins, 50% Mean Threshold invalidation, mitigation tracking
  - **Domain 3 (Displacement Quality):** Isolated-displacement exception shifting reference lines on institutional impulse candles
  - **Domain 4 (HTF PD Array Confluence):** Order Block validation against 4H dealing ranges and higher-timeframe Fair Value Gaps
  - **Domain 5 (Liquidity Primitives):** MSS preconditions (prior liquidity sweep or HTF tap required), equal highs/lows clustering, structural stop loss calculations
  - **SMT Divergence:** Intermarket correlation analysis (EURUSD vs GBPUSD, and both vs synthetic DXY)
  - **Killzone & Session Filtering:** London Open (02:00-05:00 ET), New York Open (07:00-10:00 ET), London Close (10:00-12:00 ET), Silver Bullets AM/PM
  - **Trade Planning:** Entry models (50% Mean Threshold or confirming candle open for rapid runs), structural SL, 4H liquidity draw TP, minimum 1:3 RR filter
  - **Alert Delivery:** Telegram alerts with annotated M15 candlestick charts and step-by-step reasoning trails

---

## File Structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — single run or continuous polling loop (`--loop`) |
| `fractal_engine.py` | Top-down orchestration (Monthly/Weekly context -> Daily bias -> 4H zone -> M15 entry) |
| `ict_engine.py` | Core ICT primitives (Swings, FVGs, MSS preconditions, CISD, Order Blocks, Liquidity) |
| `session_filter.py` | ICT Killzone and Session Time Filter in New York time (`America/New_York`) |
| `smt.py` | SMT divergence logic (EURUSD vs GBPUSD vs DXY) |
| `trade_math.py` | SL/TP/RR calculation and trade plan construction |
| `data_fetch.py` | TwelveData API client & synthetic DXY formula |
| `chart_render.py` | Annotated candlestick snapshot generation with `mplfinance` |
| `telegram_alert.py` | Telegram photo and reasoning trail delivery |
| `debug_*.py` | Standalone diagnostic tools for FVG, Market Structure, and CISD Orderflow |
| `*.pine` | Original Pine Script modules for TradingView |

---

## Setup & Usage

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials
```bash
cp config.example.json config.json
```
Edit `config.json` with your credentials:
- `twelvedata_api_key`: TwelveData API key
- `telegram_bot_token`: Telegram BotFather token
- `telegram_chat_id`: Your personal/channel Telegram chat ID

*(Note: `config.json` is gitignored to protect API keys)*

### 3. Run
- **Single run:**
  ```bash
  python main.py
  ```
- **Continuous monitoring:**
  ```bash
  python main.py --loop
  ```
- **Diagnostics:**
  ```bash
  python debug_structure.py GBPUSD h4
  python debug_orderflow.py EURUSD m15
  ```

---

## Attribution

Developed by Kelvin Baya (Liut-Frost)
Co-Authored-By: Claude Code <noreply@anthropic.com>
