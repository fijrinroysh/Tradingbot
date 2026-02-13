from flask import Blueprint, jsonify
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

main_routes = Blueprint('main_routes', __name__)

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================

def log_pipeline(message):
    """Central logger for the pipeline process"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [PIPELINE] {message}")

def get_safe_score(report):
    """
    Robustly extracts score. 
    Checks 'conviction_score' (Internal) AND 'Score' (Google Sheet Header).
    """
    try:
        # Priority 1: Check internal key. Priority 2: Check Sheet Header.
        val = report.get('conviction_score', report.get('Score', 0))
        
        if isinstance(val, (int, float)): return int(val)
        
        # Regex to find number in string "95/100" or "Score: 95"
        match = re.search(r'(\d+)', str(val))
        if match: return int(match.group(1))
    except: pass
    return 0

def calculate_days_held(ticker, details):
    """Calculates days held using position details or order history fallback."""
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
    """
    Manually updates Alpaca 'Position' objects with REAL-TIME data for the email.
    FIXED: Casts values to strings because Alpaca Pydantic models enforce string types.
    """
    if not portfolio_objects: return
    try:
        tickers = [p.symbol for p in portfolio_objects]
        live_prices, _ = trader.get_bulk_market_data(tickers)
        log_pipeline(f"   🌍 Refreshed {len(portfolio_objects)} positions with live market data.")
        
        for p in portfolio_objects:
            if p.symbol in live_prices:
                real_price = float(live_prices[p.symbol])
                
                # ✅ FIX: Cast to String to satisfy Pydantic validation
                p.current_price = str(real_price) 
                
                try:
                    entry = float(p.avg_entry_price)
                    qty = float(p.qty)
                    pl = (real_price - entry) * qty
                    
                    # ✅ FIX: Cast to String here too
                    p.unrealized_pl = str(pl)
                except: pass
                
    except Exception as e:
        log_pipeline(f"⚠️ Portfolio Refresh Warning: {e}")

def get_live_context():
    """Fetches portfolio holdings to inform decisions."""
    try:
        positions = trader.trading_client.get_all_positions()
        live_tickers = [p.symbol for p in positions]
        log_pipeline(f"   💼 Portfolio Context: {len(live_tickers)} active positions.")
        return live_tickers
    except Exception as e:
        log_pipeline(f"   ⚠️ Failed to fetch portfolio: {e}")
        return []

def filter_candidates(live_tickers):
    """
    Stabilized Filter: Filters based on Junior's Score.
    Cleaned up to match the new 'Lean' Google Sheet headers.
    """
    lookback = getattr(config, 'SENIOR_LOOKBACK_DAYS', 5)
    score_threshold = getattr(config, 'JUNIOR_SCORE_THRESHOLD', 88)
    
    # 1. FETCH REPORTS
    portfolio_reports = senior_history.fetch_portfolio_reports(live_tickers)
    market_reports = senior_history.fetch_market_reports(lookback)
    
    # Merge & Deduplicate
    combined_map = {r['ticker']: r for r in market_reports}
    for r in portfolio_reports:
        combined_map[r['ticker']] = r
    
    reports = list(combined_map.values())
    
    log_pipeline(f"🔍 [FILTER] Processing {len(reports)} unique reports. (Threshold: {score_threshold})")

    # 2. BULK DATA FETCH
    all_tickers = [r['ticker'] for r in reports]
    if not all_tickers: return []
    
    price_map, _ = trader.get_bulk_market_data(all_tickers)
    
    final_candidates = []
    seen_tickers = set()

    for raw_report in reports:
        ticker = raw_report.get('ticker')
        score = get_safe_score(raw_report) # Uses updated helper
        is_held = ticker in live_tickers
        
        # --- CLEANING ---
        r = copy.deepcopy(raw_report)
        
        # [UPDATED] Keys to remove before sending to Senior Manager.
        # This matches the NEW Junior Sheet Headers.
        keys_to_remove = [
            # 1. The Decision Data (Hide from Senior)
            'conviction_score', 'Score', 
            'action', 'Action', 
            'analysis_breakdown', 'Detailed_Analysis',
            
            # 2. Execution Params (Senior calculates their own)
            'execution', 'Buy_Limit', 'Take_Profit', 'Stop_Loss',
            
            # 3. Metadata
            'Date', 'Sector'
        ]
        
        # Safe Removal: Only delete if key exists
        for k in keys_to_remove:
            if k in r: del r[k]

        # --- GATE 1: ACTIVE HOLDINGS (Auto-Include) ---
        if is_held:
            if ticker not in seen_tickers:
                if ticker in price_map: r['current_price'] = price_map[ticker]
                final_candidates.append(r)
                seen_tickers.add(ticker)
                log_pipeline(f"   ✅ {ticker}: Auto-Included (Portfolio Asset).")
            continue 

        # --- GATE 2: SCORE FILTER (ACTIVE) ---
        if score < score_threshold:
            continue 

        # --- GATE 3: PRICE CHECK ---
        current_price = price_map.get(ticker)
        if not current_price:
            continue
            
        r['current_price'] = current_price
        
        # Optional: SMA Check
        sma_250 = trader.get_simple_moving_average(ticker, window=250)
        if sma_250:
            if current_price < sma_250:
                if ticker not in seen_tickers:
                    final_candidates.append(r)
                    seen_tickers.add(ticker)
    
    log_pipeline(f"✅ Filtered to {len(final_candidates)} candidates ready for Senior Agent.")
    return final_candidates

def enrich_and_sort_candidates(candidates):
    """Adds active position details and sorts candidates."""
    holdings_map = {} 
    
    # Bulk Fetch Data
    all_tickers = [c['ticker'] for c in candidates]
    price_map, atr_map = trader.get_bulk_market_data(all_tickers)

    enriched = []
    for c in candidates:
        ticker = c.get('ticker')
        
        # Inject Market Data
        c['current_price'] = price_map.get(ticker, 0.0)
        c['daily_volatility'] = atr_map.get(ticker, 0.0)

        # Inject Position Details
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

        enriched.append(c)

    # Sort: Holdings First, Then by Score (if available, else random/price)
    random.shuffle(enriched)
    enriched.sort(key=lambda x: (x['shares_held'] > 0, get_safe_score(x)), reverse=True)
    
    return enriched, holdings_map

def execute_decisions(decision_payload):
    """Executes the Final Orders from the Senior Manager."""
    orders = decision_payload.get('final_execution_orders', [])
    log_pipeline(f"⚙️ EXECUTION: Processing {len(orders)} orders...")
    
    for order in orders:
        ticker = order.get('ticker')
        action = order.get('action', 'HOLD').upper()
        p = order.get('confirmed_params', {})
        
        log_pipeline(f"   👉 Processing Command: {action} {ticker}")
        
        try:
            if action == "OPEN_NEW":
                trader.execute_entry(ticker, config.INVEST_PER_TRADE, p.get('buy_limit', 0), p.get('take_profit', 0), p.get('stop_loss', 0))
            elif action == "UPDATE_EXISTING":
                trader.execute_update(ticker, p.get('take_profit', 0), p.get('stop_loss', 0), buy_limit=p.get('buy_limit', 0))
            elif action == "CANCEL_PENDING":
                trader.execute_cancel(ticker)
        except Exception as e:
            log_pipeline(f"      ❌ Execution Failed for {ticker}: {e}")

# ==========================================
# 👶 PHASE 1: JUNIOR ANALYST
# ==========================================

def run_junior_phase():
    log_pipeline("\n👶 PHASE 1: JUNIOR ANALYST SCAN")
    
    distressed_tickers = scanner.find_distressed_stocks()
    log_pipeline(f"   Found {len(distressed_tickers)} distressed candidates.")
    
    limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
    if limit == 0:
        log_pipeline("⚠️ Daily Scan Limit set to 0. Skipping Junior Analysis.")
        return

    fresh_candidates = junior_history.filter_candidates(distressed_tickers, limit=limit)
    log_pipeline(f"Filtered to {len(fresh_candidates)} fresh candidates.")

    analyzed_count = 0
    for ticker in fresh_candidates:
        current_price = trader.get_current_price(ticker)
        if not current_price: continue
        
        report = junior_agent.analyze_stock(ticker, current_price)
        
        if report:
            junior_history.log_report(ticker, report)
            analyzed_count += 1
            log_pipeline(f"   ✅ Report logged for {ticker}")
            
    log_pipeline(f"   Phase 1 Complete. {analyzed_count} reports generated.")

# ==========================================
# 👨‍💼 PHASE 2: SENIOR MANAGER (SERIAL MODE)
# ==========================================

def run_senior_phase():
    log_pipeline("\n👨‍💼 PHASE 2: SENIOR MANAGER STRATEGY (SERIAL MODE)")
    try:
        # 1. Fetch Context
        live_tickers = get_live_context()

        # 2. Filter Candidates (Gate 2 Active, Senior Blinded to Score)
        final_candidates = filter_candidates(live_tickers)
        log_pipeline(f"Senior Agent will review {len(final_candidates)} candidates.")
        
        if not final_candidates:
            log_pipeline("📉 No candidates found. Stopping Senior Phase.")
            return

        # 3. Enrich & Sort
        sorted_candidates, holdings_map = enrich_and_sort_candidates(final_candidates)

        # 4. Blind Data (Double Check)
        blinded_candidates = copy.deepcopy(sorted_candidates)
        for c in blinded_candidates:
            c['avg_entry_price'] = "HIDDEN"
            c['days_held'] = "HIDDEN"
            c['previous_rank'] = "HIDDEN"

        # 5. Risk Context
        raw_risk = getattr(config, 'RISK_FACTOR', 1.0)
        if raw_risk == 1.0: risk_instruction = driver_fox.FOX_DRIVER_PROMPT
        elif raw_risk < 1.0: risk_instruction = "AUTHORIZATION: BE THE TURTLE. Defense first."
        else: risk_instruction = "AUTHORIZATION: BE THE CHEETAH. Aggression authorized."

        # ==============================================================================
        # 🔄 SERIAL LOOP (One-by-One Analysis)
        # ==============================================================================
        log_pipeline(f"🤖 Starting SERIAL analysis of {len(blinded_candidates)} candidates...")
        
        all_orders = []
        
        for i, candidate in enumerate(blinded_candidates):
            ticker = candidate.get('ticker')
            log_pipeline(f"   👉 [{i+1}/{len(blinded_candidates)}] Analyzing {ticker}...")
            
            # CALL SINGLE TICKER FUNCTION
            result = senior_agent.analyze_single_ticker(
                candidate, 
                risk_factor=risk_instruction
            )
            
            if result and 'final_execution_orders' in result:
                orders = result['final_execution_orders']
                all_orders.extend(orders)
            else:
                log_pipeline(f"   ⚠️ Failed to analyze {ticker}. Skipping.")
                
            time.sleep(1) # Rate limit safety
            
        if not all_orders:
            log_pipeline("❌ Senior Agent returned NO valid orders. Aborting.")
            return

        # 6. Sort Results (High Score First)
        def parse_score_safe(x):
            try: return int(x.get('conviction_score', 0))
            except: return 0
        all_orders.sort(key=parse_score_safe, reverse=True)
        
        # 7. Create Consolidated Payload
        top_pick = all_orders[0]['ticker'] if all_orders else "None"
        buy_count = len([o for o in all_orders if o['action'] == 'OPEN_NEW'])
        
        consolidated_decision = {
            "ceo_report": f"Session Complete. Analyzed {len(blinded_candidates)} assets individually. Identified {buy_count} potential buys. Top conviction leader is {top_pick}.",
            "final_execution_orders": all_orders
        }

        # 8. Logging & Execution
        senior_history.log_strategy(consolidated_decision)
        senior_history.log_detailed_decisions(consolidated_decision, holdings_map)
        
        print("\n" + "="*80)
        print("📢  EXECUTIVE STRATEGY BRIEF (CONSOLIDATED)  📢")
        print("="*80)
        print(consolidated_decision.get('ceo_report'))

        senior_agent.visualize_decision(blinded_candidates, consolidated_decision)
        
        execute_decisions(consolidated_decision)
        
        # 9. Send Email
        log_pipeline("\n📧 PHASE 4: NOTIFICATION")
        try:
            account_info = trader.trading_client.get_account()
            portfolio = trader.trading_client.get_all_positions()
            refresh_portfolio_data(portfolio) # Update prices for email
            
            notifier.send_executive_brief(consolidated_decision, account_info, portfolio)
            log_pipeline("✅ Consolidated Executive Brief email dispatched.")
        except Exception as e:
            log_pipeline(f"❌ Failed to send email: {e}")

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
    
    # 1. Market Check
    #if not trader.is_market_open():
    #   log_pipeline("💤 Market Closed. Aborting.")
    #   return

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
    return jsonify({"status": "Pipeline triggered", "timestamp": datetime.datetime.now()})

@main_routes.route('/health')
def health_check(): return jsonify(status="ok"), 200

@main_routes.route('/webhook', methods=['POST'])
def handle_webhook(): return jsonify(status="received"), 200