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

# In routes.py

def filter_candidates(live_tickers):
    """
    DUAL-STRATEGY FILTER:
    1. Fetches Pre-Merged Junior Reports (Latest Only).
    2. Enforces Config Thresholds.
    """
    # Load Thresholds from Config
    pos_thresh = getattr(config, 'JUNIOR_POSITION_SCORE_THRESHOLD', 85)
    swing_thresh = getattr(config, 'JUNIOR_SWING_SCORE_THRESHOLD', 70)
    lookback = getattr(config, 'SENIOR_LOOKBACK_DAYS', 5)

    # 1. FETCH (Delegated to Junior History)
    # This now returns clean, merged objects. No manual grouping needed here.
    candidates = junior_history.fetch_recent_reports(lookback_days=lookback)
    
    log_pipeline(f"🔍 [FILTER] Checking {len(candidates)} unique candidates against thresholds ({pos_thresh}/{swing_thresh})...")

    final_candidates = []
    
    # Bulk Price Fetch (Optimization)
    tickers = [c['ticker'] for c in candidates]
    if not tickers: return []
    price_map, _ = trader.get_bulk_market_data(tickers)

    for c in candidates:
        ticker = c['ticker']
        is_held = ticker in live_tickers
        
        # Robust Score Extraction (Handled by history, but safe cast here)
        p_score = float(c.get('Position_Score', 0))
        s_score = float(c.get('Swing_Score', 0))

        # --- GATE: Threshold Check ---
        # "AND" Logic: Must meet BOTH thresholds OR be Held
        passes_threshold = (p_score >= pos_thresh and s_score >= swing_thresh)
        
        if passes_threshold or is_held:
            # Inject Price
            if ticker in price_map: 
                c['current_price'] = price_map[ticker]
            elif 'raw_data' in c:
                c['current_price'] = c['raw_data'].get('Price', 0)

            final_candidates.append(c)
            
            reason = "Held" if is_held else f"Scores {int(p_score)}/{int(s_score)}"
            log_pipeline(f"   ✅ {ticker}: PASSED ({reason})")

    return final_candidates

def enrich_and_sort_candidates(candidates):
    """Adds active position details, market data, and STRATEGY MEMORY."""
    holdings_map = {} 
    
    # Bulk Fetch Data
    all_tickers = [c['ticker'] for c in candidates]
    price_map, atr_map = trader.get_bulk_market_data(all_tickers)
    
    # --- 1. FETCH STRATEGY MEMORY (NEW) ---
    # This calls the helper in senior_history to see what we decided last time.
    # Returns: {'AAPL': 'Position Trading', 'TSLA': 'Swing Trading'}
    strategy_map = senior_history.fetch_active_strategies(all_tickers)

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
            # Assuming calculate_days_held is available in scope
            c['days_held'] = calculate_days_held(ticker, details) 
            holdings_map[ticker] = details['shares_held']
        else:
            c['shares_held'] = 0
            c['days_held'] = 0
            holdings_map[ticker] = 0

        # --- 2. INJECT MEMORY INTO CANDIDATE (NEW) ---
        # The Prompt reads 'current_active_strategy' from this exact key.
        if ticker in strategy_map:
            c['current_active_strategy'] = strategy_map[ticker]
        else:
            c['current_active_strategy'] = "NONE"

        enriched.append(c)

    # Sort: Holdings First, Then by Score (if available, else random/price)
    random.shuffle(enriched)
    enriched.sort(key=lambda x: (x['shares_held'] > 0, get_safe_score(x)), reverse=True)
    
    return enriched, holdings_map

# ==========================================
# 🛡️ HELPER: DATA SANITIZATION
# ==========================================
def safe_float(val):
    """
    Forces any input (String, Int, messy JSON) into a clean Float.
    Examples: "$150.00" -> 150.0, "150" -> 150.0, "[150]" -> 150.0
    """
    if val is None: return 0.0
    try:
        # If it's already a number, return it as float
        if isinstance(val, (int, float)): 
            return float(val)
            
        # Clean string artifacts
        clean = str(val).replace('$', '').replace(',', '').replace('[', '').replace(']', '').strip()
        
        if not clean: return 0.0
        return float(clean)
    except Exception:
        return 0.0

