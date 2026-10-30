# GVQM Trading Bot: 7-Module Technical Architecture & System Reference

## 1. System Overview: The 7-Module Architecture

The Good Value Quick Money (GVQM) engine decomposes automated equity trading into seven decoupled modules. This modular separation ensures that enhancements to data sources, ranking models, AI providers, or execution brokers remain isolated to their respective domains without destabilizing the broader pipeline.

```text
[ MODULE 1: THE SCANNER ]
  -> Universe Ingestion (S&P 500 / Fortune 500)
  -> 250-Day Moving Average & Discount Filtering
  -> Google Sheets Contender Flagging & Inactive Elo Reset (Active_Contenders = 'Y'/'N', Elo = 1500.0 on 'N')
          |
          v
[ MODULE 2: MINOR LEAGUE MATCHMAKER & SCHEDULER ]
  -> Staleness Sorting (Priority Queue via Last_Match)
  -> Live Pricing Ingestion
  -> Adjacent-Elo Fair Pairing
          |
          v
[ MODULE 3: JUNIOR SCOUT AI ADJUDICATION ENGINE ]
  -> LLM Evaluation (Gemini API + Dual-Layer Reasoning)
  -> Hallucination Validation Guardrails
  -> Junior Elo Math & Decision Ledger Persistence
          |
          v
[ MODULE 4: PORTFOLIO MAINTENANCE & TRAPDOOR GUARD ]
  -> Active Holdings Ingestion & Live Price Fetch
  -> Batch Health Audit via Senior Agent
  -> Emergency Trapdoor Liquidations & Trailing Stop Updates
          |
          v
[ MODULE 5: MAJOR LEAGUE TOURNAMENT ENGINE ]
  -> Top Junior Rookie Draft (Call-Up)
  -> Cross-Pollinated Roster Shuffling (Champions vs. Challengers)
  -> Senior Agent Matchup Adjudication & Senior Elo Updates
  -> Senior Active Contender Sync & Inactive Elo Reset
          |
          v
[ MODULE 6: FRONT OFFICE ALLOCATION & SWAP ENGINE ]
  -> Portfolio Capacity Check (Max Position Sizing)
  -> Scenario A: Slot Fill-Up Orders via Alpaca Broker
  -> Scenario B: Swap Hurdle Verification (Challenger Elo > Champion Elo + Threshold)
  -> Sequenced Liquidation, Cash Settlement Cooldown, Entry Execution, and ORDER_REJECTED Audit Logging
          |
          v
[ MODULE 7: EXECUTIVE BRIEFING & MULTI-DAY MEMORY ]
  -> Historical Rank Extraction (A1 Cell JSON Storage)
  -> 3-to-7 Day Rank Momentum Calculation (Rising Stars / Momentum Movers)
  -> Multi-Asset HTML Briefing Dispatch (Resend API)
  -> Corporate Strategy Brief Logging
```

---

## 2. Module 1: The Scanner (Asset Discovery Engine)

```text
[S&P 500 / Universe Provider] --> [Alpaca Market Data API] --> [Moving Average Calculation] --> [Sheets Active Flag & Elo Reset Sync]
```

### Core Responsibility
Scans a large-cap equity universe, calculates moving average technical metrics, isolates equities trading at a specified discount to their 250-day moving average, and synchronizes candidate eligibility flags with the central database. Crucially, whenever a stock drops off the active distressed list, its status is set to `N` and its Elo rating is reset to baseline (1500.0) to prevent stale historical scores from biasing future evaluations.

### Primary Source Files
* `lib/good_value_quick_money_market_scanner.py`
* `bot.py` (Orchestration in `run_minor_league`)
* `gvqm_junior_history.py` (`update_active_contenders_flag`)

### Inputs & Configuration Parameters
* **Universe Source:** S&P 500 / Fortune 500 constituent roster (via Wikipedia/Yahoo Finance provider).
* **MOVING_AVERAGE_WINDOW:** 250 trading days (1 calendar year).
* **DISCOUNT_THRESHOLD_PERCENT:** Percentage threshold below the 250 MA required to qualify as distressed (e.g., 10%, 15%, or 20%).
* **Broker Data API:** Alpaca Market Data API (`trader.get_bars` for historical pricing; `trader.get_current_price` for active trade/quote).

### Execution Logic
1. **Constituent Fetch:** Downloads current universe symbols.
2. **Historical Bar Retrieval:** Pulls 250 daily closing bars for each symbol.
3. **Metric Calculation:**
   * 250 MA = Sum of 250 daily closes / 250
   * Discount % = ((250 MA - Current Price) / 250 MA) * 100
