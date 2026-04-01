
import threading
import time
import config
import sys, os
import datetime
import copy
import json
import re
import random

# Setup Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SCRIPT_DIR)
sys.path.append(parent_dir)

# Imports
import lib.good_value_quick_money_market_scanner as scanner
import lib.gvqm_alpaca_trader as trader
import lib.gvqm_junior_agent as junior_agent
import lib.gvqm_junior_history as junior_history
import lib.gvqm_senior_agent as senior_agent
import lib.gvqm_senior_history as senior_history
import lib.gvqm_email_notifier as notifier
import lib.gvqm_driver_fox as driver_fox
import lib.gvqm_minor_league as minor_league
import lib.gvqm_major_league as major_league



# ==========================================
# 🔒 CONCURRENCY LOCK
# ==========================================
pipeline_lock = threading.Lock()
is_pipeline_running = False

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================

def log_pipeline(message):
    """Central logger for the pipeline process"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [PIPELINE] {message}")

def get_safe_score(report):
    try:
        val = report.get('conviction_score', report.get('Score', 0))
        if isinstance(val, (int, float)): return int(val)
        match = re.search(r'(\d+)', str(val))
        if match: return int(match.group(1))
    except: pass
    return 0

def calculate_days_held(ticker, details):
    entry_time = details.get('entry_time', None)
    shares = details.get('shares_held', 0)

    if entry_time:
        if isinstance(entry_time, str):
            try:
                entry_dt = datetime.datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
            except:
                entry_dt = datetime.datetime.now(datetime.timezone.utc)
        else:
            entry_dt = entry_time
        delta = datetime.datetime.now(datetime.timezone.utc) - entry_dt
        return delta.days
    elif shares > 0:
        try:
            req = trader.GetOrdersRequest(status=trader.QueryOrderStatus.CLOSED, symbols=[ticker], limit=50)
            closed_orders = trader.trading_client.get_orders(filter=req)
            last_buy = next((o for o in closed_orders if o.side == trader.OrderSide.BUY and o.filled_at), None)
            if last_buy:
                delta = datetime.datetime.now(datetime.timezone.utc) - last_buy.filled_at
                return delta.days
        except Exception as e:
            pass
    return 0

def refresh_portfolio_data(portfolio_objects):
    if not portfolio_objects: return
    try:
        tickers = [p.symbol for p in portfolio_objects]
        live_prices, _ = trader.get_bulk_market_data(tickers)
        log_pipeline(f"   🌍 Refreshed {len(portfolio_objects)} positions with live market data.")
        
        for p in portfolio_objects:
            if p.symbol in live_prices:
                real_price = float(live_prices[p.symbol])
                p.current_price = str(real_price) 
                try:
                    entry = float(p.avg_entry_price)
                    qty = float(p.qty)
                    pl = (real_price - entry) * qty
                    p.unrealized_pl = str(pl)
                except: pass
    except Exception as e:
        log_pipeline(f"⚠️ Portfolio Refresh Warning: {e}")

def get_live_context():
    try:
        positions = trader.trading_client.get_all_positions()
        live_tickers = [p.symbol for p in positions]
        log_pipeline(f"   💼 Portfolio Context: {len(live_tickers)} active positions.")
        return live_tickers
    except Exception as e:
        log_pipeline(f"   ⚠️ Failed to fetch portfolio: {e}")
        return []

def enrich_and_sort_candidates(candidates):
    holdings_map = {} 
    all_tickers = [c['ticker'] for c in candidates]
    price_map, atr_map = trader.get_bulk_market_data(all_tickers)
    strategy_map = senior_history.fetch_active_strategies(all_tickers)

    enriched = []
    for c in candidates:
        ticker = c.get('ticker')
        c['current_price'] = price_map.get(ticker, 0.0)
        c['daily_volatility'] = atr_map.get(ticker, 0.0)

        if hasattr(trader, 'get_position_details'):
            details = trader.get_position_details(ticker)
            c['shares_held'] = details['shares_held']
            c['avg_entry_price'] = details['avg_entry_price']
            c['current_active_tp'] = details['active_tp']
            c['current_active_sl'] = details['active_sl']
            c['pending_buy_limit'] = details['pending_buy_limit']
            c['days_held'] = calculate_days_held(ticker, details) 
            holdings_map[ticker] = details['shares_held']
        else:
            c['shares_held'] = 0
            c['days_held'] = 0
            holdings_map[ticker] = 0

        c['current_active_strategy'] = strategy_map.get(ticker, "NONE")
        enriched.append(c)

    # Sort logic to keep holdings near the top for processing
    random.shuffle(enriched)
    enriched.sort(key=lambda x: (x['shares_held'] > 0), reverse=True)
    return enriched, holdings_map

def safe_float(val):
    if val is None: return 0.0
    try:
        if isinstance(val, (int, float)): return float(val)
        clean = str(val).replace('$', '').replace(',', '').replace('[', '').replace(']', '').strip()
        if not clean: return 0.0
        return float(clean)
    except Exception:
        return 0.0

# ==========================================
# ⚙️ THE STATE MACHINE (Pure Swap Logic)
# ==========================================

def process_swiss_standings(swiss_standings):
    """
    Evaluates the leaderboard. It ONLY buys if an unowned stock 
    ranks higher than an already owned stock (A 1-for-1 Swap).
    """
    mechanical_orders = []
    llm_orders = []

    if not swiss_standings:
        return llm_orders, mechanical_orders

    # 1. SCOUT THE PLAYERS: Find the Best Unowned and the Worst Owned
    best_unowned = None
    worst_owned = None

    for rank, candidate in enumerate(swiss_standings):
        candidate['current_rank'] = rank  # Save their leaderboard position
        shares = float(candidate.get('shares_held', 0))
        
        if shares > 0:
            # Continues updating as it moves down the list, settling on the worst owned
            worst_owned = candidate 
            
        elif shares == 0 and best_unowned is None:
            # Grabs the very first unowned stock it sees (the highest ranked one)
            best_unowned = candidate 

    # 2. THE SWAP CHECK: Does the New Guy beat the Weakest Link?
    swap_triggered = False
    if best_unowned and worst_owned:
        if best_unowned['current_rank'] < worst_owned['current_rank']:
            swap_triggered = True
            log_pipeline(f"🔄 SWAP OPPORTUNITY DETECTED: {best_unowned['ticker']} (Rank {best_unowned['current_rank']}) outranks {worst_owned['ticker']} (Rank {worst_owned['current_rank']}).")

    # 3. ASSIGN THE ACTIONS
    for candidate in swiss_standings:
        ticker = candidate['ticker']
        shares_owned = float(candidate.get('shares_held', 0))
        pending_buy = float(candidate.get('pending_buy_limit', 0) or 0)
        
        # Extract what the LLM *wants* to do based on its isolated decision
													 

							
        llm_action = "HOLD"
        order_data = {}
        if candidate.get('_senior_decision'):
            decision = candidate['_senior_decision']
            if 'final_execution_orders' in decision and decision['final_execution_orders']:
                order_data = decision['final_execution_orders'][0]
                llm_action = order_data.get('action', 'HOLD').upper()

        final_action = "HOLD"

												
										 
										   

        # --- APPLY THE SWAP RULES ---
        if swap_triggered and ticker == worst_owned['ticker']:
													  
            final_action = "CLOSE_POSITION"  # Fire the loser
            
        elif swap_triggered and ticker == best_unowned['ticker']:
            final_action = "OPEN_NEW"        # Hire the winner
								  
																		   

        # --- STANDARD MAINTENANCE (For everyone else) ---
        else:
            if shares_owned > 0:
                if llm_action == "UPDATE": 
                    final_action = "UPDATE_EXISTING" # Trail stops for healthy portfolio stocks
            elif shares_owned == 0 and pending_buy > 0:
                final_action = "CANCEL_PENDING"      # Clean up old orphaned orders

        # --- STAGE THE ORDERS ---
        if final_action == "CLOSE_POSITION":
            reason = f"Swapped out. Outranked by {best_unowned['ticker']}."
            mechanical_orders.append({"ticker": ticker, "action": "CLOSE_POSITION", "final_recommendation": "AVOID", "matchup_rationale": reason})
            if hasattr(senior_history, 'log_mechanical_trade'):
                senior_history.log_mechanical_trade(ticker, "CLOSE_POSITION", reason, candidate.get('current_price', 0), shares_owned)
        
        elif final_action == "CANCEL_PENDING":
            reason = "Orphaned Pending Order"
            mechanical_orders.append({"ticker": ticker, "action": "CANCEL_PENDING", "final_recommendation": "AVOID", "matchup_rationale": reason})
            if hasattr(senior_history, 'log_mechanical_trade'):
                senior_history.log_mechanical_trade(ticker, "CANCEL_PENDING", reason, candidate.get('current_price', 0), shares_owned)
        
        elif final_action in ["OPEN_NEW", "UPDATE_EXISTING"]:
            if order_data:
                order_data['action'] = final_action
                llm_orders.append(order_data)

    return llm_orders, mechanical_orders

# ==========================================
# ⚙️ EXECUTION LOGIC (Pure Swap Mode)
# ==========================================

def execute_decisions(decision_payload):
    orders = decision_payload.get('final_execution_orders', [])
    log_pipeline(f"⚙️ EXECUTION: Processing {len(orders)} orders (Swap Logic Enabled)...")
    
    # 🔄 CRITICAL: Sort orders so we SELL before we BUY to free up cash for the swap!
    sort_priority = {"CLOSE_POSITION": 1, "CANCEL_PENDING": 2, "UPDATE_EXISTING": 3, "OPEN_NEW": 4, "HOLD": 5}
    orders.sort(key=lambda o: sort_priority.get(o.get('action', 'HOLD').upper(), 99))

    # Pull the base trade budget from your config file
    base_capital = getattr(config, 'INVEST_PER_TRADE', 1000)

    ALLOCATION_MAP = {
        "POSITION_ONLY": 0.70,
        "SWING_ONLY":    0.30,
        "HYBRID":        1.00,
        "AVOID":         0.00
    }

    for order in orders:
        ticker = order.get('ticker')
        action = order.get('action', 'HOLD').upper()
        recommendation = order.get('final_recommendation', 'AVOID').upper()
        
        alloc_mult = ALLOCATION_MAP.get(recommendation, 0.0)
        investment_amount = base_capital * alloc_mult
        
        target_dict = order.get('swing_trade_analysis', {}) 
        
        if recommendation == "POSITION_ONLY":
            log_pipeline(f"   🛡️ Mode: POSITION ONLY (70% Capital, Wide Stops)")
            target_dict = order.get('position_trade_analysis', {})
        elif recommendation == "HYBRID":
            log_pipeline(f"   🛡️ Mode: HYBRID (100% Capital, Wide Stops)")
            target_dict = order.get('position_trade_analysis', {})
        elif recommendation == "SWING_ONLY":
            log_pipeline(f"   ⚔️ Mode: SWING ONLY (30% Capital, Tight Stops)")
            target_dict = order.get('swing_trade_analysis', {})

        plan = target_dict.get('execution_plan', {})
        entry_price = safe_float(plan.get('entry_price'))
        take_profit = safe_float(plan.get('take_profit'))
        stop_loss   = safe_float(plan.get('stop_loss'))

        log_pipeline(f"   👉 {ticker} Action: {action} | Target Alloc: ${investment_amount:.0f} ({alloc_mult*100}%)")

        try:
            if action == "CLOSE_POSITION":
                log_pipeline(f"      🚨 EJECTING {ticker} (Relegated). Freeing up cash for swap...")
                trader.close_full_position(ticker)
                time.sleep(2) # Brief pause to let Alpaca register the freed cash
				 
																							

            elif action == "CANCEL_PENDING":
                trader.execute_cancel(ticker)
                
            elif action == "UPDATE_EXISTING":
                trader.execute_update(ticker, take_profit, stop_loss, buy_limit=entry_price)
												  

            elif action == "OPEN_NEW":
                if investment_amount <= 0:
                    log_pipeline(f"      ⛔ Skipped {ticker}: Allocation is $0.")
                    continue
                    
                log_pipeline(f"      ✅ SENDING BUY ORDER for {ticker} (Target Amount: ${investment_amount:.2f}).")
                trader.execute_entry(ticker, investment_amount, entry_price, take_profit, stop_loss)

            elif action == "HOLD":
                log_pipeline(f"      ⏸️ Holding {ticker}. No changes.")

        except Exception as e:
            log_pipeline(f"      ❌ Execution Failed for {ticker}: {e}")

# ==========================================
# 👶 PHASE 1: JUNIOR ANALYST (ELO MATCHMAKING)
# ==========================================

def run_junior_phase():
    log_pipeline("\n👶 PHASE 1: JUNIOR ANALYST SCAN (ELO LEAGUE)")
    
    distressed_tickers = scanner.find_distressed_stocks()
    log_pipeline(f"   Found {len(distressed_tickers)} distressed candidates.")
    
    limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
    
    # Using the module method for staleness filtering
    priority_tickers = junior_history.filter_candidates(distressed_tickers, limit=limit)
    log_pipeline(f"   Filtered to {len(priority_tickers)} priority candidates.")

    candidates_with_prices = []
    for ticker in priority_tickers:
        price = trader.get_current_price(ticker)
        if price:
            candidates_with_prices.append({'ticker': ticker, 'current_price': price})
            
    if len(candidates_with_prices) < 2:
        log_pipeline("   ⚠️ Not enough candidates to run a matchup. Skipping Phase 1.")
        return
    
    matches_to_run = max(1, limit // 2)
    matchups = minor_league.get_next_matchups(candidates_with_prices, league_name="Junior_Elo", match_count=matches_to_run)
    
    log_pipeline(f"   🥊 Prepared {len(matchups)} 1v1 matchups.")

    analyzed_count = 0
    for match in matchups:
        cand_a = match[0]
        cand_b = match[1]
        ticker_a = cand_a['ticker']
        ticker_b = cand_b['ticker']
        
        report = junior_agent.evaluate_matchup(cand_a, cand_b)
        
        if report and 'ticker' in report:
            winner_ticker = report['ticker']
            loser_ticker = ticker_b if winner_ticker == ticker_a else ticker_a
            
            log_pipeline(f"   🏆 MATCH RESULT: {winner_ticker} defeated {loser_ticker}")
            
            minor_league.record_match_result("Junior_Elo", winner_ticker, loser_ticker)
            junior_history.log_report(winner_ticker, report)
            analyzed_count += 1
        else:
            log_pipeline(f"   ⚠️ Matchup failed or returned invalid data: {ticker_a} vs {ticker_b}")
            
    log_pipeline(f"   Phase 1 Complete. {analyzed_count} matchups successfully processed.")

# ==========================================
# 👨‍💼 PHASE 2: SENIOR MANAGER (SWISS LEAGUE)
# ==========================================

def run_senior_phase():
    log_pipeline("\n👨‍💼 PHASE 2: SENIOR MANAGER STRATEGY (SWISS LEAGUE MODE)")
    try:
		# 1. THE DRAFT (Fetching Data)
        leaderboard = minor_league.fetch_leaderboard("Junior_Elo")
        if not leaderboard:
            log_pipeline("   ⚠️ No Elo leaderboard found. Junior needs to run more matches.")
            return

        sorted_league = sorted(leaderboard.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
        live_tickers = get_live_context()  # Get our portfolio FIRST
        
        # 2. DRAFT THE CHALLENGERS (Filter out owned stocks first!)
        unowned_challengers = [item[0] for item in sorted_league if item[0] not in live_tickers]
        
        draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 4)
        top_tickers = unowned_challengers[:draft_limit] # Grab the top N fresh faces
        
        log_pipeline(f"   🥊 Minor League sent {len(top_tickers)} brand new challengers: {top_tickers}")

        # 3. ADD THE DEFENDING CHAMPIONS (The Portfolio)
        top_tickers.extend(live_tickers)
        
        log_pipeline(f"   📋 Final Major League Roster ({len(top_tickers)} stocks): {top_tickers}")
									 
                
        log_pipeline(f"   📋 Drafted {len(top_tickers)} stocks for the Swiss League: {top_tickers}")
        if len(top_tickers) < 2:
            log_pipeline("   ⚠️ Not enough candidates to run Swiss League.")
            return

        # 3. ENRICH DATA
        playoff_candidates = [{'ticker': t} for t in top_tickers]
        sorted_candidates, holdings_map = enrich_and_sort_candidates(playoff_candidates)
        
        log_pipeline(f"🤖 Starting SWISS LEAGUE analysis of {len(sorted_candidates)} candidates...")
        
        # 4. RUN THE SWISS LEAGUE
        swiss_standings = major_league.run_swiss_league(sorted_candidates, num_rounds=3)
        if not swiss_standings:
            log_pipeline("   ⚠️ Swiss League failed to produce valid standings.")
            return

        # ==============================================================
        # ⚖️ THE FIX: APPLY ALL-TIME ELO RANKING BEFORE EXECUTION
        # ==============================================================
        # We fetch the newly updated All-Time Senior Leaderboard
        senior_leaderboard = minor_league.fetch_leaderboard("Senior_Elo")
        
        for cand in swiss_standings:
            ticker = cand['ticker']
            # Default to 1500 if they are a brand new rookie today
            cand['_all_time_elo'] = senior_leaderboard.get(ticker, {}).get('Elo_Rating', 1500.0)
            
        # Re-sort today's participants STRICTLY by their All-Time rating!
        swiss_standings.sort(key=lambda x: x['_all_time_elo'], reverse=True)
        
        log_pipeline(f"   🏆 TRUE CHAMPION (All-Time): {swiss_standings[0]['ticker']} ({swiss_standings[0]['_all_time_elo']:.1f} Elo)")
        log_pipeline(f"   🗑️ TRUE LOSER (All-Time): {swiss_standings[-1]['ticker']} ({swiss_standings[-1]['_all_time_elo']:.1f} Elo)")
        # ==============================================================

        # 5. THE STATE MACHINE: Generate all execution logic
        llm_orders, mechanical_orders = process_swiss_standings(swiss_standings)
        all_orders = llm_orders + mechanical_orders

        if not all_orders:
            log_pipeline("❌ State machine generated NO valid orders. Aborting execution phase.")
            return

        # 6. LOGGING & CONSOLIDATION
        champion_ticker = swiss_standings[0]['ticker']
        consolidated_decision = {
            "ceo_report": f"Swiss League Complete. True Champion: {champion_ticker}. Actions Processed: {len(all_orders)}.",
            "final_execution_orders": all_orders
        }

        # Log overarching strategy and execute
        senior_history.log_strategy(consolidated_decision)
        if llm_orders:
            llm_only_payload = {"ceo_report": consolidated_decision["ceo_report"], "final_execution_orders": llm_orders}
            senior_history.log_detailed_decisions(llm_only_payload, holdings_map)
            if hasattr(senior_agent, 'visualize_decision'):
                senior_agent.visualize_decision(sorted_candidates, llm_only_payload)
        
        execute_decisions(consolidated_decision)
        
        # =========================================================
        # 📧 EMAIL BLOCK
        # =========================================================
        try:
            print("   📧 Preparing Email Notification...") 
            
            account_info = trader.get_account()
            portfolio_objects = trader.get_portfolio()
            refresh_portfolio_data(portfolio_objects) # Get live prices
            
            # ✅ OPTION: Filter the leaderboard to ONLY show today's participants
            active_tickers = [c['ticker'] for c in swiss_standings]
            filtered_leaderboard = {k: v for k, v in senior_leaderboard.items() if k in active_tickers}
            
            # Sort the filtered list
            sorted_senior = sorted(filtered_leaderboard.items(), key=lambda x: x[1]['Elo_Rating'], reverse=True)
   
               
            consolidated_decision["major_league_standings"] = sorted_senior
            
            # SEND IT
            notifier.send_executive_brief(consolidated_decision, account_info, portfolio_objects)
            log_pipeline("✅ Consolidated Executive Brief email dispatched.")

        except Exception as e:
            log_pipeline(f"❌ Failed to send email: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        log_pipeline(f"❌ CRITICAL ERROR in Senior Phase: {e}")
        import traceback
        traceback.print_exc()

# ==========================================
# 🚀 MAIN PIPELINE
# ==========================================

def run_pipeline():
    print("\n" + "="*60)
    log_pipeline("🚀 STARTING DAILY TRADING PIPELINE (PRODUCTION)")
    print("="*60)
    
    if getattr(config, 'DEBUG_MODE', False) == False:
        # 1. Market Check
        if not trader.is_market_open():
            log_pipeline("💤 Market Closed. Aborting.")
            return

    run_junior_phase()
    run_senior_phase()

    print("\n" + "="*80)
    log_pipeline("✅ PIPELINE COMPLETE. Check Sheets & Email.")
    print("="*80 + "\n")
