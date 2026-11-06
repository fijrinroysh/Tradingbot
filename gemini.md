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
[ MODULE 6: FRONT OFFICE DECOUPLED ALLOCATION ENGINE ]
  -> Pass 1: Demotion Sells (Complete Demotions & Bottom 30% Major League)
  -> Cash Settlement Wait: Synchronous broker funds clearing
  -> Pass 2: Top-Tier Buys (Top 30% Major League Candidates)
  -> Granular Broker Rejection Unmasking & ORDER_REJECTED Audit Logging
          |
          v
[ MODULE 7: EXECUTIVE BRIEFING & MULTI-DAY MEMORY ]
  -> Historical Rank Extraction (A1 Cell JSON Storage)
  -> 3-to-7 Day Rank Momentum Calculation (Rising Stars / Momentum Movers)
  -> Multi-Asset HTML Briefing Dispatch (Resend API)
  -> Corporate Strategy Brief Logging
```

### System Operational Invariants
* **Cross-Platform UTF-8 Console Encoding:** All standalone entry points and library logging modules must defensively reconfigure `sys.stdout` and `sys.stderr` to `utf-8` on `win32` platforms (`sys.stdout.reconfigure(encoding='utf-8')`) to prevent `UnicodeEncodeError` when emitting emoji-enhanced pipeline status logs.

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
   * **The Exemption Clause:** Before synchronizing, the engine checks the top 10% (governed by `SENIOR_DRAFT_LIMIT = 0.10`) stocks on the `Junior_Elo` leaderboard. These elite stocks are explicitly exempted from being marked inactive. This ensures a stock that has fought its way to the top isn't prematurely disqualified from a Major League draft simply because its price organically rose just above the moving average threshold. It must lose matches and naturally fall out of the top tier before it can be disqualified by price alone.
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
* **SENIOR_DRAFT_LIMIT:** Dynamic sizing basis. Minor League scans candidates to target `ceil(len(active_contenders) * (SENIOR_DRAFT_LIMIT * 2))` matches, evaluating `2 * target_matches` candidates (e.g., 60 active contenders at 10% draft limit = 12 matches, 24 candidates scanned).
* **DAILY_SCAN_LIMIT:** Deprecated; commented out in `config.py` and `.env` in favor of dynamic scaling.
* **match_count:** Dynamic match ceiling: `floor(len(candidates_with_prices) / 2)`.
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

### Intraday Broker Stop-Loss vs. Trapdoor Guard Distinction
* **Trapdoor Liquidations (Module 4):** Triggered intentionally by the Senior LLM Agent during Phase 2.5 when an asset's fundamental thesis is broken. Banishes the asset from `Senior_Elo` (`Active_Contenders = 'N'`, Elo reset to 1500.0) and blocks re-buying for that session via `liquidated_today`.
* **Broker Stop-Loss Hits (Intraday OCO Bracket):** Triggered automatically by Alpaca during active trading hours while the bot is dormant. The broker liquidates the physical position. Upon the next bot run, the asset is simply unowned. If its distressed fundamentals remain favorable and it wins its scouting and Major League matchups, Module 6 evaluates it as a candidate for capital re-allocation unless an explicit cooldown is configured.

### Module Interface & Clean Boundary
* **Output:** Verified, clean portfolio state ready for allocation decisions; updated orders at broker; risk event audit trails in Google Sheets.
* **Decoupling Boundary:** Operates exclusively on *currently held* assets. Does not consider Minor League rookies.

---

## 6. Module 5: Major League Tournament Engine

```text
[Junior_Elo Leaderboard] --> [Filter Top Unowned Rookies] --> [Combine with Active Holdings]
                                                                    |
                                                                    v
                                                  [Unified Major League Roster]
                                                                    |
                                                                    v
                                                [Sort by Staleness (Last_Match Asc)]
                                                                    |
                                                                    v
                                     [Dynamic Match Sizing: ceil(N * MAJOR_LEAGUE_BUY_PCT)]
                                                                    |
                                                                    v
                                      [Extract Stalest Brawl Pool & Sort by Senior_Elo Desc]
                                                                    |
                                                                    v
                                                [Adjacent-Elo Ladder Matchmaking (1v2, 3v4)]
                                                                    |
                                                                    v
                                                 [Senior Agent Adjudication & Logging]
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
1. **The Rookie Call-Up (10% Dynamic Draft):**
   * Reads `Junior_Elo` leaderboard via `minor_league.fetch_leaderboard("Junior_Elo")`.
   * Sorts junior stocks by Elo descending.
   * Filters out stocks already held in `portfolio_tickers` and those in `liquidated_today`.
   * Extracts the top 10% of active junior contenders (`max(1, math.ceil(total_juniors * SENIOR_DRAFT_LIMIT))`). Owned portfolio holdings are **not** subtracted, ensuring a full 10% rookie class joins the Major League roster.
