from flask import Blueprint, jsonify
import threading
import time
import config
import sys, os
import datetime
import copy
import json

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

main_routes = Blueprint('main_routes', __name__)

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

def run_pipeline():
    print("\n" + "="*60)
    log_pipeline("🚀 STARTING DAILY TRADING PIPELINE (PRODUCTION)")
    print("="*60)
    
    # 1. MARKET CHECK
    # if not trader.is_market_open():
    #    log_pipeline("💤 Market Closed. Aborting.")
    #    return
                
    # --- JUNIOR PHASE ---
    log_pipeline("🕵️ PHASE 1: JUNIOR ANALYST RESEARCH")
    
    try:
        candidates = scanner.find_distressed_stocks()
        log_pipeline(f"Scanner found {len(candidates)} raw candidates.")
        
        limit = getattr(config, 'DAILY_SCAN_LIMIT', 20)
        fresh_candidates = junior_history.filter_candidates(candidates, limit=limit)
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

    # --- SENIOR PHASE ---
    log_pipeline("\n👨‍💼 PHASE 2: SENIOR MANAGER STRATEGY")
    
    # [RESTORED] PRODUCTION SAFETY WRAPPER 
    try:
        # 2. FETCH DATA
        lookback = getattr(config, 'SENIOR_LOOKBACK_DAYS', 10)
        reports = senior_history.fetch_junior_reports(lookback)
        log_pipeline(f"Fetched {len(reports)} total reports from history (Last {lookback} days).")
        
        # --- LOGIC FIX: PORTFOLIO INJECTION ---
        # 1. Get Live Holdings (The "Must Manage" List)                                                                       
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

        # 2. FILTER CANDIDATES
        final_candidates = []
        seen_tickers = set()
        
        log_pipeline(f"Applying filters: Score > 85 AND Price < 250 SMA (Unless Held)...")

        for raw_report in reports:
            ticker = raw_report.get('ticker')
            score = get_safe_score(raw_report)
            is_held = ticker in live_tickers
            
            # --- BIAS REMOVAL: CLEAN SLATE PROTOCOL ---
            r = copy.deepcopy(raw_report)

            keys_to_remove = [
                'recommended_action',  # REMOVE: Don't tell Senior to "BUY"
                'junior_targets',      # REMOVE: Prevent Price Anchoring
                'conviction_score',    # REMOVE: Arbitrary number
                'audit_reason',        # REMOVE: System noise
                'sector',
                'status_reason',
                'valuation_reason',
                'rebound_reason'
            ]
            for k in keys_to_remove:
                if k in r: del r[k]
            # -----------------------------------------     

            # ---------------------------------------------------------
            # CRITERIA 1: ACTIVE HOLDINGS (The "Must Manage" Override)
            # ---------------------------------------------------------                                                            
            if is_held:
                if ticker not in seen_tickers:
                    final_candidates.append(r)
                    seen_tickers.add(ticker)
                    log_pipeline(f"   ✅ Auto-Included {ticker} (Portfolio Review)")
                continue 

            # ---------------------------------------------------------
            # CRITERIA 2: HIGH CONVICTION SCORE (>88)
            # ---------------------------------------------------------                                                                                                                                                                          
            if score <= 88:
                continue 
                
            # ---------------------------------------------------------
            # CRITERIA 3: PRICE BELOW 250-DAY MOVING AVERAGE
            # ---------------------------------------------------------
            current_price = trader.get_current_price(ticker)
            sma_250 = trader.get_simple_moving_average(ticker, window=250)
            
            if current_price and sma_250:
                if current_price < sma_250:
                    if ticker not in seen_tickers:
                        final_candidates.append(r)
                        seen_tickers.add(ticker)
                else:
                    log_pipeline(f"   📉 Rejecting {ticker}: Price ${current_price} is ABOVE 250 SMA (${sma_250:.2f}).")
            else:
                log_pipeline(f"   ⚠️ Skipping {ticker}: Could not verify SMA compliance.")
        
        log_pipeline(f"Senior Agent will review {len(final_candidates)} candidates.")
        
        if not final_candidates:
            log_pipeline("📉 No candidates found. Stopping Senior Phase.")
            return

        # 3. INJECT LIVE CONTEXT (THE UPGRADE)
        log_pipeline(f"Fetching Live Data & X-Ray Context for {len(final_candidates)} candidates...")
            
        # [NEW] Fetch Yesterday's Ranks -----------------------------
        previous_ranks = senior_history.fetch_latest_ranks() 
        # -----------------------------------------------------------

        holdings_map = {} 
        
        for c in final_candidates:
            ticker = c['ticker']
            c['current_price'] = trader.get_current_price(ticker)
            
            # [NEW] Inject Previous Rank ----------------------------
            # If it wasn't ranked yesterday, we label it "Unranked"
            c['previous_rank'] = previous_ranks.get(ticker, "Unranked")
            # -------------------------------------------------------
            # --- RICH DATA FETCH ---
            if hasattr(trader, 'get_position_details'):
                details = trader.get_position_details(ticker)
                
                c['shares_held'] = details['shares_held']
                c['avg_entry_price'] = details['avg_entry_price'] 
                c['current_active_tp'] = details['active_tp']
                c['current_active_sl'] = details['active_sl']
                c['pending_buy_limit'] = details['pending_buy_limit']
                
                holdings_map[ticker] = details['shares_held']
                
                if details['status_msg'] != "NONE":
                    log_pipeline(f"   ℹ️ [CONTEXT] {ticker}: {details['status_msg']}")
            else:
                c['shares_held'] = trader.get_position(ticker)
                holdings_map[ticker] = c['shares_held']
    # --- 🐛 DEBUG DUMP: RAW BRAIN INPUT ---
    # This prints exactly what the Senior Manager sees before it thinks.
    #print("\n" + ">"*20 + " [DEBUG] RAW SENIOR INPUT " + "<"*20)
    #print(json.dumps(final_candidates, indent=2, default=str))
    #print(">"*20 + " [END DEBUG] " + "<"*20 + "\n")
    # --------------------------------------
        # 4. STRATEGY & DECISION
        log_pipeline("Calling Senior Agent AI for ranking...")
        context = senior_history.get_last_strategy()
        
        decision = senior_agent.rank_portfolio(
            final_candidates, 
            top_n=getattr(config, 'SENIOR_TOP_PICKS', 5),
            prev_context=context
        )
        
        if decision:
            # Log to Sheets
            senior_history.log_strategy(decision)
            senior_history.log_detailed_decisions(decision, holdings_map)
            
            print("\n" + "="*80)
            print("📢  EXECUTIVE STRATEGY BRIEF  📢")
            print("="*80)
            print(decision.get('ceo_report'))
            
            # 5. EXECUTE TRADES
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
                        trade_events = trader.execute_entry(
                            ticker, config.INVEST_PER_TRADE, 
                            p.get('buy_limit', 0), p.get('take_profit', 0), p.get('stop_loss', 0)
                        )
                    elif action == "UPDATE_EXISTING":
                        trade_events = trader.execute_update(
                            ticker, p.get('take_profit', 0), p.get('stop_loss', 0), buy_limit=p.get('buy_limit', 0)
                        )
                    elif action == "HOLD":
                        log_pipeline(f"      ✋ Holding {ticker} (No Action Taken).")
                        continue
                    else:
                        log_pipeline(f"      ⚠️ Unknown Action '{action}' - Skipping.")
                except Exception as e:
                    log_pipeline(f"      ❌ Execution Exception for {ticker}: {e}")

                if isinstance(trade_events, dict): trade_events = [trade_events]
                for event in trade_events:
                    if isinstance(event, dict):
                        evt_type = event.get('event', 'UNKNOWN')
                        if evt_type not in ["HOLD", "ERROR"]:
                            senior_history.log_trade_event(ticker, evt_type, event)
                            log_pipeline(f"      ✅ Event Logged: {evt_type}")
                        elif evt_type == "ERROR":
                            log_pipeline(f"      ❌ Error Event: {event.get('info')}")

            # 6. SEND EMAIL
            log_pipeline("\n📧 PHASE 4: NOTIFICATION")
            try:
                # 1. Fetch Account Info                       
                account_info = trader.trading_client.get_account()
                
                # 2. Fetch Live Portfolio (Mirror Protocol)                                           
                portfolio = trader.trading_client.get_all_positions()
                
                # 3. Send Brief               
                notifier.send_executive_brief(decision, account_info, reports, portfolio)

                log_pipeline("✅ Executive Brief email dispatched.")
            except Exception as e:
                log_pipeline(f"❌ Failed to send email: {e}")

    except Exception as e:
        log_pipeline(f"❌ CRITICAL ERROR in Senior Phase: {e}")

    print("\n" + "="*80)
    log_pipeline("✅ PIPELINE COMPLETE. Check Sheets & Email.")
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