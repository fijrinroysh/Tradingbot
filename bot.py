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
        positions = trader.trading_client.get_all_positions()
        live_tickers = [p.symbol for p in positions]
        log_pipeline(f"💼 Portfolio Context: {len(live_tickers)} active positions.")
        return live_tickers
    except Exception as e:
        log_pipeline(f"⚠️ Failed to fetch portfolio: {e}")
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
    
    # 👇 NEW FUNCTION CALL 👇
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
                log_pipeline(f"   ⚠️ AI hallucinated winner '{winner}'. Skipping match.")
                continue 

            loser = cand_b['ticker'] if winner == cand_a['ticker'] else cand_a['ticker']
            
            log_pipeline(f"   🏆 {winner} defeated {loser}")
            minor_league.record_match_result("Junior_Elo", winner, loser)
            junior_history.log_report(winner, report, opponent=loser)
            
            reasoning = report.get('rationale', 'No rationale provided.')
            daily_ai_logic.append(f"🌱 SCOUT ({winner} vs {loser}): {reasoning[:200]}...")

# ==========================================
# 🛡️ PHASE 2.5: PORTFOLIO MAINTENANCE
# ==========================================
def maintain_portfolio():
    log_pipeline("\n🛡️ PHASE 2.5: PORTFOLIO MAINTENANCE")
    portfolio_tickers = get_live_portfolio()
    
    if not portfolio_tickers:
        log_pipeline(" 💼 No active positions to maintain.")
        return

    for ticker in portfolio_tickers:
        current_price = trader.get_current_price(ticker)
        log_pipeline(f"   🔍 Auditing active holding: {ticker}")
        
        # 1 API Call does the fundamental physical AND the technical paperwork!
        trade_plan = senior_agent.generate_execution_paperwork(ticker, current_price)
        
        if trade_plan:
            # 👇 THE TRAPDOOR EXIT 👇
            # CHANGED: Now looking at 'action' instead of 'portfolio_status'
            if trade_plan.get('action', '').upper() == "LIQUIDATE":
                log_pipeline(f"   🚨 TOXIC ASSET DETECTED: Senior Agent triggered Kill Switch for {ticker}!")
                trader.close_full_position(ticker)
                
                try:
                    reasoning = trade_plan.get('rationale', 'Catastrophic fundamental failure.')
                    senior_history.log_mechanical_trade(ticker, "EMERGENCY_EXIT", reasoning, current_price, 1)
                    daily_ai_logic.append(f"🚨 TRAPDOOR (Liquidated {ticker}): {reasoning}")
                except Exception as e:
                    pass
                continue # Skip the rest of the loop, stock is sold! Move to next ticker.

            # 👇 NORMAL MAINTENANCE (Stock is SAFE) 👇
            trade_plan['ticker'] = ticker
            
            # REMOVED: trade_plan['action'] = "UPDATE_EXISTING" (The AI already did this!)

            log_pipeline(f"   ✅ {ticker} is structurally safe. Updating trailing stops...")
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
                log_pipeline(f"   ⚠️ Failed to log maintenance to sheets: {e}")
        else:
            log_pipeline(f"   ⚠️ Senior Agent failed to return paperwork for {ticker}.")