2. **Roster Unification:** `major_league_roster = list(set(portfolio_tickers + promoted_rookies))`
3. **Adjacent-Elo Ladder Pairing (`minor_league.get_major_league_matchups`):**
   * Eliminates artificial separation between Champions and Challengers; pools all roster contenders into a unified competition ladder.
   * **Dynamic Match Sizing:** Calculates `target_matches = ceil(len(roster) * MAJOR_LEAGUE_BUY_PCT)` with a physical ceiling of `len(roster) // 2` (e.g., 10 roster stocks at 30% buy = 3 matches evaluating 6 contenders).
   * **Staleness Priority Queue:** Contenders are sorted ascending by `Last_Match` (unfought contenders with `datetime.min` or oldest match timestamps placed first), breaking exact timestamp ties by higher active `Junior_Elo` (with missing active `Junior_Elo` rows treated as lowest priority, and full ties preserving Google Sheet row order).
   * **Adjacent-Elo Pairing:** The top `target_matches * 2` stalest contenders are extracted and sorted descending by `Senior_Elo` (with active `Junior_Elo` as secondary tie-breaker and Sheet row order on full ties), pairing adjacent elements (`Match 1: Rank 1 vs 2`, `Match 2: Rank 3 vs 4`, etc.). Emits a `⚖️ TIE-BREAK` pipeline log line whenever `Junior_Elo` resolves a tie.
   * **Zero-Holdings Resilience:** Operates seamlessly when portfolio is empty (e.g. at startup or after full cash liquidation); unowned contenders compete directly against each other.
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

## 7. Module 6: Front Office Decoupled Allocation Engine

```text
                              [Fetch Senior_Elo Leaderboard (N Contenders)]
                                                    |
                         +--------------------------+--------------------------+
                         |                                                     |
            [PASS 1: DEMOTION & BOTTOM SELLS]                        [PASS 2: TOP-TIER BUYS]
                         |                                                     |
        [Evaluate Current Portfolio Holdings]                   [Identify Ranks 1..ceil(N * 0.30)]
                         |                                                     |
       +-----------------+-----------------+                    [Filter: Unowned & Not Liquidated]
       |                                   |                                   |
[Not in Senior_Elo]              [Rank in Bottom 30%]            [Request Entry Paperwork via Senior Agent]
(Complete Demotion)               (Bottom Demotion)                            |
       |                                   |                         [trader.execute_entry()]
       +-----------------+-----------------+                                   |
                         |                                       +-------------+-------------+
            [trader.close_full_position()]                       |                           |
                         |                                   [SUCCESS]                   [REJECTED]
            [Log CLOSE_POSITION to Trade_Log]                    |                           |
                         |                             [Wait for Fill & Log]        [Unmask Broker Error]
         [Wait for Cash Settlement Cooldown]           (detailed_decisions)         [Log ORDER_REJECTED]
                         |                                       |                           |
                         +---------------------------------------+---------------------------+
                                                     |
                                                     v
                                   [Proceed to Module 7 Briefings]
```

### Core Responsibility
Governs capital deployment through an independent, decoupled two-pass architecture. Buys and sells operate autonomously: holdings are liquidated only upon complete Major League demotion or when dropping into the bottom 30% of the active Major League roster, while new capital is deployed exclusively to buy candidates in the top 30% of the Major League. Eliminates atomic swaps and artificial portfolio capacity caps, unmasks granular broker rejections, maintains an immutable failure audit trail in Google Sheets, and preserves pipeline continuity.

### Primary Source Files
* `bot.py` (Orchestration in `execute_swaps`)
* `gvqm_senior_agent.py`
* `lib/gvqm_senior_history.py`
* `lib/gvqm_alpaca_trader.py`

