from flask import Blueprint, jsonify
import threading
import time
import config
import sys, os
import datetime
import copy
import json
import re
import random  # <--- NEW: Required for shuffling

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
import lib.gvqm_driver_fox as driver_fox  # <--- NEW: Import Fox Driver

main_routes = Blueprint('main_routes', __name__)

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================

def log_pipeline(message):
    """Central logger for the pipeline process"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [PIPELINE] {message}")

def get_safe_score(report):
    """Safely extracts conviction score, returning 0 if invalid."""
    try:
        val = report.get('conviction_score', 0)
        if val is None or val == "": return 0
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def parse_rank_score(rank_str):
    """
    Helper to convert alphanumeric ranks (A1, B10) into sortable integers.
    A1 -> 10001, B10 -> 20010, Unranked -> 99999
    """
    if not rank_str or rank_str == "Unranked": return 99999
    try:
        zone = rank_str[0].upper()
        num_str = re.sub(r'\D', '', rank_str)
        num = int(num_str) if num_str else 0
        prefix = (ord(zone) - ord('A') + 1) * 10000
        return prefix + num
    except:
        return 99999

def calculate_days_held(ticker, details):
    """
    Robustly calculates days held using position details or order history fallback.
    Returns: Integer (days)
    """
    entry_time = details.get('entry_time', None)
    shares = details.get('shares_held', 0)

    # 1. Try fetching from Details first
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

    # 2. Fallback: If missing but we OWN it, check Order History
    elif shares > 0:
        try:
            # Fetch last 50 closed orders to find the entry
            req = trader.GetOrdersRequest(status=trader.QueryOrderStatus.CLOSED, symbols=[ticker], limit=50)
            closed_orders = trader.trading_client.get_orders(filter=req)
            
            # Find the most recent BUY order
            last_buy = next((o for o in closed_orders if o.side == trader.OrderSide.BUY and o.filled_at), None)
            
            if last_buy:
                delta = datetime.datetime.now(datetime.timezone.utc) - last_buy.filled_at
                log_pipeline(f"   🕒 Calculated days_held for {ticker} from orders: {delta.days} days")
                return delta.days
        except Exception as e:
            log_pipeline(f"   ⚠️ Could not calc days_held for {ticker}: {e}")
    
    # Default to 0 (New/Unknown)
    return 0

# ==========================================
# 🕵️ PHASE 1: JUNIOR ANALYST
# ==========================================

def run_junior_phase():
    log_pipeline("🕵️ PHASE 1: JUNIOR ANALYST RESEARCH")
    try:
        candidates = scanner.find_distressed_stocks()
        log_pipeline(f"Scanner found {len(candidates)} raw candidates.")
        
        limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
                                                                       
        
        # --- FIX: EXPLICITLY HANDLE 0 LIMIT ---
        if limit == 0:
            log_pipeline("⚠️ Daily Scan Limit set to 0. Skipping Junior Analysis.")
            fresh_candidates = []
        else:
            fresh_candidates = junior_history.filter_candidates(candidates, limit=limit)
        # --------------------------------------

        log_pipeline(f"Filtered to {len(fresh_candidates)} fresh candidates (Limit: {limit}).")
        
        processed_count = 0
        for ticker in fresh_candidates:
            price = trader.get_current_price(ticker)
            if not price: 
                log_pipeline(f"⚠️ Skipping {ticker}: No price data available.")
                continue
                
            report = junior_agent.analyze_stock(ticker, price)
            if report:
                junior_history.log_report(ticker, report)
                processed_count += 1
            time.sleep(1)
        log_pipeline(f"Junior Analyst filed {processed_count} new reports.")
    except Exception as e:
        log_pipeline(f"❌ CRITICAL ERROR in Junior Phase: {e}")

# ==========================================
# 👨‍💼 PHASE 2: SENIOR MANAGER
# ==========================================

def get_live_context():
    """Returns a set of all tickers currently held or with open orders."""
    log_pipeline("   ℹ️ Fetching Live Portfolio Context...")
    live_tickers = set()
    try:
        positions = trader.trading_client.get_all_positions()
        for p in positions: live_tickers.add(p.symbol)
        
        req_params = trader.GetOrdersRequest(status=trader.QueryOrderStatus.OPEN)
        orders = trader.trading_client.get_orders(filter=req_params)
        for o in orders: live_tickers.add(o.symbol)
        
        log_pipeline(f"   ℹ️ Portfolio Context: Tracking {len(live_tickers)} active tickers: {list(live_tickers)}")
    except Exception as e:
        log_pipeline(f"   ⚠️ Could not fetch live portfolio: {e}")
    return live_tickers

def filter_candidates(live_tickers):
    """Fetches reports and filters them based on Score and SMA rules."""
    lookback = getattr(config, 'SENIOR_LOOKBACK_DAYS', 5)
    score_threshold = getattr(config, 'JUNIOR_SCORE_THRESHOLD', 88)
    
    # --- STEP 2: FETCH REPORTS (DUAL METHOD) ---
    portfolio_reports = senior_history.fetch_portfolio_reports(live_tickers)
    market_reports = senior_history.fetch_market_reports(lookback)
    reports = portfolio_reports + market_reports
    
    log_pipeline(f"fetched {len(portfolio_reports)} portfolio reports + {len(market_reports)} market reports. Total: {len(reports)}")
    log_pipeline(f"Applying filters: Score > {score_threshold} AND Price < 250 SMA (Unless Held)...")

    # --- STEP 3: FILTER CANDIDATES ---
    final_candidates = []
    seen_tickers = set()

    for raw_report in reports:
        ticker = raw_report.get('ticker')
        score = get_safe_score(raw_report)
        is_held = ticker in live_tickers
        
        # Clean report
        r = copy.deepcopy(raw_report)
        
                      
        
                                                                                  
        keys_to_remove = [
            'recommended_action', 'audit_reason', 'sector', 'junior_targets' ,'catalyst'
        ]
        
        for k in keys_to_remove:
            if k in r: del r[k]

        # CRITERIA 1: ACTIVE HOLDINGS (Always Include)
        if is_held:
            if ticker not in seen_tickers:
                final_candidates.append(r)
                seen_tickers.add(ticker)
                log_pipeline(f"   ✅ Auto-Included {ticker} (Portfolio Review)")
            continue 

        # CRITERIA 2: SCORE FILTER
        if score <= score_threshold: continue 
            
        # CRITERIA 3: 250 SMA CHECK
        current_price = trader.get_current_price(ticker)
        sma_250 = trader.get_simple_moving_average(ticker, window=250)
        
        if current_price and sma_250:
            if current_price < sma_250:
                if ticker not in seen_tickers:
                    final_candidates.append(r)
                    seen_tickers.add(ticker)
            else:
                log_pipeline(f"   📉 Rejecting {ticker}: Price ${current_price} is ABOVE 250 SMA.")
        else:
            log_pipeline(f"   ⚠️ Skipping {ticker}: Could not verify SMA compliance.")

    return final_candidates

def enrich_and_sort_candidates(candidates):
    """Injects live data (Price, Rank, Holdings, Days Held) and sorts them."""
    log_pipeline(f"Fetching Live Data & Rank History...")
    previous_ranks = senior_history.fetch_latest_ranks()
    holdings_map = {}
    

    # [NEW] 1. Extract List of Tickers & Bulk Fetch via Trader
    all_tickers = [c['ticker'] for c in candidates]
    price_map, atr_map = trader.get_bulk_market_data(all_tickers)                                                              
                                                   
                 

    # 1. Enrich Data
    for c in candidates:
        ticker = c['ticker']
        
          
        # [NEW] Assign from Bulk Data
        c['current_price'] = price_map.get(ticker, 0.0)
        c['daily_volatility'] = atr_map.get(ticker, 0.0) # Inject ATR
                                                                     
  
        # Inject Previous Rank for Ladder Logic
        c['previous_rank'] = previous_ranks.get(ticker, "Unranked")
        
                     
        if hasattr(trader, 'get_position_details'):
            details = trader.get_position_details(ticker)
            
            c['shares_held'] = details['shares_held']
            c['avg_entry_price'] = details['avg_entry_price']
            c['current_active_tp'] = details['active_tp']
            c['current_active_sl'] = details['active_sl']
            c['pending_buy_limit'] = details['pending_buy_limit']
            
            # --- NEW: CALCULATE DAYS HELD ---
            c['days_held'] = calculate_days_held(ticker, details)
            
            holdings_map[ticker] = details['shares_held']
        else:
            c['shares_held'] = trader.get_position(ticker)
            holdings_map[ticker] = c['shares_held']

    # ------------------------------------------------------------------
    # STEP 4.5: THE SHUFFLE (Removing Bias)
    # ------------------------------------------------------------------
    # We remove the "Veterans vs Recruits" sorting.
    # We SHUFFLE the deck so the Senior Manager doesn't just pick the top stocks.
    
    log_pipeline("   🎲 Shuffling Candidates to prevent Order Bias...")
    random.shuffle(candidates)
    
	
	

	
  

	
  

   
  
    log_pipeline(f"   📊 List Randomized: {len(candidates)} candidates ready for review.")
    
    return candidates, holdings_map

def execute_decisions(decision):
    """Parses JSON decision and executes trades."""
    # 6. EXECUTE TRADES
    orders = decision.get('final_execution_orders', [])
    log_pipeline(f"\n⚡ PHASE 3: EXECUTION ({len(orders)} Commands)")
    
    for order in orders:
        ticker = order.get('ticker')
        action = order.get('action', 'HOLD').upper() 
        p = order.get('confirmed_params', {})
        
        log_pipeline(f"   👉 Processing Command: {action} {ticker}")
        
        trade_events = []
        try:
            if action == "OPEN_NEW":
                trade_events = trader.execute_entry(ticker, config.INVEST_PER_TRADE, p.get('buy_limit', 0), p.get('take_profit', 0), p.get('stop_loss', 0))
            
            elif action == "UPDATE_EXISTING":
                # --- NEW: BLIND PROTOCOL SAFETY CHECK ---
                # If AI was blinded, it might not send valid SL/TP numbers.
                # However, Python executes based on valid inputs. 
                # If 'stop_loss' is missing or 0, existing logic might fail or set 0.
                # We assume the AI still provides 'structure-based' SL if it can see Current Price and ATR.
                # The 'Break-Even' logic will be handled if the AI outputs a specific number, 
                # OR we could add a flag here, but sticking to non-aggressive changes, we rely on the Prompt using ATR/Price.
                trade_events = trader.execute_update(ticker, p.get('take_profit', 0), p.get('stop_loss', 0), buy_limit=p.get('buy_limit', 0))
            
            elif action == "CANCEL_PENDING":
                trade_events = trader.execute_cancel(ticker)
            
            elif action == "HOLD":
                log_pipeline(f"      ✋ Holding {ticker}.")
                continue
                
        except Exception as e:
            log_pipeline(f"      ❌ Execution Exception for {ticker}: {e}")

        if isinstance(trade_events, dict): trade_events = [trade_events]
        for event in trade_events:
            if isinstance(event, dict) and event.get('event') != "ERROR":
                senior_history.log_trade_event(ticker, event.get('event'), event)

def run_senior_phase():
    log_pipeline("\n👨‍💼 PHASE 2: SENIOR MANAGER STRATEGY")
    try:
        # 1. Fetch Context
        live_tickers = get_live_context()

        # 2. Filter Candidates
        final_candidates = filter_candidates(live_tickers)
        log_pipeline(f"Senior Agent will review {len(final_candidates)} candidates.")
        
        if not final_candidates:
            log_pipeline("📉 No candidates found. Stopping Senior Phase.")
            return

        # 3. Enrich & Sort
        sorted_candidates, holdings_map = enrich_and_sort_candidates(final_candidates)

        # --- NEW: DATA SANITIZATION (BLIND PROTOCOL) ---
        # We perform a deep copy to sanitize the data sent to the AI, 
        # protecting it from Profit Bias (Entry Price) and Tenure Bias (Days Held).
        blinded_candidates = copy.deepcopy(sorted_candidates)
        for c in blinded_candidates:
            c['avg_entry_price'] = "HIDDEN"
            c['days_held'] = "HIDDEN"
            c['previous_rank'] = "HIDDEN"  # <--- NEW: Hides Previous Rank to prevent Confirmation Bias
        # -----------------------------------------------


# --- CONVERSATIONAL RISK TRANSLATOR (DYNAMIC INJECTION) ---
        raw_risk = getattr(config, 'RISK_FACTOR', 1.0)
        

        if raw_risk == 1.0:
            # THE FOX (Balance)
            risk_instruction = driver_fox.FOX_DRIVER_PROMPT
			 
					
							
	

        elif raw_risk < 1.0:
            # THE TURTLE (Defense)
            pct = int(round((1.0 - raw_risk) * 100))
            risk_instruction = (
                f"AUTHORIZATION: BE THE TURTLE.\n"
                f"The CEO is worried (Risk reduced by {pct}%).\n"
                "INSTRUCTION: Hide in your shell! Do not lose money. If the deal isn't perfect, walk away. WAITING is better than LOSING."
            )

        else:
            # THE CHEETAH (Offense)
            pct = int(round((raw_risk - 1.0) * 100))
            risk_instruction = (
                f"AUTHORIZATION: BE THE CHEETAH.\n"
                f"The CEO wants growth (Aggression increased by {pct}%).\n"
                "INSTRUCTION: Run fast! The market is hot. Don't worry about small scratches. Chase the big prize before it gets away."
            )
 
        log_pipeline(f"   ⚖️ Risk Mandate: {risk_instruction[:10]}...")
        # -------------------------------------------

        # 4. AI Decision                                                      
        log_pipeline("Calling Senior Agent AI for ranking ...")
        
        # --- NEW: CONTEXT FROM INDIVIDUAL TICKERS ---
        # 1. Fetch Granular Decisions (Ticker + Reason + Date)
        previous_decisions = senior_history.fetch_latest_decisions() 
        
        # 2. Extract Date (Take from the first record if available)
        prev_date = 'Unknown Date'
        # Try finding date in any capitalization (Date/date)
        if previous_decisions and len(previous_decisions) > 0:
            first = previous_decisions[0]
            prev_date = first.get('Date') or first.get('date') or 'Unknown Date'

        context_lines = []
        if previous_decisions:
            for d in previous_decisions:
                # Robust extraction (Capitalized or Lowercase keys)
                t = d.get('ticker') or d.get('Ticker') or 'UNKNOWN'
                # REMOVED RANK extraction per user instruction
                
                # [FIXED] Extraction using 'Reasoning' column header
                why = d.get('Reasoning') or d.get('reasoning') or 'No reason provided.'
                
                # Format: [Ticker]: Reason
                context_lines.append(f"[{t}]: {why}")
        
        combined_context = "\n".join(context_lines) if context_lines else "No previous ticker context available."
        
        # 3. Construct Context Dictionary
        # CRITICAL: Keys must match what senior_agent expects ('prev_report', NOT 'ceo_report')
        context = {
            'date': prev_date,
            'prev_report': combined_context 
        }
        # --------------------------------------------
        
        # [UPDATED] We now pass 'blinded_candidates' instead of 'sorted_candidates'
        decision = senior_agent.rank_portfolio(
            blinded_candidates, 
            top_n=getattr(config, 'SENIOR_TOP_PICKS', 5),
                                            
            risk_factor = risk_instruction,
            prev_context=context
        )
        
        if decision:
            senior_history.log_strategy(decision)
            senior_history.log_detailed_decisions(decision, holdings_map)
            
            print("\n" + "="*80)
            print("📢  EXECUTIVE STRATEGY BRIEF  📢")
            print("="*80)
            print(decision.get('ceo_report'))
            
            # 5. Execute
            execute_decisions(decision)
            
            # 7. SEND EMAIL
            log_pipeline("\n📧 PHASE 4: NOTIFICATION")
            try:
                account_info = trader.trading_client.get_account()
                portfolio = trader.trading_client.get_all_positions()
                notifier.send_executive_brief(decision, account_info, sorted_candidates, portfolio)
                log_pipeline("✅ Executive Brief email dispatched.")
            except Exception as e:
                log_pipeline(f"❌ Failed to send email: {e}")

    except Exception as e:
        log_pipeline(f"❌ CRITICAL ERROR in Senior Phase: {e}")

# ==========================================
# 🚀 MAIN PIPELINE
# ==========================================

def run_pipeline():
    print("\n" + "="*60)
    log_pipeline("🚀 STARTING DAILY TRADING PIPELINE (PRODUCTION)")
    print("="*60)
    
    #if getattr(config, 'DEBUG_MODE', False) == False:
    #    log_pipeline("⚠️ DEBUG MODE ACTIVE: No real trades will be executed.")
    #    # 1. MARKET CHECK
    #    if not trader.is_market_open():
    #        log_pipeline("💤 Market Closed. Aborting.")
    #        return

    run_junior_phase()
    run_senior_phase()

    print("\n" + "="*80)
    log_pipeline("✅ PIPELINE COMPLETE. Check Sheets & Email.")
    print("="*80 + "\n")

# ==========================================
# 🌐 FLASK ROUTES
# ==========================================

@main_routes.route('/tradingbot')
def trigger_scan():
    thread = threading.Thread(target=run_pipeline)
    thread.start()
    return jsonify(status="pipeline_started"), 202

@main_routes.route('/health')
def health_check(): return jsonify(status="ok"), 200

@main_routes.route('/webhook', methods=['POST'])
def handle_webhook(): return jsonify(status="received"), 200