# ==========================================
# 🏟️ PHASE 2: THE MAJOR LEAGUE (The Heavyweights)
# ==========================================
def run_major_league():
    log_pipeline("\n👨‍💼 PHASE 2: MAJOR LEAGUE (SENIOR ELO)")
    
    junior_board = minor_league.fetch_leaderboard("Junior_Elo")
    if not junior_board: return
        
    portfolio_tickers = get_live_portfolio()
    
    # 1. THE CALL-UP: Promote top 3 unowned Minor Leaguers
    sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
    unowned_juniors = [item[0] for item in sorted_juniors if item[0] not in portfolio_tickers]
    promoted_rookies = unowned_juniors[:3]
    
    major_league_roster = list(set(portfolio_tickers + promoted_rookies))
    log_pipeline(f" 📈 Major League Roster: {major_league_roster}")

    if len(major_league_roster) < 2: return

    # EDGE CASE FIX: Fetch price ONCE per ticker to save API calls
    roster_data = []
    for t in major_league_roster:
        price = trader.get_current_price(t)
        if price:
            roster_data.append({'ticker': t, 'current_price': price})

    # 3. RUN HEAVYWEIGHT MATCHUPS
    matches_to_run = max(1, len(roster_data) // 2)
    
    # 👇 NEW FUNCTION CALL (With Title Defense logic) 👇
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
            # Clean the text to prevent spacing/case errors
            winner = str(report['winner']).strip().upper()
            
            # 👇 SAFETY CHECK: Did the AI hallucinate a random ticker? 👇
            if winner not in [cand_a['ticker'], cand_b['ticker']]:
                log_pipeline(f"   ⚠️ AI hallucinated winner '{winner}'. Skipping match.")
                continue 

            loser = cand_b['ticker'] if winner == cand_a['ticker'] else cand_a['ticker']
            minor_league.record_match_result("Senior_Elo", winner, loser)
            
            reasoning = report.get('rationale', 'No rationale provided.')
            daily_ai_logic.append(f"🥊 MATCHUP ({cand_a['ticker']} vs {cand_b['ticker']}): Selected {winner}. {reasoning}")
            
            try:
                senior_history.log_matchup(cand_a['ticker'], cand_b['ticker'], winner, reasoning)
            except Exception as e:
                log_pipeline(f"   ⚠️ Failed to log matchup rationale: {e}")

# ==========================================
# ⚙️ PHASE 3: THE FRONT OFFICE (Execution)
# ==========================================
def execute_swaps():
    log_pipeline("\n⚖️ PHASE 3: FRONT OFFICE (SWAP EXECUTION)")
    
    senior_board = minor_league.fetch_leaderboard("Senior_Elo")
    if not senior_board: return
    
    ranked_majors = sorted(senior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
    portfolio_tickers = get_live_portfolio()

    # ---------------------------------------------------------
    # 🚀 SCENARIO A: THE COLD START (Portfolio is empty)
    # ---------------------------------------------------------
    if not portfolio_tickers:
        log_pipeline(" 💼 Portfolio is empty. Initiating Cold Start...")
        if not ranked_majors: return
        
        best_ticker, best_data = ranked_majors[0] # Grab the absolute #1 stock
        
        current_price = trader.get_current_price(best_ticker)
        trade_plan = senior_agent.generate_execution_paperwork(best_ticker, current_price)
        
        if trade_plan:
            trade_plan['ticker'] = best_ticker
            trade_plan['action'] = "OPEN_NEW"
            budget = getattr(config, 'INVEST_PER_TRADE', 1000)
            
            try:
                trader.execute_entry(
                    ticker=best_ticker, investment_amount=budget,
                    buy_limit=trade_plan.get('entry_price'),
                    take_profit=trade_plan.get('take_profit'),
                    stop_loss=trade_plan.get('stop_loss')
                )
                payload = {"ceo_report": f"Initial Purchase: {best_ticker}", "final_execution_orders": [trade_plan]}
                senior_history.log_detailed_decisions(payload, {best_ticker: 0})
                
                reasoning = trade_plan.get('rationale', 'No rationale provided.')
                daily_ai_logic.append(f"🚀 COLD START (Bought {best_ticker}): {reasoning}")
            except Exception as e:
                log_pipeline(f"   ❌ Alpaca Trade Failed: {e}")
        else:
            log_pipeline(f"   ❌ Senior Agent failed paperwork for {best_ticker}.")
        return # Exit after cold start

    # ---------------------------------------------------------
    # ⚖️ SCENARIO B: THE SWAP (Portfolio has assets)
    # ---------------------------------------------------------
    best_unowned = next((item for item in ranked_majors if item[0] not in portfolio_tickers), None)
    worst_owned = next((item for item in reversed(ranked_majors) if item[0] in portfolio_tickers), None)

    if not best_unowned or not worst_owned: 
        log_pipeline(" ⏸️ Not enough data to process a swap today.")
        return

    best_ticker, best_data = best_unowned[0], best_unowned[1]
    worst_ticker, worst_data = worst_owned[0], worst_owned[1]

    log_pipeline(f" 🏆 Best Unowned: {best_ticker} ({best_data['Elo_Rating']:.1f} Elo)")
    log_pipeline(f" 🗑️ Worst Owned: {worst_ticker} ({worst_data['Elo_Rating']:.1f} Elo)")

    # 👇 THE FRICTION TAX 👇
    ELO_THRESHOLD = getattr(config, 'ELO_SWAP_THRESHOLD', 15.0) 

    if best_data['Elo_Rating'] > (worst_data['Elo_Rating'] + ELO_THRESHOLD):
        log_pipeline(f" 🚨 SWAP TRIGGERED: {best_ticker} defeated {worst_ticker} by more than {ELO_THRESHOLD} pts!")
        
        current_loser_price = trader.get_current_price(worst_ticker)
        trader.close_full_position(worst_ticker)
        
        try:
            senior_history.log_mechanical_trade(worst_ticker, "CLOSE_POSITION", f"Replaced by {best_ticker}", current_loser_price, 1)
        except: pass

        time.sleep(3) 
        
        current_price = trader.get_current_price(best_ticker)
        trade_plan = senior_agent.generate_execution_paperwork(best_ticker, current_price) 
        
        if trade_plan:
            # 👇 INJECT STANDARDIZED DATA FOR THE LOGGER 👇
            trade_plan['ticker'] = best_ticker
            trade_plan['action'] = "OPEN_NEW"

            budget = getattr(config, 'INVEST_PER_TRADE', 1000)
            try:
                trader.execute_entry(
                    ticker=best_ticker, investment_amount=budget,
                    buy_limit=trade_plan.get('entry_price'), 
                    take_profit=trade_plan.get('take_profit'),
                    stop_loss=trade_plan.get('stop_loss')
                )
                
                payload = {"ceo_report": f"Swap: {worst_ticker} -> {best_ticker}", "final_execution_orders": [trade_plan]}
                senior_history.log_detailed_decisions(payload, {best_ticker: 0}) 
                
                reasoning = trade_plan.get('rationale', 'No rationale provided.')
                daily_ai_logic.append(f"🔄 SWAP ({worst_ticker} -> {best_ticker}): {reasoning}")
            except Exception as e:
                log_pipeline(f"   ❌ Alpaca Trade Failed: {e}")
        else:
            log_pipeline(f"   ❌ Senior Agent failed to write paperwork for {best_ticker}. Cash held.")
    else:
        log_pipeline(f" 🛡️ No swap. Challenger did not beat the +{ELO_THRESHOLD} pt margin of victory.")

# ==========================================
# 🚀 GITHUB ACTIONS ENTRY POINT
# ==========================================
if __name__ == "__main__":
    log_pipeline("🚀 STARTING DAILY TRADING PIPELINE")
    
    if not trader.is_market_open() and not getattr(config, 'DEBUG_MODE', False):
        log_pipeline("💤 Market Closed. Exiting.")
        sys.exit(0)

    # 1. Operations
    run_minor_league()
    maintain_portfolio()
    run_major_league()
    execute_swaps()

    # 2. Reporting
    try:
        log_pipeline("\n📧 Dispatching Executive Brief...")
        
        portfolio_tickers = get_live_portfolio()
        senior_board = minor_league.fetch_leaderboard("Senior_Elo")
        
        # 👇 1. DYNAMICALLY PULL *TODAY'S* ROOKIES FROM JUNIOR BOARD 👇
        junior_board = minor_league.fetch_leaderboard("Junior_Elo")
        sorted_juniors = sorted(junior_board.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
        unowned_juniors = [item[0] for item in sorted_juniors if item[0] not in portfolio_tickers]
        actual_promoted_rookies = unowned_juniors[:3]
        
        # 👇 2. BUILD THE ACTIVE ROSTER STANDINGS 👇
        active_standings = []
        for t in portfolio_tickers:
            if t in senior_board:
                active_standings.append((t, senior_board[t]))
                
        # 👇 3. BUILD THE CHALLENGER STANDINGS (Syncing the scores) 👇
        challenger_standings = []
        for t in actual_promoted_rookies:
            if t in senior_board:
                challenger_standings.append((t, senior_board[t]))
            else:
                # If they are brand new and haven't fought yet, give them a clean slate score!
                challenger_standings.append((t, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0}))
        
        # Combine and re-sort them so they display in proper Elo order
        presentation_standings = active_standings + challenger_standings
        presentation_standings.sort(key=lambda x: x[1]['Elo_Rating'], reverse=True)
        
        # 👇 4. SEPARATE ACTIONS FROM SCOUTING NOTES 👇
        actions_taken = [log for log in daily_ai_logic if "SWAP" in log or "PORTFOLIO" in log or "COLD START" in log or "TRAPDOOR" in log]
        scout_notes = [log for log in daily_ai_logic if "SCOUT" in log or "MATCHUP" in log]
        
        action_text = "\n".join(actions_taken) if actions_taken else "No immediate portfolio changes required today."
        notes_text = "\n".join(scout_notes) if scout_notes else "Routine market conditions."
        
        # Build the new categorized payload
        decision_payload = {
            "immediate_actions": action_text,
            "ceo_report": notes_text, 
            "major_league_standings": presentation_standings
        }
        
        senior_history.log_strategy(decision_payload)
        notifier.send_executive_brief(decision_payload, trader.get_account(), trader.get_portfolio())
        log_pipeline("✅ Email dispatched.")
    except Exception as e:
        log_pipeline(f"❌ Reporting Failed: {e}")