4. **Filtering:** Retains only assets where Discount % >= DISCOUNT_THRESHOLD_PERCENT.
5. **State Flag Synchronization & Elo Reset (with Exemption Clause):** Invokes `league_common.update_active_contenders_flag("Junior_Elo", active_and_protected, wipe_inactive_elo=True)`.
   * **The Exemption Clause:** Before synchronizing, the engine checks the top `SENIOR_DRAFT_LIMIT` stocks on the `Junior_Elo` leaderboard. These elite stocks are explicitly exempted from being marked inactive. This ensures a stock that has fought its way to the top isn't prematurely disqualified from a Major League draft simply because its price organically rose just above the moving average threshold. It must lose matches and naturally fall out of the top N before it can be disqualified by price alone.
   * Sets `Active_Contenders = 'Y'` for qualifying/exempt tickers.
   * Sets `Active_Contenders = 'N'` for previously tracked tickers that no longer meet criteria (and are not exempt).
   * **Elo Reset Rule:** For any ticker set to `Active_Contenders = 'N'`, automatically resets `Elo_Rating = 1500.0` in the sheet. This eliminates stale memory from months prior so returning candidates always start fresh on a clean baseline.

### Module Interface & Clean Boundary
* **Output:** A list of valid, active distressed ticker symbols (`List[str]`) and updated row flags/reset Elo ratings in the `Junior_Elo` Google Sheet.
* **Decoupling Boundary:** Module 1 does not evaluate fundamentals or inspect portfolio holdings. Its database interaction is strictly limited to candidate eligibility discovery and active state synchronization.

---

## 3. Module 2: Minor League Matchmaker & Scheduler

```text
[Junior_Elo Leaderboard] --> [Filter Active ('Y')] --> [Sort by Staleness] --> [Live Price Tagging] --> [Adjacent Elo Pairing]
```

### Core Responsibility
Ingests qualified candidate tickers from Module 1, cross-references historical match recency in Google Sheets, isolates candidates through a staleness priority queue, fetches live pricing, and pairs assets into balanced matchups.

### Primary Source Files
* `gvqm_minor_league.py`
* `gvqm_junior_history.py`

### Inputs & Configuration Parameters
* **DAILY_SCAN_LIMIT:** Maximum candidate cap for today's active evaluation pool (default: 20).
* **match_count:** Dynamic match ceiling: `max(1, floor(len(candidates) / 2))`
* **Database State:** `Junior_Elo` tab (`Active_Contenders`, `Last_Match`, `Elo_Rating`).

### Function Implementations & Logic Flow

#### `junior_history.filter_candidates(distressed_tickers: List[str], limit: int = 20) -> List[str]`
* **Priority 1 (Rookies / Fresh Contenders):** Tickers with no historical matches or newly reset baseline scores (`Last_Match == '1900-01-01'`) placed at head of queue.
* **Priority 2 (Stale Veterans):** Tickers sorted ascending by `Last_Match` timestamp (longest since last evaluation).
* Truncates output to `limit`.

#### `minor_league.get_minor_league_matchups(candidates: List[Dict], match_count: int = 3) -> List[Tuple[Dict, Dict]]`
* Attaches current Elo ratings and timestamps via `_enrich_candidates(candidates, "Junior_Elo")`.
* Sorts candidates by `_last_match_dt` ascending (stalest first).
* Takes the top `match_count * 2` contenders, re-sorts that subset by `_elo` descending, and pairs adjacent elements: `Matchup_i = (Candidate_2i, Candidate_2i+1)`.

### Module Interface & Clean Boundary
* **Output Payload:** A structured list of head-to-head match tuples:
  ```python
  [
      ({"ticker": "INTC", "current_price": 22.50, "_elo": 1520.0}, {"ticker": "WBD", "current_price": 7.80, "_elo": 1515.2}),
      ({"ticker": "T", "current_price": 18.20, "_elo": 1490.5}, {"ticker": "PFE", "current_price": 27.10, "_elo": 1488.0})
  ]
  ```
* **Decoupling Boundary:** Does not interact with AI models or submit orders. Any changes to matchmaking balance or queue prioritization remain inside this module.

---

## 4. Module 3: Junior Scout AI Adjudication Engine

```text
[Matchup Tuple] --> [Gemini API (Junior Prompt)] --> [Hallucination Guard] --> [Elo Calculation] --> [Decision Logging]
```

### Core Responsibility
Executes automated fundamental and technical analysis between matched pairs using Google's Gemini API, enforces non-technical beginner educational reasoning, validates winners against hallucination, updates Elo ratings, and records rationales in Google Sheets.

### Primary Source Files
* `gvqm_junior_agent.py`
* `gvqm_junior_prompts.py`
* `gvqm_minor_league.py`
* `gvqm_junior_history.py`

