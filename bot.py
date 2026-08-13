import sys, os
import datetime
import time
import random
import config

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

# ==========================================
# 📝 THE AI DIARY (For final email report)
# ==========================================
daily_ai_logic = []

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================
def log_pipeline(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [PIPELINE] {message}")

def get_live_portfolio():
    try:
        # Delegate the heavy lifting to the Trader script to find filled + pending tickers
        tickers, live_count, pending_count = trader.get_all_active_and_pending_tickers()
        
        log_pipeline(f"💼 Portfolio Context: {live_count} filled, {pending_count} pending buys.")
        return tickers
    except Exception as e:
        log_pipeline(f"⚠️ Failed to fetch portfolio context: {e}")
        return []

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

    try:
        # Call the helper to update 'Junior_Elo' tab flags to Y or N in Google Sheets
        junior_history.update_active_contenders_flag("Junior_Elo", distressed_tickers)
    except Exception as e:
        log_pipeline(f" ⚠️ Failed to update Junior Elo active contender flags: {e}")
    

    limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
    priority_tickers = junior_history.filter_candidates(distressed_tickers, limit=limit)
    
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
    portfolio_tickers = get_live_portfolio()
    
    if not portfolio_tickers:
        log_pipeline(" 💼 No active positions to maintain.")
        return

    # 1. Gather all current prices into a dictionary
    portfolio_data = {}
    for ticker in portfolio_tickers:
        price = trader.get_current_price(ticker)
        if price:
            portfolio_data[ticker] = price

    if not portfolio_data:
        log_pipeline(" ⚠️ Could not fetch current prices. Skipping maintenance.")
        return

    log_pipeline(f" 📦 Sending BATCH Analysis Request for {len(portfolio_data)} stocks...")
    
    # 2. ⚡ ONE SINGLE API CALL FOR EXTENDED PORTFOLIOS ⚡
    batch_trade_plans = senior_agent.generate_batch_execution_paperwork(portfolio_data)

    if not batch_trade_plans:
        log_pipeline(" ⚠️ Senior Agent failed to return batch paperwork.")
        return

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

# ==========================================
# 🏟️ PHASE 2: THE MAJOR LEAGUE (The Heavyweights)
# ==========================================
def run_major_league():
    log_pipeline("\n👨‍💼 PHASE 2: MAJOR LEAGUE (SENIOR ELO)")
    
    junior_board = minor_league.fetch_leaderboard("Junior_Elo")
    if not junior_board: return
    
    portfolio_tickers = get_live_portfolio()
    
    # INTEGRATED SENIOR DRAFT LIMIT
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
    
    # 1. THE CALL-UP: Promote top unowned Minor Leaguers
    sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
    unowned_juniors = [item[0] for item in sorted_juniors if item[0] not in portfolio_tickers]
    promoted_rookies = unowned_juniors[:draft_limit] 

    major_league_roster = list(set(portfolio_tickers + promoted_rookies))
    log_pipeline(f" 📈 Major League Roster: {major_league_roster}")

    if len(major_league_roster) < 2: return

    # EDGE CASE FIX: Fetch price ONCE per ticker to save API calls
    roster_data = []
    for t in major_league_roster:
        price = trader.get_current_price(t)
        if price:
            roster_data.append({'ticker': t, 'current_price': price})

    # 3. RUN HEAVYWEIGHT MATCHUPS (Title Defenses scale with portfolio size)
    matches_to_run = max(1, len(roster_data) // 2)
    
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

    # 👇  Update just the tickers that are today's active contenders (active contender flag) in the Senior Elo tab in Google sheet 👇

    try:
        # Call the helper to update 'Senior_Elo' tab flags to Y or N in Google Sheets
        junior_history.update_active_contenders_flag("Senior_Elo", major_league_roster)
    except Exception as e:
        log_pipeline(f" ⚠️ Failed to update Senior Elo active contender flags: {e}")

# ==========================================
# ⚙️ PHASE 3: THE FRONT OFFICE (Execution Engine)
# ==========================================
def execute_swaps():
    log_pipeline("\n⚖️ PHASE 3: FRONT OFFICE (ASSET ALLOCATION ENGINE)")
    
    senior_board = minor_league.fetch_leaderboard("Senior_Elo")
    if not senior_board: return
    
    ranked_majors = sorted(senior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
    portfolio_tickers = get_live_portfolio()

    # Read capital parameters and target limits securely from config
    max_portfolio_positions = getattr(config, 'MAX_PORTFOLIO_POSITIONS', 3)
    budget = getattr(config, 'INVEST_PER_TRADE', 1000)
    elo_swap_threshold = getattr(config, 'ELO_SWAP_THRESHOLD', 15.0)

    log_pipeline(f" 🎯 Portfolio Capacity Check: {len(portfolio_tickers)} / {max_portfolio_positions} slots filled.")

    # ---------------------------------------------------------
    # 🚀 SCENARIO A: THE FILL-UP PHASE (Open Slots Available)
    # ---------------------------------------------------------
    if len(portfolio_tickers) < max_portfolio_positions:
        open_slots = max_portfolio_positions - len(portfolio_tickers)
        log_pipeline(f" 🪟 Found {open_slots} open slot(s). Initiating Fill-Up Execution Phase...")
		
																			  
		
															 
        
        # Filter down to top-ranked assets that we do not currently own or have pending orders for
        unowned_majors = [item for item in ranked_majors if item[0] not in portfolio_tickers]
												
        
        if not unowned_majors:
            log_pipeline(" ⏸️ No unowned Major League assets available to fill open slots today.")
            return

        # Systematically purchase the top assets to fill the capacity vacuum
        slots_to_process = min(open_slots, len(unowned_majors))
        log_pipeline(f" 🛒 Deploying capital across the top {slots_to_process} unowned elite asset(s).")

        for i in range(slots_to_process):
            best_ticker, best_data = unowned_majors[i]
            log_pipeline(f" 📥 Slot {i+1}: Drafting {best_ticker} ({best_data['Elo_Rating']:.1f} Elo) into the portfolio.")
            
            current_price = trader.get_current_price(best_ticker)
            if not current_price:
                log_pipeline(f" ⚠️ Could not resolve price for {best_ticker}. Skipping slot.")
                continue

            # Run batch function for a single target allocation
            batch_plan = senior_agent.generate_batch_execution_paperwork({best_ticker: current_price})
            trade_plan = batch_plan.get(best_ticker)
            
            if trade_plan:
                trade_plan['ticker'] = best_ticker
                trade_plan['action'] = "OPEN_NEW"
                
                try:
                    # Execute entry sequence and verify acceptance with Alpaca
                    entry_status = trader.execute_entry(
                        ticker=best_ticker, 
                        investment_amount=budget,
                        buy_limit=trade_plan.get('entry_price'),
                        take_profit=trade_plan.get('take_profit'),
                        stop_loss=trade_plan.get('stop_loss')
                    )
                    
                    if entry_status and entry_status[0].get("event") not in ["ERROR", "HOLD"]:
                        payload = {"ceo_report": f"Slot Fill Purchase: {best_ticker}", "final_execution_orders": [trade_plan]}
                        senior_history.log_detailed_decisions(payload, {best_ticker: 0})
                        
                        reasoning = trade_plan.get('rationale', 'No rationale provided.')
                        daily_ai_logic.append(f"🚀 ALLOCATION FILL (Bought {best_ticker}): {reasoning}")
                    else:
                        log_pipeline(f" ❌ Allocation Fill aborted: Alpaca rejected order for {best_ticker}.")
                except Exception as e:
                    log_pipeline(f" ❌ Alpaca Entry Pipeline Failed for {best_ticker}: {e}")
            else:
                log_pipeline(f" ❌ Senior Agent failed paperwork generation for {best_ticker}.")
        
        # Safe exit after deploying capital into open slots to allow trades to settle
        return

    # ---------------------------------------------------------
    # ⚖️ SCENARIO B: THE SWAP PROTOCOL (Portfolio at Max Capacity)
    # ---------------------------------------------------------
    best_unowned = next((item for item in ranked_majors if item[0] not in portfolio_tickers), None)
    worst_owned = next((item for item in reversed(ranked_majors) if item[0] in portfolio_tickers), None)

    if not best_unowned or not worst_owned: 
        log_pipeline(" ⏸️ Portfolio at max capacity but data insufficient to evaluate swaps.")
        return

    best_ticker, best_data = best_unowned[0], best_unowned[1]
    worst_ticker, worst_data = worst_owned[0], worst_owned[1]

    log_pipeline(f" 🏆 Best Unowned: {best_ticker} ({best_data['Elo_Rating']:.1f} Elo)")
    log_pipeline(f" 🗑️ Worst Owned: {worst_ticker} ({worst_data['Elo_Rating']:.1f} Elo)")

								
																

    if best_data['Elo_Rating'] > (worst_data['Elo_Rating'] + elo_swap_threshold):
        log_pipeline(f" 🚨 SWAP TRIGGERED: {best_ticker} defeated {worst_ticker} by more than {elo_swap_threshold} pts!")
        
        current_loser_price = trader.get_current_price(worst_ticker)
        
        # 👇 WAIT & VERIFY LIQUIDATION SEQUENCING 👇
        close_status = trader.close_full_position(worst_ticker)
        
        if close_status == "FILLED":
            try:
                senior_history.log_mechanical_trade(worst_ticker, "CLOSE_POSITION", f"Replaced by {best_ticker}", current_loser_price, 1)
            except: 
                pass

            time.sleep(3) # Safe cooldown interval for broker cash clearing
            
            current_price = trader.get_current_price(best_ticker)
            
            # Request paperwork for the incoming outperforming asset
            batch_plan = senior_agent.generate_batch_execution_paperwork({best_ticker: current_price}) 
            trade_plan = batch_plan.get(best_ticker)
            
            if trade_plan:
                trade_plan['ticker'] = best_ticker
                trade_plan['action'] = "OPEN_NEW"

																  
                try:
                    # Fire entry order and lock verification contract
                    entry_status = trader.execute_entry(
                        ticker=best_ticker, 
                        investment_amount=budget,
                        buy_limit=trade_plan.get('entry_price'), 
                        take_profit=trade_plan.get('take_profit'),
                        stop_loss=trade_plan.get('stop_loss')
                    )
                    
                    if entry_status and entry_status[0].get("event") not in ["ERROR", "HOLD"]:
                        payload = {"ceo_report": f"Swap: {worst_ticker} -> {best_ticker}", "final_execution_orders": [trade_plan]}
                        senior_history.log_detailed_decisions(payload, {best_ticker: 0}) 

                        reasoning = trade_plan.get('rationale', 'No rationale provided.')
                        daily_ai_logic.append(f"🔄 SWAP ({worst_ticker} -> {best_ticker}): {reasoning}")
                    else:
                        log_pipeline(f" ❌ Swap incomplete: Alpaca liquidated {worst_ticker} but rejected buy order for {best_ticker}.")
                except Exception as e:
                    log_pipeline(f" ❌ Alpaca Trade Failed on Swap Entry: {e}")
            else:
                log_pipeline(f" ❌ Senior Agent failed to write paperwork for {best_ticker}. Capital preserved in cash.")
        else:
            log_pipeline(f" ❌ Swap Aborted: Failed to cleanly liquidate {worst_ticker}. Halting sequence to protect structure.")
    else:
        log_pipeline(f" 🛡️ Strategic equilibrium maintained. Challenger did not breach the +{elo_swap_threshold} margin.")

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
    maintain_portfolio()
    run_major_league()
    execute_swaps()

    # 2. Comprehensive Multi-Asset Reporting Strategy
    try:
        log_pipeline("\n📧 Dispatching Executive Brief...")
        
        portfolio_tickers = get_live_portfolio()
        senior_board = minor_league.fetch_leaderboard("Senior_Elo")
        
        draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
        
        junior_board = minor_league.fetch_leaderboard("Junior_Elo")
        sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
        unowned_juniors = [item[0] for item in sorted_juniors if item[0] not in portfolio_tickers]
        actual_promoted_rookies = unowned_juniors[:draft_limit] 

        # Gather complete standings for all active champions in the portfolio
        active_standings = []
        for t in portfolio_tickers:
            if t in senior_board:
                active_standings.append((t, senior_board[t]))
        
        # Gather standings for the current drafted pipeline challengers
        challenger_standings = []
        for t in actual_promoted_rookies:
            if t in senior_board:
                challenger_standings.append((t, senior_board[t]))
            else:
                challenger_standings.append((t, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0}))
        
        presentation_standings = active_standings + challenger_standings
        presentation_standings.sort(key=lambda x: x[1]['Elo_Rating'], reverse=True)
        
      
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
        sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1].get('Elo_Rating', 1500), reverse=True)

        # 3. Dispatch Both Emails
        log_pipeline("📧 Dispatching Major and Minor League Briefs...")
        notifier.send_minor_league_scouting_report(minor_league_notes, sorted_juniors)
        notifier.send_executive_brief(decision_payload, trader.get_account(), trader.get_portfolio())
        
        senior_history.log_strategy(decision_payload)
        log_pipeline("✅ Multi-asset corporate briefing emails successfully dispatched.")
        
    except Exception as e:
        log_pipeline(f"❌ Reporting Pipeline Failed: {e}")