import sys, os
import math
import datetime
import time
import random
import config

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# Setup Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR) # Simplified pathing

# Imports
import lib.good_value_quick_money_market_scanner as scanner
import lib.gvqm_alpaca_trader as trader
import lib.gvqm_junior_agent as junior_agent
import lib.gvqm_junior_history as junior_history
import lib.gvqm_senior_agent as senior_agent
import lib.gvqm_senior_history as senior_history
import lib.gvqm_email_notifier as notifier
import lib.gvqm_minor_league as minor_league
from lib.gvqm_minor_league import rank_senior_board as _rank_senior_board
import lib.gvqm_league_common as league_common

# ==========================================
# 📝 THE AI DIARY (For final email report)
# ==========================================
daily_ai_logic = []

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================
def log_pipeline(message):
    timestamp = league_common.get_eastern_time_str("%H:%M:%S")
    print(f"[{timestamp}] [PIPELINE] {message}")

def _resolve_count(total: int, limit_or_pct: float) -> int:
    """
    Resolves a draft/buy/sell setting that can be either a decimal percentage
    (e.g., 0.10 for 10%, 0.30 for 30%) or a legacy integer count (e.g., 3).
    Always returns an integer >= 1 if total > 0, else 0.
    """
    if total <= 0:
        return 0
    if isinstance(limit_or_pct, float) and limit_or_pct <= 1.0:
        return max(1, math.ceil(total * limit_or_pct))
    return max(1, int(limit_or_pct))


# ==========================================
# ⚾ PHASE 1: THE MINOR LEAGUE (The Scout)
# ==========================================
def run_minor_league():
    log_pipeline("\n👶 PHASE 1: MINOR LEAGUE SCOUTING (JUNIOR ELO)")
    
    distressed_tickers = scanner.find_distressed_stocks()
    if not distressed_tickers:
        log_pipeline(" ⚠️ Scanner found zero distressed stocks today. Skipping Minor League.")
        return