### Prompt & Analytical Directives (`JUNIOR_MATCHUP_PROMPT`)
* **Role:** Senior Quantitative Manager & Mentor.
* **Teaching Directive:** All technical metrics must use **Dual-Layer** notation: `Wall Street Term (Plain-English Analogy / Simple Explanation)`.
* **Input Data & Price Grounding:** Injects live market prices fetched from the Alpaca Market Data API into the prompt (`Candidate A: {ticker_a} (Current Market Price: ${price_a})`), falling back to `N/A` if unavailable, grounding valuation and profit ceiling calculations in current reality.
* **Mandate Weights:** Safety Priority: 30% | Reward Priority: 70%.
* **12-Pillar Analytical Framework:**
  1. Financial Safety (Balance sheet liquidity / cash runway)
  2. Reality Check (Temporary headwind vs. broken business model)
  3. Economic Moat (Competitive barriers)
  4. Macro Wind (Sector-wide tailwinds)
  5. Bargain Bin (Enterprise value vs. free cash flow)
  6. Bleeding Check (Selling volume exhaustion)
  7. Insider Buying (Open-market executive purchases)
  8. Quiet Accumulation (Volume balance on down vs. up days)
  9. Coiled Spring (Consolidation duration)
  10. The Spark (Imminent fundamental catalyst)
  11. Upgrade Cycle (Sell-side revisions)
  12. Profit Ceiling (Distance to technical resistance)
  13. Event Risk Assessment (Binary events treated neutral unless corroborated)
* **Tie-Breaker Rule:** Mandatory default to the candidate demonstrating superior Safety.

### Function Implementations & Logic Flow

#### `junior_agent._call_gemini_api(prompt: str, context_label: str) -> Dict | None`
* Directly queries `v1beta/models/{MODEL_NAME}:generateContent`.
* Enables `googleSearch` grounding.
* Sets safety thresholds to `BLOCK_NONE`.
* Implements exponential backoff: HTTP 429 waits 60s; HTTP 5xx backs off by `(attempt + 1) * 10`s. Max 3 retries.
* Strips markdown and backticks via `clean_json_text()`.

#### `minor_league.calculate_elo(winner_rating: float, loser_rating: float, k_factor: int = 32) -> Tuple[float, float]`
* Expected_winner = `1 / (1 + 10^((loser_rating - winner_rating) / 400))`
* New_winner = `winner_rating + k_factor * (1 - Expected_winner)`
* New_loser = `loser_rating + k_factor * (0 - Expected_loser)`

#### `junior_history.log_report(winner_ticker: str, analysis: Dict, opponent: str) -> None`
* Appends row to `Junior_Decisions` worksheet: `[Timestamp, Matchup, Winner, Rationale]`.

#### `junior_history.update_active_contenders_flag(tab_name: str, todays_active_tickers: List[str]) -> None`
* Reads worksheet header to locate `Active_Contenders` and `Elo_Rating` columns.
* For tickers present in `todays_active_tickers`, updates status to `Active_Contenders = 'Y'`.
* For tickers NOT present in `todays_active_tickers`, updates status to `Active_Contenders = 'N'` AND resets `Elo_Rating = 1500.0`.
* Batch updates Google Sheets in a single API request to avoid rate limit issues.

### Module Interface & Clean Boundary
* **Output:** Updated Elo scores on `Junior_Elo` tab, battle records on `Junior_Decisions` tab, and entries appended to `daily_ai_logic` memory array.

---

## 5. Module 4: Portfolio Maintenance & Trapdoor Guard

```text
[Live Portfolio Positions] --> [Fetch Live Prices] --> [Batch Senior Paperwork Request]
                                                             |
                              +------------------------------+------------------------------+
                              |                                                             |
                     [Action == LIQUIDATE]                                         [Action == MAINTAIN]
                              |                                                             |
                [trader.close_full_position()]                                [trader.execute_update()]
                              |                                                             |
               [senior_history.log_mechanical_trade()]                       [senior_history.log_detailed_decisions()]
```

### Core Responsibility
Performs daily structural risk audits on active positions before new capital deployment. Updates dynamic trailing stops, profit targets, or triggers emergency liquidations ("trapdoor exits") if a thesis breaks.

### Primary Source Files
* `gvqm_senior_agent.py`
* `gvqm_senior_history.py`
* `bot.py` (Orchestration in `maintain_portfolio`)
* `lib/gvqm_senior_paperwork_prompt.py`

### Execution Logic Flow
1. **Portfolio Discovery:** Calls `get_live_portfolio()` to collect all active position symbols.
2. **Price Extraction:** Pulls live pricing into `portfolio_data = {ticker: current_price}`.
3. **Batch Audit Call:** Dispatches single batch payload to Gemini: `senior_agent.generate_batch_execution_paperwork(portfolio_data)`.
4. **Action Processing:**
   * **Trapdoor Branch (`action == "LIQUIDATE"`):**
     * Submits market exit via `trader.close_full_position(ticker)`.
     * If filled, logs exit to `Trade_Log` tab via `senior_history.log_mechanical_trade(ticker, "EMERGENCY_EXIT", rationale, price, shares)`.
     * Injects trapdoor alert into `daily_ai_logic`.
     * **Trapdoor Demotion Protocol (Re-Buy Prevention & League Isolation):**
       - Injects `ticker` into the runtime session set `liquidated_today`, strictly suppressing same-day re-drafting in Major League (Module 5) and same-day re-allocation / capacity fill-ups (Module 6).
       - Invokes `league_common.banish_ticker(ticker)`, which locates the ticker in `Senior_Elo`, sets `Active_Contenders = 'N'`, and resets `Elo_Rating = 1500.0` (terminating its Major League tenure and removing its Champion status).
       - **Grassroots Minor League Preservation:** Crucially, `banish_ticker` does **NOT** alter or wipe `Junior_Elo`. The asset's grassroots Minor League match history (accumulated wins, losses, win rate, and Junior Elo rating) remains strictly preserved. Once the liquidation trading session clears, if the asset's fundamentals recover, its preserved Junior standing allows it to naturally qualify for future Rookie Call-Up drafts rather than being permanently locked out of the trading pipeline.
   * **Maintenance Branch (`action == "MAINTAIN"` / `"UPDATE_EXISTING"`):**
     * Adjusts broker stop-loss and take-profit orders via `trader.execute_update(ticker, take_profit, stop_loss)`.
     * Logs updated risk thresholds to `Trade_Log` via `senior_history.log_detailed_decisions()`.

