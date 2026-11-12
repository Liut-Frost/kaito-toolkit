# Graph Report - kaito-toolkit  (2026-11-12)

## Corpus Check
- Corpus is ~15,514 words - fits in a single context window. You may not need a graph.

## Summary
- 208 nodes · 439 edges · 33 communities (9 shown, 24 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.92)
- Token cost: 25,304 input · 0 output

## Community Hubs (Navigation)
- ict engine.py
- main.py
- fractal engine.py
- detect fvgs()
- session filter.py
- analyze market structure()
- build htf pd matrix()
- relevant pd array()
- ICT/SMC Trading Automation
- Domain 3 Displacement Quality
- main.py
- Alert Delivery
- Combined Module
- Community Structure
- Cross-File Relationships
- DailyRangeEngine
- debug *.py Modules
- Domain 1 Swings & Structure
- Domain 2 Order Flow &
- God Nodes
- graphify Skill
- Killzone & Session Filtering
- Knowledge Graph
- MarketTimeEngine
- Pine Scripts
- SMT Divergence
- Telegram Bot
- Trade Planning
- TwelveData API
- WeeklyRangeEngine

## God Nodes (most connected - your core abstractions)
1. `fractal_descend()` - 21 edges
2. `FVG` - 16 edges
3. `Swing` - 15 edges
4. `TwelveDataClient` - 13 edges
5. `render()` - 12 edges
6. `identify_order_blocks_from_cisd()` - 12 edges
7. `analyze_timeframe()` - 11 edges
8. `analyze_market_structure()` - 11 edges
9. `OrderBlock` - 10 edges
10. `detect_fvgs()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `SignalResult` --uses--> `TradePlan`  [INFERRED]
  fractal_engine.py → trade_math.py
- `fractal_descend()` --uses--> `SMTResult`  [INFERRED]
  fractal_engine.py → smt.py
- `check_smt_divergence()` --uses--> `Swing`  [INFERRED]
  smt.py → ict_engine.py
- `_recent_extreme()` --uses--> `Swing`  [INFERRED]
  smt.py → ict_engine.py
- `build_trade_plan()` --uses--> `Swing`  [INFERRED]
  trade_math.py → ict_engine.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **ICT Domain Modules** — domain_1_swings, domain_2_order_flow, domain_3_displacement, domain_4_htf, domain_5_liquidity [EXTRACTED 1.00]
- **Python ICT Modules** — main_py, fractal_engine, ict_engine, session_filter, smt_py, trade_math, data_fetch, chart_render, telegram_alert [EXTRACTED 1.00]

## Communities (33 total, 24 thin omitted)

### Community 0 - "ict engine.py"
Cohesion: 0.10
Nodes (27): main(), fractal_descend(), build_dealing_range(), calculate_atr(), _candle_direction(), _check_isolated_displacement(), _check_mss_precondition(), check_run_displacement_quality() (+19 more)

### Community 1 - "main.py"
Cohesion: 0.09
Nodes (16): render_signal_chart(), compute_synthetic_dxy(), DataFetchError, fetch_full_dataset(), TwelveDataClient, main(), render(), get_alpha_vantage() (+8 more)

### Community 2 - "fractal engine.py"
Cohesion: 0.11
Nodes (10): analyze_timeframe(), macro_context_check(), run_model(), TFAnalysis, check_smt_divergence(), _recent_extreme(), SMTResult, build_trade_plan() (+2 more)

### Community 3 - "detect fvgs()"
Cohesion: 0.24
Nodes (3): main(), main(), detect_fvgs()

### Community 4 - "session filter.py"
Cohesion: 0.31
Nodes (3): get_active_killzones(), is_in_killzone(), _to_ny_time()

### Community 5 - "analyze market structure()"
Cohesion: 0.28
Nodes (3): analyze_market_structure(), StructureEvent, StructureState

### Community 7 - "relevant pd array()"
Cohesion: 0.43
Nodes (3): DealingRange, relevant_pd_array(), validate_ob_htf_context()

### Community 8 - "ICT/SMC Trading Automation"
Cohesion: 0.33
Nodes (6): Forex Trading, ICT/SMC Trading Automation, Indices Trading, Inner Circle Trader (ICT), Kaito Toolkit, Smart Money Concepts (SMC)

### Community 9 - "Domain 3 Displacement Quality"
Cohesion: 1.00
Nodes (3): Domain 3 Displacement Quality, Domain 4 HTF PD Array Confluence, Domain 5 Liquidity Primitives

## Knowledge Gaps
- **25 isolated node(s):** `graphify Skill`, `Knowledge Graph`, `God Nodes`, `Community Structure`, `Cross-File Relationships` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 90 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `fractal_descend()` connect `ict engine.py` to `main.py`, `fractal engine.py`, `detect fvgs()`, `session filter.py`, `relevant pd array()`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Swing` (e.g. with `check_smt_divergence()` and `_recent_extreme()`) actually correct?**
  _`Swing` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `graphify Skill`, `Knowledge Graph`, `God Nodes` to the rest of the system?**
  _25 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `ict engine.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09714285714285714 - nodes in this community are weakly interconnected._
- **Why does `OrderBlock` connect `ict engine.py` to `fractal engine.py`, `relevant pd array()`, `.mean threshold()`, `.proximal edge()`, `.valid()`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09082125603864734 - nodes in this community are weakly interconnected._
- **Why does `HTFPDArray` connect `build htf pd matrix()` to `ict engine.py`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._