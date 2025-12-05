from flask import Blueprint, jsonify, request
import threading
import config
import sys, os 
import time 
import textwrap

# --- Add root folder to path to import 'lib' ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SCRIPT_DIR)
sys.path.append(parent_dir)

import lib.good_value_quick_money_alpaca_trader as gv_trader
from lib.good_value_quick_money_market_scanner import find_distressed_stocks
# Import the new logging function
from lib.good_value_quick_money_history_manager import filter_candidates, log_decision_to_sheet
from lib.good_value_quick_money_gemini_agent import analyze_stock

from lib.live_data_loader import get_24h_summary_score_gemini

main_routes = Blueprint('main_routes', __name__)

# --- HELPER: Fixed ASCII Table ---
def print_analysis_table(data):
    ticker = data.get("ticker", "N/A")
    action = data.get("action", "N/A")
    conf = data.get("confidence", "N/A")
    
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    
    color = GREEN if action == "BUY" else RED
    if action == "WATCH" or conf == "LOW": color = YELLOW

    ex = data.get("execution", {})

    # Fixed width for stability
    print(f"\n{BOLD}╔════════════════════════════════════════════════════════════╗{RESET}")
    print(f"║ {BOLD}ANALYSIS REPORT:{RESET} {ticker:<37} ║")
    print(f"╠════════════════════════════════════════════════════════════╣")
    print(f"║ ACTION: {color}{action:<10}{RESET} | CONFIDENCE: {conf:<17} ║")
    print(f"╟────────────────────────────────────────────────────────────╢")
    print(f"║ Status:   {data.get('status', 'N/A'):<45}║")
    print(f"║ Value:    {data.get('valuation', 'N/A'):<45}║")
    print(f"║ Rebound:  {data.get('rebound_potential', 'N/A'):<45}║")
    print(f"╠════════════════════════════════════════════════════════════╣")
    print(f"║ {BOLD}EXECUTION PLAN{RESET}                                             ║")
    print(f"║ • Buy Limit:   ${float(ex.get('buy_limit', 0)):<35.2f} ║")
    print(f"║ • Take Profit: ${float(ex.get('take_profit', 0)):<35.2f} ║")
    print(f"║ • Stop Loss:   ${float(ex.get('stop_loss', 0)):<35.2f} ║")
    print(f"╚════════════════════════════════════════════════════════════╝")

    def print_text(title, text):
        if not text: return
        print(f"\n{BOLD}{CYAN}{title}:{RESET}")
        # Wrap at 60 chars to fit nicely in most logs
        for line in textwrap.wrap(str(text), width=60):
            print(f"  {line}")

    print_text("🧠 REASONING", data.get('reasoning'))
    print_text("🕵️ CRITICAL INTEL", data.get('intel'))
    print("-" * 60)

# ----------------------------------------------------
# ROUTE 2: GOOD VALUE QUICK MONEY BOT
# ----------------------------------------------------
def run_good_value_quick_money_scan():
    print("\n" + "█"*60)
    print("🚀 [GOOD VALUE BOT] STARTING DAILY SCAN")
    print("█"*60 + "\n")

    # --- THIS IS THE FIX ---
    # Check if market is open BEFORE doing anything else.
    #if not gv_trader.is_market_open():
    #    print("💤 Market is closed. Skipping scan to save API credits.")
    #    print("="*60 + "\n")
    #    return
    # --- END OF FIX ---
    
    try:
        candidates = find_distressed_stocks()
        if not candidates:
            print("😴 No distressed stocks found.")
            return

        limit = getattr(config, 'DAILY_SCAN_LIMIT', 18)
        to_analyze = filter_candidates(candidates, limit)
        
        if not to_analyze:
            print("🕒 All candidates are on cooldown.")
            return

        print(f"\n🧠 Analyzing {len(to_analyze)} tickers...")
        
        trades_placed = 0
        
        for ticker in to_analyze:
            try:
                current_price = gv_trader.get_current_price(ticker)
                if not current_price:
                    print(f"   ⚠️ Skipping {ticker}: No price.")
                    continue
                
                result = analyze_stock(ticker, current_price) 
                
                # Default trade status
                trade_status = "ANALYZED_ONLY"
                trade_details = {"qty": 0, "cost": 0}

                if result:
                    print_analysis_table(result)
                    
                    action = result.get('action')
                    status = result.get('status')
                    conf = result.get('confidence')
                    valuation = result.get('valuation')
                    rebound = result.get('rebound_potential')

                    # EXECUTE LOGIC
                    if (action == "BUY" and status == "SAFE" and 
                        valuation == "BARGAIN" and rebound == "HIGH" and 
                        conf == "HIGH"):
                        
                        print(f"   🚨 HIGH CONVICTION SIGNAL! Executing...")
                        
                        exec_plan = result.get('execution', {})
                        invest_amt = getattr(config, 'INVEST_PER_TRADE', 10)
                        
                        trade = gv_trader.place_smart_trade(
                            ticker, 
                            invest_amt,
                            exec_plan.get('buy_limit'),
                            exec_plan.get('take_profit'),
                            exec_plan.get('stop_loss')
                        )
                        
                        if trade: 
                            trades_placed += 1
                            trade_status = "ORDER_PLACED"
                            # Calculate estimated qty based on limit price
                            limit_price = float(exec_plan.get('buy_limit'))
                            qty = int(invest_amt / limit_price)
                            trade_details = {"qty": qty, "cost": qty * limit_price}
                        else:
                            trade_status = "FAILED_ORDER"
                    else:
                         trade_status = "SKIPPED_CRITERIA"
                         print(f"   ✋ Criteria not met (Status: {status}, Val: {valuation})")

                    # --- LOG TO GOOGLE SHEETS ---
                    log_decision_to_sheet(ticker, result, trade_status, trade_details)
                    # ----------------------------

                else:
                    print(f"   ℹ️ No insight for {ticker}.")
            
            except Exception as e:
                print(f"   ❌ Error processing {ticker}: {e}")
                continue

            time.sleep(5) 
            
        print("\n" + "="*60)
        print(f"🏁 SCAN COMPLETE. Trades: {trades_placed}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ CRITICAL FAILURE IN SCAN JOB: {e}")


@main_routes.route('/tradingbot')
def trigger_good_value_quick_money_scan():
    print("--- /tradingbot route hit! ---")
    thread = threading.Thread(target=run_good_value_quick_money_scan)
    thread.start()
    return jsonify(status="good_value_quick_money_scan_started"), 202

# ... (Health/Webhook unchanged) ...
@main_routes.route('/health')
def health_check():
    return jsonify(status="ok"), 200
@main_routes.route('/webhook', methods=['POST'])
def handle_tradingview_webhook():
    return jsonify(status="webhook_received"), 200
if __name__ == "__main__":
    app = Flask(__name__)
    app.register_blueprint(main_routes)
    app.run(host='0.0.0.0', port=10000)