### Module Interface & Clean Boundary
* **Output:** Verified, clean portfolio state ready for allocation decisions; updated orders at broker; risk event audit trails in Google Sheets.
* **Decoupling Boundary:** Operates exclusively on *currently held* assets. Does not consider Minor League rookies.

---

## 6. Module 5: Major League Tournament Engine

```text
[Junior_Elo Leaderboard] --> [Filter Top Unowned Rookies] --> [Combine with Active Holdings]
                                                                    |
                                                                    v
                                                  [Random Shuffle Both Lineups]
                                                                    |
                                                                    v
                                                 [Senior Agent Cross-Pollinated Matchup]
                                                                    |
                                                                    v
                                                 [Update Senior_Elo & Senior_Decisions]
                                                                    |
                                                                    v
                                             [Senior Active Sync & Inactive Elo Reset]
```

### Core Responsibility
Drafts top-performing unowned assets from the Minor League, combines them with active portfolio holdings into an elite roster, and executes title defense matches evaluated by the Senior LLM Agent. Synchronizes `Senior_Elo` active status flags and resets Elo scores for inactive candidates to 1500.0.

### Primary Source Files
* `gvqm_minor_league.py`
* `gvqm_senior_agent.py`
* `gvqm_senior_prompts.py`
* `gvqm_senior_history.py`
* `bot.py` (Orchestration in `run_major_league`)

### Execution Logic Flow
1. **The Rookie Call-Up:**
   * Reads `Junior_Elo` leaderboard via `minor_league.fetch_leaderboard("Junior_Elo")`.
   * Sorts junior stocks by Elo descending.
   * Filters out stocks already held in `portfolio_tickers`.
   * Extracts top `SENIOR_DRAFT_LIMIT` (default: 3) tickers.
2. **Roster Unification:** `major_league_roster = list(set(portfolio_tickers + promoted_rookies))`
3. **Cross-Pollinated Pairing (`minor_league.get_major_league_matchups`):**
   * Divides roster into Champions (owned) and Challengers (unowned).
   * **Shuffle Protocol:** Applies `random.shuffle()` to both pools to eliminate deterministic rematch loops and minimize duplicate API costs.
   * Pairs each Champion with an available Challenger.
4. **Senior Agent Evaluation:**
   * Invokes `senior_agent.evaluate_matchup(cand_a, cand_b)` using `SENIOR_MATCHUP_PROMPT` under high reasoning settings (`thinkingLevel="HIGH"`), injecting live Alpaca prices (`Candidate A: {ticker_a} (Current Market Price: ${price_a})`) for market grounding.
   * Validates winner against hallucinations.
   * Updates `Senior_Elo` tab via `minor_league.record_match_result("Senior_Elo", winner, loser)`.
   * Logs title defense decision to `Senior_Decisions` worksheet via `senior_history.log_matchup()`.
   * Invokes `junior_history.update_active_contenders_flag("Senior_Elo", major_league_roster)`.
     * Sets `Active_Contenders = 'Y'` for current Major League roster tickers.
     * Sets `Active_Contenders = 'N'` for demoted/inactive tickers AND resets their `Elo_Rating = 1500.0` to eliminate stale historical scores.

### Module Interface & Clean Boundary
* **Output:** Updated `Senior_Elo` standings reflecting relative strength between active holdings and prospective acquisitions, with clean 1500.0 resets for dropped contenders.

---

## 7. Module 6: Front Office Allocation & Swap Engine