### Inputs & Configuration Parameters
* **SENIOR_DRAFT_LIMIT:** Decimal percentage of active Minor League candidates drafted into Major League (default: `0.10` = 10%).
* **MAJOR_LEAGUE_BUY_PCT:** Decimal percentage defining top-tier Major League buy eligibility (default: `0.30` = 30%).
* **MAJOR_LEAGUE_SELL_PCT:** Decimal percentage defining bottom-tier Major League liquidation threshold (default: `0.30` = 30%).
* **INVEST_PER_TRADE:** Dollar allocation per holding.
* **MAX_PORTFOLIO_POSITIONS & ELO_SWAP_THRESHOLD:** Deprecated; retained for backwards compatibility. Portfolio size is naturally governed by the top-tier buy rule.

### Execution Logic Flow

#### Leaderboard Ranking & Junior Elo Tie-Breaker (`minor_league.rank_senior_board`)
Active `Senior_Elo` contenders are ranked via a deterministic three-tier hierarchy:
1. **Primary:** `Senior_Elo` descending.
2. **Secondary (Tie-Breaker):** Active `Junior_Elo` descending (`junior_tiebreak_key`). Tickers with no active (`'Y'`) row in `Junior_Elo` are assigned lowest priority in a tie so active scouted contenders win boundary ties.
3. **Tertiary (Full Tie):** Existing Google Sheet row order preserved via Python's stable sort.
* **Audit Logging:** Whenever `Junior_Elo` resolves a `Senior_Elo` tie, the engine emits `⚖️ TIE-BREAK (Senior Elo ...)` to the pipeline log.

#### Pass 1: Demotion Sells (Holding Retention & Liquidation Gate)
1. **Holding Inspection:** Inspects all active positions via `portfolio_tickers = trader.get_live_portfolio()`.
   * **Major League Sovereignty:** Once an asset enters the portfolio, its retention or liquidation is governed strictly by Major League competition (Module 5 & 6). An owned stock is never demoted or sold based on Minor League standings or 250-day moving average price recovery. Liquidations occur strictly via Emergency Trapdoor exits (Module 4) or when the holding drops into the bottom 30% of the active Major League roster.
2. **Eligibility Audit:**
   * **Complete Demotion:** If an owned stock is not present in `Senior_Elo` (`Active_Contenders != 'Y'`), executes `trader.close_full_position(ticker)` with reason `"Major League Demotion"`.
   * **Bottom 30% Major League Demotion:** If an owned stock is in the bottom 30% of active Major League contenders (`rank > total_majors - ceil(total_majors * MAJOR_LEAGUE_SELL_PCT)`), executes `trader.close_full_position(ticker)` with reason `"Bottom 30% Major League Demotion"`.
   * **Holding Retention:** Stocks in the top 70% (top 30% or middle 40%) are maintained (`HOLD`).
3. **Cash Settlement Cooldown:** If any liquidations occurred, calls `trader.wait_for_cash_settlement(budget)` before proceeding.

#### Pass 2: Top-Tier Major League Buys (Candidate Entry Gate)
1. **Candidate Screening:** Identifies active Major League contenders ranked in the top 30% (`ranked_majors[:ceil(total_majors * MAJOR_LEAGUE_BUY_PCT)]`).
2. **Filtering:** Filters down to assets that are:
   * Not currently owned (`ticker not in portfolio_tickers`).
   * Not liquidated today via Trapdoor (`ticker not in liquidated_today`).
3. **Paperwork Request:** Obtains entry bracket limits via `senior_agent.generate_batch_execution_paperwork({ticker: current_price})`.
4. **Broker Entry Submission:** Submits bracket order via `trader.execute_entry(ticker, amount, buy_limit, take_profit, stop_loss)`.
5. **Outcome Evaluation & Audit Trail:**
   * **Success Branch:**
     * Submits bracket order to broker.
     * Invokes `trader.wait_for_position_fill()`: verifies against physical filled positions (`get_portfolio()`). If filled within timeout (30s), logs confirmation. If resting on the order book as an open limit order, logs resting status gracefully and proceeds without halting the pipeline.
     * Logs trade paperwork to `Trade_Log` via `senior_history.log_detailed_decisions()`.
     * Injects allocation thesis into `daily_ai_logic` and appends ticker to session portfolio context.
   * **Rejection / Exception Branch (Broker Error Unmasking):** If Alpaca rejects the order or an exception occurs:
     * Unmasks the exact broker rationale via `entry_status[0].get("info")` or pipeline exception.
     * Logs the specific broker rejection reason directly to stdout: `log_pipeline(f" ❌ Allocation Fill aborted: Alpaca rejected order for {best_ticker}. Reason: {error_reason}")`.
     * Records an audit row in Google Sheets `Trade_Log` via `senior_history.log_mechanical_trade(best_ticker, "ORDER_REJECTED", error_reason, current_price, 0)`.
     * Leaves capital preserved in cash and proceeds cleanly without crashing execution.