# 👇  Update just the tickers that are today's active contenders to the active contender flag in the Junior Elo tab in Google sheet 👇

    active_and_protected = list(distressed_tickers)
    try:
        # 🛡️ THE EXEMPTION CLAUSE: Protect the Top 10% from premature disqualification
        junior_board = minor_league.fetch_leaderboard("Junior_Elo")
        if junior_board:
            # Sort by Elo descending to find the top tier
            sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1].get('Elo_Rating', 1500.0), reverse=True)
            draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 0.10)
            num_protected = _resolve_count(len(sorted_juniors), draft_limit)
            # Identify tickers that have earned the right to stay due to high Elo
            protected_tickers = [t[0] for t in sorted_juniors[:num_protected]]
            # Combine the distressed list with the protected list (removing duplicates)
            active_and_protected = list(set(distressed_tickers + protected_tickers))
        else:
            active_and_protected = distressed_tickers

        # Call the helper to update 'Junior_Elo' tab flags to Y or N in Google Sheets
        league_common.update_active_contenders_flag("Junior_Elo", active_and_protected, wipe_inactive_elo=True)
    except Exception as e:
        log_pipeline(f" ⚠️ Failed to update Junior Elo active contender flags: {e}")
    

    # Dynamic Minor League Scan Limit based on SENIOR_DRAFT_LIMIT * 2
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 0.10)
    match_pct = (draft_limit * 2) if isinstance(draft_limit, float) and draft_limit <= 1.0 else 0.20
    target_minor_matches = max(1, math.ceil(len(active_and_protected) * match_pct))
    candidates_to_scan = min(len(active_and_protected), target_minor_matches * 2)
    log_pipeline(f" 📊 Minor League Dynamic Scan: {len(active_and_protected)} contenders -> targeting {target_minor_matches} matches ({candidates_to_scan} candidates scanned)")
    priority_tickers = junior_history.filter_candidates(active_and_protected, limit=candidates_to_scan)
    
    # EDGE CASE FIX: Fetch price ONCE per ticker to save API rate limits
    candidates_with_prices = []
    for t in priority_tickers:
        price = trader.get_current_price(t)
        if price:
            candidates_with_prices.append({'ticker': t, 'current_price': price})
    
    if len(candidates_with_prices) < 2:
        log_pipeline(" ⚠️ Not enough candidates with valid prices. Skipping Minor League.")
        return
        
    # EDGE CASE FIX: Calculate matches based on ACTUAL survivors, not the abstract 'limit'
    matches_to_run = max(1, len(candidates_with_prices) // 2)
    
    # Matchmaking engine setup for Minor League
    matchups = minor_league.get_minor_league_matchups(candidates_with_prices, match_count=matches_to_run)
    
    if not matchups:
        log_pipeline(" ⚠️ Matchmaking engine returned no eligible fights today.")
        return
        
    log_pipeline(f" 🥊 Running {len(matchups)} Minor League Matchups...")

    for match in matchups:
        cand_a, cand_b = match[0], match[1]
        report = junior_agent.evaluate_matchup(cand_a, cand_b)
        
        if report and 'winner' in report:
            # Clean the text to prevent spacing/case errors
            winner = str(report['winner']).strip().upper()
            
            # 👇 SAFETY CHECK: Did the AI hallucinate a random ticker? 👇
            if winner not in [cand_a['ticker'], cand_b['ticker']]:
                log_pipeline(f" ⚠️ AI hallucinated winner '{winner}'. Skipping match.")
                continue 

            loser = cand_b['ticker'] if winner == cand_a['ticker'] else cand_a['ticker']
            
            log_pipeline(f" 🏆 {winner} defeated {loser}")
            minor_league.record_match_result("Junior_Elo", winner, loser)
            junior_history.log_report(winner, report, opponent=loser)
            
            reasoning = report.get('rationale', 'No rationale provided.')
            
            daily_ai_logic.append(f"🌱 SCOUT ({winner} vs {loser}): {reasoning}")

# ==========================================
# 🛡️ PHASE 2.5: PORTFOLIO MAINTENANCE (BATCHED)
# ==========================================
def maintain_portfolio():
    log_pipeline("\n🛡️ PHASE 2.5: PORTFOLIO MAINTENANCE")
    liquidated_today = set()
    
    portfolio_tickers = trader.get_live_portfolio()
    
    if not portfolio_tickers:
        log_pipeline(" 💼 No active positions to maintain.")
        return liquidated_today

    # 1. Gather all current prices into a dictionary
    portfolio_data = {}
    for ticker in portfolio_tickers:
        price = trader.get_current_price(ticker)
        if price:
            portfolio_data[ticker] = price

    if not portfolio_data:
        log_pipeline(" ⚠️ Could not fetch current prices. Skipping maintenance.")
        return liquidated_today

    log_pipeline(f" 📦 Sending BATCH Analysis Request for {len(portfolio_data)} stocks...")
    
    # 2. ⚡ ONE SINGLE API CALL FOR EXTENDED PORTFOLIOS ⚡
    batch_trade_plans = senior_agent.generate_batch_execution_paperwork(portfolio_data)

    if not batch_trade_plans:
        log_pipeline(" ⚠️ Senior Agent failed to return batch paperwork.")
        return liquidated_today

    # 3. Process the results efficiently across all active assets
    for ticker, current_price in portfolio_data.items():
        log_pipeline(f" 🔍 Auditing active holding: {ticker}")
        
        trade_plan = batch_trade_plans.get(ticker)
        
        if trade_plan:
            # 👇 THE TRAPDOOR EXIT 👇
            if trade_plan.get('action', '').upper() == "LIQUIDATE":
                log_pipeline(f" 🚨 TOXIC ASSET DETECTED: Senior Agent triggered Kill Switch for {ticker}!")
                
                # Verify Alpaca actually sold it before logging
                status = trader.close_full_position(ticker)
                
                if status == "FILLED":
                    liquidated_today.add(ticker)
                    league_common.banish_ticker(ticker)
                    
                    try:
                        reasoning = trade_plan.get('rationale', 'Catastrophic fundamental failure.')
                        senior_history.log_mechanical_trade(ticker, "EMERGENCY_EXIT", reasoning, current_price, 1)
                        daily_ai_logic.append(f"🚨 TRAPDOOR (Liquidated {ticker}): {reasoning}")
                    except Exception as e:
                        pass
                else:
                    log_pipeline(f" ❌ TRAPDOOR FAILED: Alpaca rejected liquidation for {ticker}.")
                continue # Move to next ticker

            # 👇 NORMAL MAINTENANCE (Stock is SAFE) 👇
            trade_plan['ticker'] = ticker

            log_pipeline(f" ✅ {ticker} is structurally safe. Updating trailing stops...")
            trader.execute_update(
                ticker=ticker, 
                take_profit=trade_plan.get('take_profit'), 
                stop_loss=trade_plan.get('stop_loss')
            )
            
            try:
                payload = {"ceo_report": f"Maintained {ticker}", "final_execution_orders": [trade_plan]}
                senior_history.log_detailed_decisions(payload, {ticker: 1})
                
                reasoning = trade_plan.get('rationale', 'No rationale provided.')
                daily_ai_logic.append(f"💼 PORTFOLIO ({ticker}): {reasoning}")
            except Exception as e:
                log_pipeline(f" ⚠️ Failed to log maintenance to sheets: {e}")
        else:
            log_pipeline(f" ⚠️ Senior Agent failed to return paperwork for {ticker} in the batch response.")

    return liquidated_today

# ==========================================
# 🏟️ PHASE 2: THE MAJOR LEAGUE (The Heavyweights)
# ==========================================
def run_major_league(liquidated_today=None):
    if liquidated_today is None: liquidated_today = set()
    log_pipeline("\n👨‍💼 PHASE 2: MAJOR LEAGUE (SENIOR ELO)")
    
    junior_board = minor_league.fetch_leaderboard("Junior_Elo")
    if not junior_board: return
    
    portfolio_tickers = trader.get_live_portfolio()
    
    # INTEGRATED SENIOR DRAFT LIMIT (Top 10% of active Minor League candidates)
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 0.10)
    
    # 1. THE CALL-UP: Promote top 10% unowned Minor Leaguers directly
    sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
    unowned_juniors = [item[0] for item in sorted_juniors if item[0] not in portfolio_tickers and item[0] not in liquidated_today]
    
    rookie_count = _resolve_count(len(junior_board), draft_limit)
    promoted_rookies = unowned_juniors[:rookie_count] 

    major_league_roster = list(set(portfolio_tickers + promoted_rookies))
    log_pipeline(f" 📈 Major League Roster: {major_league_roster}")

    if len(major_league_roster) < 2: return

    # 👇 2. SYNC SENIOR ELO CONTENDERS & AUTO-REGISTER BEFORE MATCHMAKING 👇
    try:
        league_common.update_active_contenders_flag("Senior_Elo", major_league_roster, wipe_inactive_elo=True)
    except Exception as e:
        log_pipeline(f" ⚠️ Failed to update Senior Elo active contender flags: {e}")

    # EDGE CASE FIX: Fetch price ONCE per ticker to save API calls
    roster_data = []
    for t in major_league_roster:
        price = trader.get_current_price(t)
        if price:
            roster_data.append({'ticker': t, 'current_price': price})

    # 3. RUN HEAVYWEIGHT MATCHUPS (Dynamically scaled by MAJOR_LEAGUE_BUY_PCT)
    buy_pct = getattr(config, 'MAJOR_LEAGUE_BUY_PCT', 0.30)
    target_matches = _resolve_count(len(roster_data), buy_pct)
    matches_to_run = min(len(roster_data) // 2, max(1, target_matches))
    log_pipeline(f" 🥊 Major League Dynamic Matches: {len(roster_data)} contenders -> running {matches_to_run} matches")
    
    matchups = minor_league.get_major_league_matchups(
        candidates=roster_data, 
        owned_tickers=portfolio_tickers, 
        match_count=matches_to_run
    )
    
    if not matchups:
        log_pipeline(" 🛡️ No valid Major League matchups generated (e.g. waiting on challengers).")
        return
    
    log_pipeline(f" 🥊 Running {len(matchups)} Major League Matchups...")
    
    for match in matchups:
        cand_a, cand_b = match[0], match[1]
        report = senior_agent.evaluate_matchup(cand_a, cand_b) 

        if report and 'winner' in report:
            winner = str(report['winner']).strip().upper()
            
            if winner not in [cand_a['ticker'], cand_b['ticker']]:
                log_pipeline(f" ⚠️ AI hallucinated winner '{winner}'. Skipping match.")
                continue 

            loser = cand_b['ticker'] if winner == cand_a['ticker'] else cand_a['ticker']
            minor_league.record_match_result("Senior_Elo", winner, loser)
            
            reasoning = report.get('rationale', 'No rationale provided.')
            daily_ai_logic.append(f"🥊 MATCHUP ({cand_a['ticker']} vs {cand_b['ticker']}): Selected {winner}. {reasoning}")
            
            try:
                senior_history.log_matchup(cand_a['ticker'], cand_b['ticker'], winner, reasoning)
            except Exception as e:
                log_pipeline(f" ⚠️ Failed to log matchup rationale: {e}")

    # Contender flags already synchronized prior to matchmaking.

# ==========================================
# ⚙️ PHASE 3: THE FRONT OFFICE (Execution Engine)
# ==========================================
def execute_swaps(liquidated_today=None):
    if liquidated_today is None: liquidated_today = set()
    log_pipeline("\n⚖️ PHASE 3: FRONT OFFICE (ASSET ALLOCATION ENGINE)")
    
    senior_board = minor_league.fetch_leaderboard("Senior_Elo")
    if not senior_board:
        log_pipeline(" ⏸️ Senior_Elo leaderboard is empty. Skipping Front Office execution.")
        return []
    
    junior_board = minor_league.fetch_leaderboard("Junior_Elo")
    ranked_majors = _rank_senior_board(senior_board, junior_board if isinstance(junior_board, dict) else {})
    total_majors = len(ranked_majors)
    portfolio_tickers = trader.get_live_portfolio()

    # Read capital parameters and allocation percentages
    budget = getattr(config, 'INVEST_PER_TRADE', 1000)
    major_buy_pct = getattr(config, 'MAJOR_LEAGUE_BUY_PCT', 0.30)
    major_sell_pct = getattr(config, 'MAJOR_LEAGUE_SELL_PCT', 0.30)

    buy_count = _resolve_count(total_majors, major_buy_pct)
    sell_count = _resolve_count(total_majors, major_sell_pct)
    # Ensure bottom cutoff does not overlap with top buy zone when total_majors is small
    bottom_start_idx = max(buy_count, total_majors - sell_count)
    bottom_majors = {item[0] for item in ranked_majors[bottom_start_idx:]}

    log_pipeline(f" 📊 Major League Roster: {total_majors} active contenders.")
    log_pipeline(f" 🎯 Allocation Targets: Top {buy_count} eligible to BUY (Top {int(major_buy_pct*100)}%), Bottom {len(bottom_majors)} flagged to SELL (Bottom {int(major_sell_pct*100)}%).")
    log_pipeline(f" 💼 Current Portfolio: {len(portfolio_tickers)} positions: {portfolio_tickers}")

    # ---------------------------------------------------------
    # 📉 PASS 1: SELLS (Demotions & Bottom 30% Major League)
    # ---------------------------------------------------------
    log_pipeline("\n🔍 Pass 1: Auditing Holdings for Demotion or Bottom Tier...")
    any_liquidations = False

    for held_ticker in list(portfolio_tickers):
        # 1. Complete Demotion: Stock is no longer an active contender in Senior_Elo
        if held_ticker not in senior_board:
            log_pipeline(f" 🚨 DEMOTION DETECTED: {held_ticker} is no longer in Senior_Elo. Liquidating...")
            current_price = trader.get_current_price(held_ticker)
            close_status = trader.close_full_position(held_ticker)
            if close_status == "FILLED":
                any_liquidations = True
                try:
                    senior_history.log_mechanical_trade(held_ticker, "CLOSE_POSITION", "Major League Demotion", current_price or 0.0, 1)
                except Exception as log_err:
                    log_pipeline(f" ⚠️ Failed to log demotion trade for {held_ticker}: {log_err}")
                daily_ai_logic.append(f"📉 DEMOTION EXIT: Sold {held_ticker} because it dropped out of the Major League.")
            else:
                log_pipeline(f" ❌ Failed to liquidate demoted asset {held_ticker}.")

        # 2. Bottom 30% Major League: Stock is in the active Major League but fell to bottom tier
        elif held_ticker in bottom_majors:
            held_elo = senior_board[held_ticker].get('Elo_Rating', 1500.0)
            held_rank = next((idx + 1 for idx, item in enumerate(ranked_majors) if item[0] == held_ticker), total_majors)
            log_pipeline(f" 🚨 BOTTOM TIER DETECTED: {held_ticker} (Rank {held_rank}/{total_majors}, {held_elo:.1f} Elo) is in bottom {int(major_sell_pct*100)}%. Liquidating...")
            current_price = trader.get_current_price(held_ticker)
            close_status = trader.close_full_position(held_ticker)
            if close_status == "FILLED":
                any_liquidations = True
                try:
                    senior_history.log_mechanical_trade(held_ticker, "CLOSE_POSITION", "Bottom 30% Major League Demotion", current_price or 0.0, 1)
                except Exception as log_err:
                    log_pipeline(f" ⚠️ Failed to log bottom tier trade for {held_ticker}: {log_err}")
                daily_ai_logic.append(f"📉 BOTTOM TIER EXIT: Sold {held_ticker} (Rank {held_rank}/{total_majors}) in bottom {int(major_sell_pct*100)}% of Major League.")
            else:
                log_pipeline(f" ❌ Failed to liquidate bottom tier asset {held_ticker}.")

        else:
            held_elo = senior_board[held_ticker].get('Elo_Rating', 1500.0)
            held_rank = next((idx + 1 for idx, item in enumerate(ranked_majors) if item[0] == held_ticker), total_majors)
            log_pipeline(f" ✅ HOLD: {held_ticker} (Rank {held_rank}/{total_majors}, {held_elo:.1f} Elo) maintained in Major League.")

    # If any sales were executed, wait for cash settlement before proceeding to buys
    if any_liquidations:
        log_pipeline(" ⏳ Waiting for cash settlement from liquidations before initiating buys...")
        trader.wait_for_cash_settlement(budget)

    # Refresh live portfolio after liquidations
    portfolio_tickers = trader.get_live_portfolio()

    # ---------------------------------------------------------
    # 🚀 PASS 2: BUYS (Top 30% Major League)
    # ---------------------------------------------------------
    log_pipeline("\n🛒 Pass 2: Evaluating Top-Tier Major League Buys...")
    eligible_candidates = [
        item for item in ranked_majors[:buy_count]
        if item[0] not in portfolio_tickers and item[0] not in liquidated_today
    ]

    if not eligible_candidates:
        log_pipeline(" ⏸️ No unowned, non-liquidated candidates in the top tier to buy today.")
        return ranked_majors

    log_pipeline(f" 🎯 Found {len(eligible_candidates)} qualifying unowned candidate(s) in top {buy_count} ranks.")

    for best_ticker, best_data in eligible_candidates:
        rank = next((idx + 1 for idx, item in enumerate(ranked_majors) if item[0] == best_ticker), 1)
        log_pipeline(f" 📥 Candidate {best_ticker} (Rank {rank}/{total_majors}, {best_data['Elo_Rating']:.1f} Elo): Generating paperwork...")

        current_price = trader.get_current_price(best_ticker)
        if not current_price:
            log_pipeline(f" ⚠️ Could not resolve price for {best_ticker}. Skipping.")
            continue

        batch_plan = senior_agent.generate_batch_execution_paperwork({best_ticker: current_price})
        trade_plan = batch_plan.get(best_ticker) if batch_plan else None

        if trade_plan:
            trade_plan['ticker'] = best_ticker
            trade_plan['action'] = "OPEN_NEW"

            try:
                entry_status = trader.execute_entry(
                    ticker=best_ticker,
                    investment_amount=budget,
                    buy_limit=trade_plan.get('entry_price'),
                    take_profit=trade_plan.get('take_profit'),
                    stop_loss=trade_plan.get('stop_loss')
                )

                if entry_status and entry_status[0].get("event") not in ["ERROR", "HOLD"]:
                    trader.wait_for_position_fill(best_ticker)
                    payload = {"ceo_report": f"Top-Tier Purchase: {best_ticker}", "final_execution_orders": [trade_plan]}
                    senior_history.log_detailed_decisions(payload, {best_ticker: 0})

                    reasoning = trade_plan.get('rationale', 'No rationale provided.')
                    daily_ai_logic.append(f"🚀 TOP-TIER ALLOCATION (Bought {best_ticker}): {reasoning}")
                    portfolio_tickers.append(best_ticker)
                else:
                    error_reason = entry_status[0].get("info", "Unknown broker rejection") if entry_status else "No status returned"
                    log_pipeline(f" ❌ Allocation Fill aborted: Alpaca rejected order for {best_ticker}. Reason: {error_reason}")
                    try:
                        senior_history.log_mechanical_trade(best_ticker, "ORDER_REJECTED", error_reason, current_price, 0)
                    except Exception as log_err:
                        log_pipeline(f" ⚠️ Failed to log ORDER_REJECTED to Trade_Log: {log_err}")
            except Exception as e:
                log_pipeline(f" ❌ Alpaca Entry Pipeline Failed for {best_ticker}: {e}")
                try:
                    senior_history.log_mechanical_trade(best_ticker, "ORDER_REJECTED", f"Pipeline Exception: {e}", current_price, 0)
                except Exception as log_err:
                    log_pipeline(f" ⚠️ Failed to log ORDER_REJECTED to Trade_Log: {log_err}")
        else:
            log_pipeline(f" ❌ Senior Agent failed paperwork generation for {best_ticker}.")

    return ranked_majors

# ==========================================
# 🚀 GITHUB ACTIONS ENTRY POINT
# ==========================================
if __name__ == "__main__":
    log_pipeline("🚀 STARTING DAILY TRADING PIPELINE")
    
    if not trader.is_market_open() and not getattr(config, 'DEBUG_MODE', False):
        log_pipeline("💤 Market Closed. Exiting execution run gracefully.")
        sys.exit(0)

    # 1. Pipeline Execution Sequences
    run_minor_league()
    liquidated_today = maintain_portfolio()
    run_major_league(liquidated_today)
    ranked_majors = execute_swaps(liquidated_today)

    # 2. Comprehensive Multi-Asset Reporting Strategy
    try:
        log_pipeline("\n📧 Dispatching Executive Brief...")
        
        # Ground-Truth Parity: Present the exact Major League roster evaluated during execute_swaps()
        if not ranked_majors:
            senior_board = minor_league.fetch_leaderboard("Senior_Elo")
            if senior_board:
                junior_board = minor_league.fetch_leaderboard("Junior_Elo")
                ranked_majors = _rank_senior_board(senior_board, junior_board if isinstance(junior_board, dict) else {})
            else:
                ranked_majors = []
        
        presentation_standings = ranked_majors
      
        # ==========================================
        # 📧 THE CLEAN SPLIT: EMAIL DISPATCH
        # ==========================================
        
        # 1. Gather Major League Data (Actions + Senior Matchups)
        actions_taken = [log for log in daily_ai_logic if "SWAP" in log or "PORTFOLIO" in log or "ALLOCATION" in log or "TRAPDOOR" in log]
        action_text = "\n".join(actions_taken) if actions_taken else "No structural portfolio allocation shifts executed today."
        
        major_league_notes = [log for log in daily_ai_logic if "MATCHUP" in log]
        major_notes_text = "\n".join(major_league_notes) if major_league_notes else "No Major League title defenses today."
        
        decision_payload = {
            "immediate_actions": action_text,
            "ceo_report": major_notes_text, # Purely Major League logic
            "major_league_standings": presentation_standings
        }

        # 2. Gather Minor League Data (Scouting Matches + Sorted Leaderboard)
        minor_league_notes = [log for log in daily_ai_logic if "SCOUT" in log]
        
        # Convert the junior_board dictionary into the sorted list format the email expects
        junior_board = minor_league.fetch_leaderboard("Junior_Elo")
        sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1].get('Elo_Rating', 1500.0), reverse=True) if junior_board else []

        # Fetch full Junior leaderboard (including inactive contenders) for accurate cross-league perspective in Executive Brief
        junior_board_full = minor_league.fetch_leaderboard("Junior_Elo", active_only=False)
        decision_payload["junior_board"] = junior_board_full

        # 3. Dispatch Both Emails
        log_pipeline("📧 Dispatching Major and Minor League Briefs...")
        notifier.send_minor_league_scouting_report(minor_league_notes, sorted_juniors)
        pending_buys = trader.get_pending_buy_orders()
        notifier.send_executive_brief(decision_payload, trader.get_account(), trader.get_portfolio(), pending_orders=pending_buys, junior_board=junior_board_full)
        
        senior_history.log_strategy(decision_payload)
        log_pipeline("✅ Multi-asset corporate briefing emails successfully dispatched.")
        
    except Exception as e:
        log_pipeline(f"❌ Reporting Pipeline Failed: {e}")