```text
                              [Fetch Senior_Elo Leaderboard]
                                            |
                  +-------------------------+-------------------------+
                  |                                                   |
     [Portfolio Size < Max Capacity]                     [Portfolio Size >= Max Capacity]
       (SCENARIO A: CAPACITY FILL)                         (SCENARIO B: SWAP PROTOCOL)
                  |                                                   |
     [Isolate Top Unowned Senior]                    [Identify Best Challenger & Worst Champion]
                  |                                                   |
     [Request Entry Trade Paperwork]                 [Is Challenger Elo > Champion Elo + 15.0?]
                  |                                                   |
     [trader.execute_entry()]                         +---------------+---------------+
                  |                                   |                               |
     +------------+------------+                    [YES]                            [NO]
     |                         |                      |                               |
 [SUCCESS]                 [REJECTED]   [1. Liquidate Worst Champion]       [Maintain Roster]
     |                         |                      |                               |
[Log Trade_Log]       [Log ORDER_REJECTED] [2. Settle Delay: sleep(3)]                |
(detailed_decisions)   (log_mechanical)               |                               |
     |                         |        [3. Generate Winner Paperwork]                |
     |                         |                      |                               |
     |                         |        [4. Execute Winner Entry]                     |
     |                         |                      |                               |
     |                         |         +------------+------------+                  |
     |                         |         |                         |                  |
     |                         |     [SUCCESS]                 [REJECTED]             |
     |                         |         |                         |                  |
     |                         |   [Log Trade_Log]        [Log ORDER_REJECTED]        |
     |                         | (detailed_decisions)      (log_mechanical)           |
     |                         |         |                         |                  |
     +------------+------------+---------+-------------------------+------------------+
                                         |
                                         v
                         [Proceed Cleanly to Module 7 Briefings]
```

### Core Responsibility
Governs capital deployment. Determines whether to allocate cash into empty portfolio slots or trigger asset replacement swaps based on Elo rating differentials. Unmasks granular broker rejections, maintains an immutable failure audit trail in Google Sheets, and preserves pipeline continuity so downstream executive briefings execute without interruption.

### Primary Source Files
* `bot.py` (Orchestration in `execute_swaps`)
* `gvqm_senior_agent.py`
* `lib/gvqm_senior_history.py`
* `lib/gvqm_alpaca_trader.py`

### Inputs & Configuration Parameters
* **MAX_PORTFOLIO_POSITIONS:** Maximum simultaneous holdings allowed (default: 3).
* **ELO_SWAP_THRESHOLD:** Minimum rating advantage a challenger must hold over an incumbent to trigger a swap (default: 15.0 Elo points).
* **MAX_INVESTMENT_PER_POSITION:** Dollar allocation per holding.

### Execution Logic Flow

#### Scenario A: Capacity Fill-Up (Empty Slots Available)
1. **Capacity Audit:** Checks open slots: `open_slots = MAX_PORTFOLIO_POSITIONS - len(portfolio_tickers)`.
2. **Drafting:** Selects highest-ranked unowned tickers from `Senior_Elo`.
3. **Paperwork Request:** Calls `senior_agent.generate_batch_execution_paperwork({ticker: current_price})`.
4. **Broker Entry Submission:** Submits bracket order via `trader.execute_entry(ticker, amount, buy_limit, take_profit, stop_loss)`.
5. **Outcome Evaluation & Audit Trail:**
   * **Success Branch:** If entry order succeeds, logs trade details to `Trade_Log` via `senior_history.log_detailed_decisions()` and records allocation thesis in `daily_ai_logic`.
   * **Rejection / Exception Branch (Broker Error Unmasking):** If Alpaca rejects the order or an exception occurs:
     * Unmasks the exact broker rationale via `_extract_broker_error()` and `entry_status[0].get("info")`.
     * Logs the specific broker rejection reason directly to stdout: `log_pipeline(f" ❌ Allocation Fill aborted: Alpaca rejected order for {best_ticker}. Reason: {error_reason}")`.
     * Records an audit row in Google Sheets `Trade_Log` via `senior_history.log_mechanical_trade(best_ticker, "ORDER_REJECTED", error_reason, current_price, 0)`.
     * If an unhandled exception occurs in the entry pipeline, logs `ORDER_REJECTED` with rationale `Pipeline Exception: {e}`.
     * Leaves the slot available in cash and proceeds cleanly without crashing execution.

#### Scenario B: The Swap Protocol (Portfolio Full)
1. **Target Identification:** Extracts `best_unowned` challenger and `worst_owned` champion from `Senior_Elo`.
2. **Hurdle Verification:** Tests the Hurdle Condition: `Elo_challenger > Elo_champion + ELO_SWAP_THRESHOLD`.
3. **Execution Sequence:**
   * **Step 1 (Liquidation):** Calls `trader.close_full_position(worst_ticker)`. Logs exit to `Trade_Log` via `senior_history.log_mechanical_trade()`.
   * **Step 2 (Cash Settlement Cooldown):** Executes `time.sleep(3)` to allow broker balance clearing.
   * **Step 3 (Paperwork Generation):** Obtains entry limits and stop levels for incoming asset via `senior_agent.generate_batch_execution_paperwork()`.
   * **Step 4 (Acquisition & Outcome Handling):** Fires entry order via `trader.execute_entry()`.
     * **Success Branch:** Logs swap transaction to `Trade_Log` via `senior_history.log_detailed_decisions()` and records replacement in `daily_ai_logic`.
     * **Rejection / Exception Branch (Capital Preservation):** If Alpaca rejects the buy order or an exception occurs:
       * The incumbent champion has been liquidated, preserving capital in cash.
       * Unmasks the exact broker rejection explanation via `entry_status[0].get("info")` or pipeline exception string.
       * Logs full failure context to stdout: `log_pipeline(f" ❌ Swap incomplete: Alpaca liquidated {worst_ticker} but rejected buy order for {best_ticker}. Reason: {error_reason}")`.
       * Appends an audit row to `Trade_Log` via `senior_history.log_mechanical_trade(best_ticker, "ORDER_REJECTED", error_reason, current_price, 0)`.
       * Gracefully bypasses position creation while maintaining pipeline continuity to Module 7.