# ==========================================
# ⚙️ EXECUTION LOGIC (The Capital Guard)
# ==========================================
def execute_decisions(decision_payload):
    """
    Executes trades with Dynamic Capital Allocation based on Conviction.
    
    SCENARIO A (Position Only): 70% Capital, Wide Stops.
    SCENARIO B (Swing Only):    30% Capital, Tight Stops.
    SCENARIO C (Hybrid):       100% Capital, Wide Stops (Safety First).
    """
    orders = decision_payload.get('final_execution_orders', [])
    log_pipeline(f"⚙️ EXECUTION: Processing {len(orders)} orders with Capital Guard logic...")
    
    # Base Capital (The "Max" amount you would invest in a perfect trade)
    # Ensure this is set in your config.py, e.g., INVEST_PER_TRADE = 2000
    base_capital = getattr(config, 'INVEST_PER_TRADE', 1000)

    # 1. DEFINE THE ALLOCATION MAP
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
        
        # --- 2. SELECT PARAMETERS & CAPITAL ---
        # Logic: Pick the correct "Lens" (Dictionary) and Capital Multiplier
        
        alloc_mult = ALLOCATION_MAP.get(recommendation, 0.0)
        investment_amount = base_capital * alloc_mult
        
        # Default to Swing params, but override if Position/Hybrid
        target_dict = order.get('swing_trade_analysis', {}) # Default
        
        if recommendation == "POSITION_ONLY":
            log_pipeline(f"   🛡️ Mode: POSITION ONLY (70% Capital, Wide Stops)")
            target_dict = order.get('position_trade_analysis', {})
            
        elif recommendation == "HYBRID":
            log_pipeline(f"   🛡️ Mode: HYBRID (100% Capital, Wide Stops)")
            # "Hybrid trades always default to Safety (Position stops)"
            target_dict = order.get('position_trade_analysis', {})
            
        elif recommendation == "SWING_ONLY":
            log_pipeline(f"   ⚔️ Mode: SWING ONLY (30% Capital, Tight Stops)")
            target_dict = order.get('swing_trade_analysis', {})

        # Extract Execution Plan from the selected dictionary
        plan = target_dict.get('execution_plan', {})
        
        # Sanitize Inputs (Prevent the '>' int vs str error)
        entry_price = safe_float(plan.get('entry_price'))
        take_profit = safe_float(plan.get('take_profit'))
        stop_loss   = safe_float(plan.get('stop_loss'))

        log_pipeline(f"   👉 {ticker} Action: {action} | Alloc: ${investment_amount:.0f} ({alloc_mult*100}%)")

        try:
            # --- 3. EXECUTE BASED ON ACTION ---
            
            if action == "OPEN_NEW":
                # Capital Guard: Cannot buy if allocation is 0
                if investment_amount <= 0:
                    log_pipeline(f"      ⛔ Skipped {ticker}: Allocation is $0 (AVOID/Unknown).")
                    continue
                    
                trader.execute_entry(
                    ticker, 
                    investment_amount, # Dynamic Amount
                    entry_price,       # Limit Price from selected strategy
                    take_profit, 
                    stop_loss
                )

            elif action == "UPDATE_EXISTING":
                # Risk Management: Update Safety Nets ONLY. Do not buy more.
                trader.execute_update(
                    ticker, 
                    take_profit, 
                    stop_loss, 
                    buy_limit=entry_price # Updates entry if still pending
                )

            elif action == "CANCEL_PENDING":
                trader.execute_cancel(ticker)
                


            elif action == "CLOSE_POSITION":
                log_pipeline(f"      🚨 EJECTING {ticker} (Score too low).")
                trader.close_full_position(ticker)

            elif action == "HOLD":
                log_pipeline(f"      ⏸️ Holding {ticker}. No changes.")

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
    
    # ✅ FIX: Renamed 'fresh_candidates' to match logic
    priority_candidates = junior_history.filter_candidates(distressed_tickers, limit=limit)
    log_pipeline(f"Filtered to {len(priority_candidates)} fresh candidates.")

    analyzed_count = 0
    
    # ✅ NEW: We must split the Dual JSON into separate objects for the Senior Agent
    # This list will be used if we want to pass data to Senior Phase immediately (optional)
    # For now, we mainly log to history.
    
    for ticker in priority_candidates:
        current_price = trader.get_current_price(ticker)
        if not current_price: continue
        
        # 1. Call Junior
        report = junior_agent.analyze_stock(ticker, current_price)
        
        if report:
            # 2. Log to History (Handles the 2 rows writing)
            junior_history.log_report(ticker, report)
            analyzed_count += 1
            
            # Note: The Senior Phase currently reads from History or Live Portfolio.
            # If you want Senior to immediately trade these, we would append to a list here.
            # But based on your architecture, Senior reads from 'filter_candidates' which reads history.
            
            log_pipeline(f"   ✅ Dual Report logged for {ticker}")
            
    log_pipeline(f"   Phase 1 Complete. {analyzed_count} reports generated.")