---

## 8. Module 7: Executive Briefing & Multi-Day Memory

```text
[Gather daily_ai_logic Logs] --> [Extract Historical Ranks from Sheet A1] --> [Compute 3-7 Day Momentum]
                                                                                      |
                                    +-------------------------------------------------+-------------------------------------------------+
                                    |                                                                                                   |
                  [Minor League Scouting Brief (Resend API)]                                                    [Major League Executive Brief (Resend API)]
                                    |                                                                                                   |
                    - Rising Stars Table (Top 3 Movers)                                                         - Executive Actions Taken
                    - Top 10% Draft Pool Standings (Rank, Ticker, Elo)                                          - Account Equity & Buying Power
                    - Dual-Layer Educational Match Breakdowns                                                   - Unrealized P/L by Active Holding
                                                                                                                - 5-Col Major Standings (Rank, Ticker, Elo, Status, Zone)
                                                                                                                - Major League Momentum Shifts (Top 3 Movers)
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
  * Minor League Rising Stars (Top 3 biggest rank improvements over 3-7 days via `Junior_Memory_Bank`).
  * Top 10% Minor League Heavyweights: Displays top `ceil(len(active_contenders) * SENIOR_DRAFT_LIMIT)` contenders with explicit `Rank`, `Ticker`, and `Elo Score`. Represents the rookie class drafted into Major League.
  * Dual-layer beginner educational battle breakdowns for all daily matchups.
* **Executive Brief (`send_executive_brief`):**
  * Immediate actions executed (Entries, Demotion Sells, Trapdoor Liquidations).
  * Account financial metrics (Equity, Cash %, Position P/L table including open resting limit orders tagged as `(Pending Buy)` with limit prices and `Order Open` status).
  * **Major League Standings Table (5 Columns & Ground-Truth Parity):**
    * **Ground-Truth Execution Parity:** The executive reporting engine binds `presentation_standings` directly to the `ranked_majors` roster returned by `execute_swaps()`. It does not re-draft unowned rookies post-trade, guaranteeing that the roster size, rankings, and Action Zone cutoffs (`BUY ZONE`, `HOLD`, `SELL ZONE`) presented in the email match broker trade execution with 100% fidelity.
    * Displays all $P$ portfolio holdings + all $R$ drafted unowned rookies ($P + R$ total).
    * `Rank`: Explicit numeric rank (`#1`, `#2`, `#3`... sorted by `Senior_Elo` descending, `Junior_Elo` tie-breaker, then Sheet row order; fallback path also uses `minor_league.rank_senior_board`).
    * `Ticker`: Equity symbol.
    * `Elo Rating`: Current Senior Elo score.
    * `Status`: Tripartite classification:
      - `🟢 Active` (held in portfolio): Light green background (`#e8f5e9`).
      - `🟢 Active (Pending)` (submitted limit buy order pending execution): Light green background (`#e8f5e9`).
      - `🟡 Challenger` (unowned rookie): Light yellow background (`#fffde7`).
    * `Action Zone`: Dynamically computed matching Module 6 Front Office rules:
      - Ranks 1 to `buy_count` (top $\lceil N \times \text{MAJOR\_LEAGUE\_BUY\_PCT} \rceil$): `🎯 BUY ZONE (Top 30%)`.
      - Ranks from `bottom_start_rank` to $N$: `🚨 SELL ZONE (Bot 30%)`.
      - Intermediate ranks: `⏸️ HOLD`.
  * Major League Momentum (Top 3 biggest rank improvements over 3-7 days via `Senior_Memory_Bank`).
  * Senior Agent portfolio diaries and matchup debate notes.

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