---

### Broker Rejection Handling & Audit Trail Protocol (`GVQM-TICKET-01`)

To guarantee complete operational transparency and ensure that downstream modules never suffer catastrophic failures due to broker-level rejections (e.g., margin limits, pattern day trading rules, minimum order constraints, or invalid symbol status), Module 6 enforces a dedicated five-step rejection handling and audit protocol:

```text
[Broker Exception / Rejection]
              |
              v
[1. Deep Error Extraction (_extract_broker_error)]
  -> Inspects: e.message, e.error['message'], e._error['message'], JSON string, or raw fallback
              |
              v
[2. Contract Enforcer Dict Preservation (_enforce_contract)]
  -> Preserves dict payload: isinstance(data, dict) -> [data]
  -> Eliminates stringified dictionary representations (e.g., "{'event': 'ERROR'}")
              |
              v
[3. Multi-Line Terminal Formatting (log_execution_matrix)]
  -> Wraps info text across up to 4 lines using textwrap (width: 24, boundary: 32 columns)
  -> Zero character cutoff; renders complete broker explanation in stdout
              |
              v
[4. Google Sheets Audit Persistence & Pipeline Safety]
  -> Appends ORDER_REJECTED row to Trade_Log via log_mechanical_trade()
  -> Catches pipeline exceptions; guarantees seamless progression to Module 7 Briefings
```

#### 1. Broker Error Unmasking (`_extract_broker_error`)
Legacy implementations often masked broker rejections behind generic status strings or truncated error codes. The `_extract_broker_error(e)` utility extracts the root explanation from Alpaca SDK exceptions:
* **Attribute Inspection:** Sequentially checks `e.message`, `e.error`, and `e._error` for structured dictionary payloads or JSON strings containing a `message` key.
* **JSON Envelope Parsing:** If `str(e)` begins and ends with curly braces, safely parses the payload as JSON to retrieve `parsed['message']`.
* **Clean Fallback:** Returns clean unmasked error text (e.g., `"insufficient buying power: require $10000.00 but available is $4520.10"`, `"order is not fractionable"`), falling back to `"Unknown broker error"` only if no string representation exists.

#### 2. Contract Enforcer Dictionary Preservation (`_enforce_contract`)
Trader responses must adhere to a standardized contract list `[{"event": ..., "info": ...}]`:
* Ensures that dictionary payloads passed into `_enforce_contract` are preserved directly: `if isinstance(data, dict): return [data]`.
* Eliminates the issue where passing an error dict converted it into stringified dictionary representations (e.g., `"{'event': 'ERROR', 'info': '...'}"`), ensuring callers can cleanly access `entry_status[0].get("info")` directly without regex parsing.

#### 3. Multi-Line Terminal Execution Matrix (`log_execution_matrix`)
When an order event terminates in `"ERROR"`, `"HOLD"`, or `"CANCEL_PENDING"`, the terminal execution matrix logs diagnostic information:
* Replaces legacy 25-character hard truncation (`[:25]`) with word-wrapping via Python's `textwrap.wrap(info_text, width=col_width - 8)`.
* Wraps across up to 4 lines within the 32-column boundary (`col_width = 32`), displaying the full broker rejection explanation without breaking the visual alignment of the execution table.

#### 4. Audit Trail Persistence in `Trade_Log`
Every rejected entry order (both in Scenario A and Scenario B) is recorded in Google Sheets `Trade_Log` via `senior_history.log_mechanical_trade()` with 8-column alignment:

| Column Position | Header Name | Recorded Value | Description |
| :---: | :--- | :--- | :--- |
| **Col 1** | `Date` | `YYYY-MM-DD HH:MM:SS` | Timestamp of rejection event. |
| **Col 2** | `Ticker` | `{best_ticker}` | Target equity candidate. |
| **Col 3** | `Action` | `"ORDER_REJECTED"` | Explicit rejection status identifier. |
| **Col 4** | `Entry_Price` | `{current_price}` | Market price at time of order attempt. |
| **Col 5** | `Stop_Loss` | `""` | Empty string (no order filled). |
| **Col 6** | `Take_Profit` | `""` | Empty string (no order filled). |
| **Col 7** | `Rationale` | `{error_reason}` | Exact unmasked broker rejection explanation. |
| **Col 8** | `Shares_Held` | `0` | Explicit 0 shares held indication. |

#### 5. Graceful Pipeline Continuation to Module 7
Broker rejections and entry pipeline exceptions are fully isolated within Module 6:
* All order execution and logging calls in `execute_swaps()` are protected with nested `try/except` blocks.
* A rejected buy order does not halt bot execution or raise unhandled exceptions.
* The pipeline seamlessly proceeds to **Module 7: Executive Briefing & Multi-Day Memory**, allowing CEO reports, account balances, and scouting notifications to be generated and dispatched without interruption.