# ==========================================
# 👨‍💼 PHASE 2: SENIOR MANAGER (SERIAL MODE)
# ==========================================

def run_senior_phase():
    log_pipeline("\n👨‍💼 PHASE 2: SENIOR MANAGER STRATEGY (SERIAL MODE)")
    try:
        live_tickers = get_live_context()
        final_candidates = filter_candidates(live_tickers)
        
        if not final_candidates:
            log_pipeline("📉 No candidates found. Stopping Senior Phase.")
            return

        sorted_candidates, holdings_map = enrich_and_sort_candidates(final_candidates)
        
        # Blind Data
        #blinded_candidates = copy.deepcopy(sorted_candidates)
        #for c in blinded_candidates:
        #    c['avg_entry_price'] = "HIDDEN"
        #    c['days_held'] = "HIDDEN"

        risk_instruction = driver_fox.FOX_DRIVER_PROMPT

        log_pipeline(f"🤖 Starting SERIAL analysis of {len(sorted_candidates)} candidates...")
        
        all_dual_orders = []
        
        # ... inside run_senior_phase in routes.py ...

        for i, candidate in enumerate(sorted_candidates):
            ticker = candidate.get('ticker')
            log_pipeline(f"   👉 [{i+1}/{len(sorted_candidates)}] Analyzing {ticker}...")
            
            # CALL SINGLE TICKER FUNCTION
            result = senior_agent.analyze_single_ticker(
                candidate, 
                risk_factor=risk_instruction
            )
            
            # ✅ FIX: UNWRAP THE AI RESPONSE
            # The AI returns: { "final_execution_orders": [ {TARGET DATA} ] }
            # We need to grab {TARGET DATA} and throw away the wrapper.
            
            if result and 'final_execution_orders' in result:
                inner_orders = result['final_execution_orders']
                
                if isinstance(inner_orders, list) and len(inner_orders) > 0:
                    # Take the first (and only) item from the list
                    clean_order = inner_orders[0]
                    
                    # Double check it has the keys we need
                    if 'ticker' in clean_order:
                        all_dual_orders.append(clean_order)
                    else:
                        log_pipeline(f"   ⚠️ Result for {ticker} missing 'ticker' key.")
                else:
                     log_pipeline(f"   ⚠️ Result for {ticker} had empty order list.")
            else:
                log_pipeline(f"   ⚠️ Failed to analyze {ticker}. Skipping.")
                
            time.sleep(1)

        if not all_dual_orders:
            log_pipeline("❌ Senior Agent returned NO valid orders. Aborting.")
            return

        # Create Consolidated Payload
        # We assume 'all_dual_orders' IS the 'final_execution_orders' list
        consolidated_decision = {
            "ceo_report": f"Session Complete. Analyzed {len(final_candidates)} assets. {len(all_dual_orders)} reports generated.",
            "final_execution_orders": all_dual_orders
        }

        # Logging & Execution
        senior_history.log_strategy(consolidated_decision)
        senior_history.log_detailed_decisions(consolidated_decision, holdings_map)
        
        print("\n" + "="*80)
        print("📢  EXECUTIVE STRATEGY BRIEF (CONSOLIDATED)  📢")
        print("="*80)
        print(consolidated_decision.get('ceo_report'))

        senior_agent.visualize_decision(final_candidates, consolidated_decision)
        
        execute_decisions(consolidated_decision)
        
        # =========================================================
        # 📧 EMAIL BLOCK (Make sure this exists!)
        # =========================================================
        try:
            print("   📧 Preparing Email Notification...") # <--- Added debug print
            
            # Fetch fresh account data for the email
            account_info = trader.get_account()
            portfolio_objects = trader.get_portfolio()
            refresh_portfolio_data(portfolio_objects) # Get live prices
            
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