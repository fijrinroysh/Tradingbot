from flask import Blueprint, jsonify
import threading
import time
import config
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SCRIPT_DIR)
sys.path.append(parent_dir)

import lib.good_value_quick_money_market_scanner as scanner
import lib.gvqm_alpaca_trader as trader
import lib.gvqm_junior_agent as junior_agent
import lib.gvqm_junior_history as junior_history
import lib.gvqm_senior_agent as senior_agent
import lib.gvqm_senior_history as senior_history
import lib.gvqm_email_notifier as notifier

main_routes = Blueprint('main_routes', __name__)

def run_pipeline():
    print("🚀 [BOT] Starting Daily Pipeline")
    
    #if not trader.is_market_open():
    #    print("💤 Market Closed.")
    #    return

    # --- JUNIOR PHASE ---
    print("\n🕵️ [JUNIOR] Starting Research...")
    candidates = scanner.find_distressed_stocks()
    limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
    print(f"⚙️ Applying Daily Scan Limit: {limit}")
    fresh_candidates = junior_history.filter_candidates(candidates, limit=limit)
    
    for ticker in fresh_candidates:
        price = trader.get_current_price(ticker)
        if not price: continue
        report = junior_agent.analyze_stock(ticker, price)
        if report:
            junior_history.log_report(ticker, report)
        time.sleep(2)

    # --- SENIOR PHASE ---
    print("\n👨‍💼 [SENIOR] Starting Strategy Review...")
    
    # 1. Get Data
    reports = senior_history.fetch_junior_reports(getattr(config, 'SENIOR_LOOKBACK_DAYS', 10))
    high_conviction = [r for r in reports if int(r.get('conviction_score', 0)) >= 85]
    
    if not high_conviction:
        print("📉 No high-conviction candidates found.")
        return

# 2. INJECT LIVE CONTEXT (Price + Holdings + PENDING ORDERS)
    print(f"   > Fetching Live Data (Price & Holdings) for {len(high_conviction)} candidates...")
    holdings_map = {} 
    
    for c in high_conviction:
        ticker = c['ticker']
        c['current_price'] = trader.get_current_price(ticker)
        
        # Check holdings
        qty = trader.get_position(ticker)
        c['shares_held'] = qty
        holdings_map[ticker] = qty
        
        # --- NEW: Check Pending Orders ---
        pending_status = trader.get_pending_order_status(ticker)
        if pending_status:
            c['pending_orders'] = pending_status
            print(f"     ℹ️ Context {ticker}: {pending_status}")
        
        if qty > 0:
            print(f"     ℹ️ Context {ticker}: We hold {qty} shares.")

    # 3. Get Context & Analyze
    context = senior_history.get_last_strategy()
    decision = senior_agent.rank_portfolio(
        high_conviction, 
        top_n=getattr(config, 'SENIOR_TOP_PICKS', 5),
        prev_context=context
    )
    
    if decision:
        # 4. LOGGING (Double-Decker)
        # A. The Morning Newspaper (Markdown Summary)
        senior_history.log_strategy(decision)
        
        # B. The Database Ledger (Structured Rows) <--- NEW CALL
        senior_history.log_detailed_decisions(decision, holdings_map)
        
        print("\n" + "="*80)
        print("📢  EXECUTIVE STRATEGY BRIEF  📢")
        print("="*80)
        print(decision.get('ceo_report'))
        
# 5. EXECUTE & LOG TRADES (Updated)
        print(f"\n⚡ Processing Senior Manager Commands...")
        
        for order in decision.get('final_execution_orders', []):
            ticker = order.get('ticker')
            action = order.get('action', 'HOLD').upper() # OPEN_NEW or UPDATE_EXISTING
            p = order.get('confirmed_params', {})
            
            trade_events = []
            
            # --- COMMAND DISPATCHER ---
            if action == "OPEN_NEW":
                # Senior Manager says BUY. We BUY.
                trade_events = trader.execute_entry(
                    ticker, 
                    config.INVEST_PER_TRADE, 
                    p.get('buy_limit', 0), 
                    p.get('take_profit', 0), 
                    p.get('stop_loss', 0)
                )
                
            elif action == "UPDATE_EXISTING":
                # Senior Manager says UPDATE. We UPDATE.
                # Note: We do NOT pass buy_limit here, avoiding the ZeroDivisionError.
                trade_events = trader.execute_update(
                    ticker,
                    p.get('take_profit', 0), 
                    p.get('stop_loss', 0)
                )
                
            elif action == "HOLD":
                print(f"   ✋ Holding {ticker} (No Action).")
                continue
                
            else:
                print(f"   ⚠️ Unknown Action '{action}' for {ticker}")

            # --- LOGGING (Same as before) ---
            # (Check for Raw Objects or Lists and log to Sheets)
            if hasattr(trade_events, 'id'): trade_events = [{"event": "NEW_ENTRY", "info": "Recovered", "order_id": str(trade_events.id)}]
            if isinstance(trade_events, dict): trade_events = [trade_events]
            
            for event in trade_events:
                if isinstance(event, dict):
                    evt_type = event.get('event', 'UNKNOWN')
                    if evt_type not in ["HOLD", "ERROR"]:
                        senior_history.log_trade_event(ticker, evt_type, event)
                    elif evt_type == "ERROR":
                        print(f"   ❌ Execution Error for {ticker}: {event.get('info')}")

# 6. SEND EXECUTIVE BRIEF (NEW SECTION)
    print("\n📧 Generating Executive Brief...")
    try:
        # Fetch latest account data from Alpaca
        account_info = trader.trading_client.get_account()
        
        # Send the email with: Decision, Account Data, and Junior Reports
        notifier.send_executive_brief(decision, account_info, reports)
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETE. Check Sheets & Email.")
    print("="*80 + "\n")

    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETE. Check Sheets: 'Trade_Log', 'Senior_Decisions', 'Executive_Briefs'")
    print("="*80 + "\n")

@main_routes.route('/tradingbot')
def trigger_scan():
    thread = threading.Thread(target=run_pipeline)
    thread.start()
    return jsonify(status="pipeline_started"), 202

@main_routes.route('/health')
def health_check(): return jsonify(status="ok"), 200

@main_routes.route('/webhook', methods=['POST'])
def handle_webhook(): return jsonify(status="received"), 200