### Module Interface & Clean Boundary
* **Output:** Real-world capital allocation via broker API, update of `Trade_Log` (including successful entries, exits, and unmasked `ORDER_REJECTED` audit entries), and emission of allocation audit messages.
* **Decoupling Boundary:** Operates exclusively at the trade execution and broker interface boundary. Does not modify candidate scouting or recalculate Elo ratings.

---

## 8. Module 7: Executive Briefing & Multi-Day Memory

```text
[Gather daily_ai_logic Logs] --> [Extract Historical Ranks from Sheet A1] --> [Compute 3-7 Day Momentum]
                                                                                      |
                                    +-------------------------------------------------+-------------------------------------------------+
                                    |                                                                                                   |
                  [Minor League Scouting Brief (Resend API)]                                                    [Major League Executive Brief (Resend API)]
                                    |                                                                                                   |
                    - Rising Stars Table                                                                        - Executive Actions Taken
                    - Top 5 Heavyweights                                                                        - Account Equity & Buying Power
                    - Dual-Layer Educational Notes                                                              - Unrealized P/L by Position
                                                                                                                - Major Standings & Momentum Shifts
```

### Core Responsibility
Aggregates logs, calculates multi-day momentum metrics by comparing live rankings against historical snapshots stored in Google Sheets, generates responsive HTML executive emails, and dispatches briefings via Resend.

### Primary Source Files
* `gvqm_email_notifier.py`
* `gvqm_junior_history.py` (Memory bank persistence)
* `gvqm_senior_history.py` (Memory bank persistence)
* `bot.py` (Orchestration in `__main__`)

### Multi-Day Momentum Logic (`get_rising_stars` & `get_senior_momentum`)
1. **Memory Retrieval:** Invokes `load_history_from_sheets()` / `load_senior_history_from_sheets()` to fetch JSON from cell `A1` of `Junior_Memory_Bank` / `Senior_Memory_Bank`.
2. **State Injection:** Converts current standings into `{ticker: rank}` map and stores under key `YYYY-MM-DD`.
3. **Memory Persistence:** Overwrites updated JSON string back into cell `A1` via `save_history_to_sheets()` / `save_senior_history_to_sheets()`.
4. **Lookback Resolution:** Targets `today - 3 days`. If exact date is unavailable, falls back to oldest available date in history.
5. **Momentum Metric:** `Delta_rank = Rank_past - Rank_current` (Positive value indicates rank improvement toward #1). Returns top 3 positive movers.

### Dispatch Payloads
* **Scouting Report (`send_minor_league_scouting_report`):**
  * Minor League Rising Stars.
  * Top 5 Minor League Heavyweights.
  * Dual-layer beginner educational battle breakdowns.
* **Executive Brief (`send_executive_brief`):**
  * Immediate actions executed (Swaps, Entries, Liquidations).
  * Account financial metrics (Equity, Cash %, Position P/L).
  * Major League standings and momentum shifts.
  * Senior Agent portfolio diaries.

### Module Interface & Clean Boundary
* **Output:** Outbound SMTP/API emails via Resend and strategy summaries archived to the `Strategy_Brief` tab.

---

## 9. Master Google Sheets Database Schema

Central Google Sheet: `TradingBot_History`

| Tab Name | Owner Module | Column Names & Order | Data Types | Functional Description |
| :--- | :--- | :--- | :--- | :--- |
| `Junior_Elo` | Module 1 & 3 | `Ticker`, `Elo_Rating`, `Wins`, `Losses`, `Win_Rate`, `Last_Match`, `Active_Contenders` | `str`, `float`, `int`, `int`, `str`, `str (YYYY-MM-DD HH:MM:SS)`, `str (Y/N)` | Minor League master leaderboard and scanner status. Transition to `Active_Contenders = 'N'` resets `Elo_Rating` to `1500.0`. |
| `Junior_Decisions` | Module 3 | `Date`, `Matchup`, `Winner`, `Rationale` | `str (YYYY-MM-DD HH:MM)`, `str`, `str`, `str` | Scouting head-to-head decision archive. |
| `Junior_Memory_Bank` | Module 7 | Raw cell `A1` | `JSON String` | Multi-day rank histories for Minor League momentum calculations. |
| `Senior_Elo` | Module 5 | `Ticker`, `Elo_Rating`, `Wins`, `Losses`, `Win_Rate`, `Last_Match`, `Active_Contenders` | `str`, `float`, `int`, `int`, `str`, `str (YYYY-MM-DD HH:MM:SS)`, `str (Y/N)` | Major League master leaderboard and roster status. Transition to `Active_Contenders = 'N'` resets `Elo_Rating` to `1500.0`. |
| `Senior_Decisions` | Module 5 | `Date`, `Matchup`, `Winner`, `Rationale` | `str (YYYY-MM-DD HH:MM)`, `str`, `str`, `str` | Title defense match rationale archive. |
| `Senior_Memory_Bank` | Module 7 | Raw cell `A1` | `JSON String` | Multi-day rank histories for Major League momentum calculations. |
| `Trade_Log` | Module 4 & 6 | `Date`, `Ticker`, `Action`, `Entry_Price`, `Stop_Loss`, `Take_Profit`, `Rationale`, `Shares_Held` | `str (YYYY-MM-DD HH:MM:SS)`, `str`, `str`, `float`, `float`, `float`, `str`, `int` | Comprehensive execution ledger for trades, maintenance, trapdoors, and unmasked broker rejections (`ORDER_REJECTED`). |
| `Strategy_Brief` | Module 7 | `Date`, `CEO_Report` | `str (YYYY-MM-DD HH:MM)`, `str` | Archive of daily executive briefings. |

---

## 10. Cross-Module Impact & Enhancement Matrix

| Targeted Enhancement | Primary Module | Secondary Modules Impacted | Files Requiring Changes | Mitigation & Safeguard Directives |
| :--- | :--- | :--- | :--- | :--- |
| **Reset Elo to 1500.0 for Inactive Contenders ('N')** | **Module 1 & 5** | Module 2 & 3 | `gvqm_junior_history.py` (`update_active_contenders_flag`), `bot.py` | Ensures stocks returning after months of inactivity start at baseline 1500.0 rather than carrying stale historical scores. |
| **Switch Universe from S&P 500 to Russell 2000** | **Module 1** | Module 2 | `good_value_quick_money_market_scanner.py` | Ensure ticker formatting matches Alpaca symbology. Increase Google Sheets quotas for larger contender tracking. |
| **Modify Moving Average Window or Discount %** | **Module 1** | None | `good_value_quick_money_market_scanner.py`, `config.py` | Stricter thresholds reduce candidate volume; ensure `DAILY_SCAN_LIMIT` handles smaller pools gracefully. |
| **Change Staleness Prioritization Algorithm** | **Module 2** | None | `gvqm_junior_history.py` (`filter_candidates`) | Keep fallback timestamp (`1900-01-01`) for unranked rookies to prevent starvation. |
| **Adjust Elo Volatility ($K$-Factor)** | **Module 3 & 5** | Module 6 | `gvqm_minor_league.py` (`calculate_elo`) | $K > 48$ induces extreme volatility; $K < 16$ suppresses rookie promotions. Re-evaluate `ELO_SWAP_THRESHOLD` if $K$ changes. |
| **Switch LLM Provider (e.g., Gemini to Claude/GPT)** | **Module 3 & 5** | Module 4 | `gvqm_junior_agent.py`, `gvqm_senior_agent.py` | Enforce identical JSON schemas (`winner`, `rationale`, `scratchpad`). Verify markdown sanitization in `clean_json_text()`. |
| **Alter Risk/Reward Balance Prompts** | **Module 3 & 5** | None | `gvqm_junior_prompts.py`, `gvqm_senior_prompts.py` | Preserve Dual-Layer notation directive to maintain beginner educational utility. |
| **Modify Trailing Stop or Take-Profit Logic** | **Module 4** | Module 6 | `gvqm_senior_paperwork_prompt.py`, `bot.py` | Ensure LLM returns numerical values for `stop_loss` and `take_profit` to prevent broker submission crashes. |
| **Adjust Portfolio Capacity or Swap Hurdle** | **Module 6** | None | `config.py`, `bot.py` (`execute_swaps`) | Ensure account cash balance supports expanded position counts. Keep `ELO_SWAP_THRESHOLD >= 10.0` to prevent over-trading. |
| **Broker Error Unmasking & ORDER_REJECTED Audit** | **Module 6** | Module 4 & 7 | `lib/gvqm_alpaca_trader.py`, `bot.py`, `lib/gvqm_senior_history.py` | Unmasks granular Alpaca error messages via `_extract_broker_error`, preserves dicts in `_enforce_contract`, wraps matrix info across 4 lines, logs `ORDER_REJECTED` to `Trade_Log`, and guarantees pipeline progression to Module 7. |
| **Redesign Email Layouts or Notification Channels** | **Module 7** | None | `gvqm_email_notifier.py` | Maintain HTML table structures and retain dictionary key mappings passed from `bot.py`. |

---

## 11. Testing & Validation Strategy

When making updates to database interactions, Google Sheets logic, or module synchronization, the standard validation procedure is:
1. **Target the Test Environment**: Ensure `.env` is configured with `GOOGLE_SHEET_NAME = "TradingBot_History_Test"`.
2. **Execute the Pipeline**: Run the pipeline locally (e.g., `python bot.py` or the specific module) to trigger the updates.
3. **Programmatic Verification**: Write and execute a Python verification script using `gspread` and the project's service account credentials (`google_credentials.json` or `.env`) to read directly from the `TradingBot_History_Test` sheet. Programmatically assert that the expected rows, columns, and values (e.g., Active_Contenders flags, Elo_Ratings) are correctly formatted and updated rather than relying solely on manual inspection.