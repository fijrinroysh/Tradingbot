from flask import Blueprint, jsonify, request
import threading
import config
import sys, os 
import time 
import textwrap # <-- Added for nice text formatting

# --- Add root folder to path to import 'lib' ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SCRIPT_DIR)
sys.path.append(parent_dir)

# --- Import the modules for the "Good Value Quick Money" Strategy ---
import lib.good_value_quick_money_alpaca_trader as gv_trader
from lib.good_value_quick_money_market_scanner import find_distressed_stocks
from lib.good_value_quick_money_history_manager import filter_candidates, mark_as_analyzed
from lib.good_value_quick_money_gemini_agent import analyze_stock

# --- Import Legacy modules ---
from lib.live_data_loader import get_24h_summary_score_gemini

main_routes = Blueprint('main_routes', __name__)

# --- HELPER: ASCII Table Printer (Enhanced) ---
def print_analysis_table(data):
    """Prints a beautiful summary of the analysis for logs."""
    ticker = data.get("ticker", "N/A")
    action = data.get("action", "N/A")
    confidence = data.get("confidence", "N/A")
    
    # ANSI Colors
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    
    color = GREEN if action == "BUY" else RED
    if action == "WATCH" or confidence == "LOW": color = YELLOW

    exec_data = data.get("execution", {})
    buy = exec_data.get("buy_limit", 0)
    tp = exec_data.get("take_profit", 0)
    sl = exec_data.get("stop_loss", 0)

    # 1. Print the Summary Table
    print(f"""
{BOLD}╔════════════════════════════════════════════════════════════════════════╗{RESET}
║  {BOLD}ANALYSIS:{RESET} {ticker:<54} ║
╠══════════════════════════════╦═════════════════════════════════════════╣
║  ACTION: {color}{action:<20}{RESET}║  CONFIDENCE: {confidence:<21} ║
╠══════════════════════════════╬═════════════════════════════════════════╣
║  Status:    {data.get('status', 'N/A'):<17}║  Valuation:  {data.get('valuation', 'N/A'):<21} ║
║  Rebound:   {data.get('rebound_potential', 'N/A'):<17}║                                      ║
╠══════════════════════════════╩═════════════════════════════════════════╣
║  {BOLD}EXECUTION PLAN{RESET}                                                        ║
║  • Buy Limit:   ${buy:<53.2f} ║
║  • Take Profit: ${tp:<53.2f} ║
║  • Stop Loss:   ${sl:<53.2f} ║
╚════════════════════════════════════════════════════════════════════════╝""")

    # 2. Print Full Text Sections Below
    
    # Helper to wrap text nicely
    def print_section(title, text):
        if not text: return
        print(f"\n{BOLD}{CYAN}{title}:{RESET}")
        # Wrap text to 80 characters so it doesn't scroll off screen in logs
        wrapped_lines = textwrap.wrap(str(text), width=80)
        for line in wrapped_lines:
            print(f"  {line}")

    print_section("🧠 FULL REASONING", data.get('reasoning'))
    print_section("🕵️ CRITICAL INTEL", data.get('intel'))
    print("\n" + "-"*80 + "\n")

# ----------------------------------------------------
# ROUTE 1: HEALTH CHECK
# ----------------------------------------------------
@main_routes.route('/health')
def health_check():
    return jsonify(status="ok"), 200

# ----------------------------------------------------
# ROUTE 2: GOOD VALUE QUICK MONEY BOT
# ----------------------------------------------------
def run_good_value_quick_money_scan():
    print("\n" + "█"*60)
    print("🚀 [GOOD VALUE BOT] STARTING DAILY SCAN")
    print("█"*60 + "\n")
    
    try:
        # 1. SCAN
        candidates = find_distressed_stocks()
        if not candidates:
            print("😴 No distressed stocks found today.")
            return

        # 2. FILTER (History)
        limit = getattr(config, 'DAILY_SCAN_LIMIT', 18)
        to_analyze = filter_candidates(candidates, limit)
        
        if not to_analyze:
            print("🕒 All candidates are on cooldown. No new work.")
            return

        print(f"\n🧠 Analyzing {len(to_analyze)} tickers...")
        
        trades_placed = 0
        
        # 3. ANALYZE & TRADE
        for ticker in to_analyze:
            try:
                # A. Get Price
                current_price = gv_trader.get_current_price(ticker)
                
                if not current_price:
                    print(f"   ⚠️ Skipping {ticker}: Could not fetch price.")
                    continue
                
                # B. Analyze (Gemini)
                result = analyze_stock(ticker, current_price) 
                mark_as_analyzed(ticker) 
                
                if result:
                    # Print the beautiful, full logs
                    print_analysis_table(result)
                    
                    action = result.get('action')
                    
                    status = result.get('status')
                    valuation = result.get('valuation')
                    rebound_potential = result.get('rebound_potential')
                    confidence = result.get('confidence')
                    
                    # C. Execute
                    if action == "BUY" and  status == "SAFE" and valuation == "BARGAIN" and rebound_potential == "HIGH" and confidence == "HIGH":
                        print(f"   🚨 HIGH CONVICTION SIGNAL! Executing Trade...")
                        
                        exec_plan = result.get('execution', {})
                        
                        trade = gv_trader.place_smart_trade(
                            ticker, 
                            getattr(config, 'INVEST_PER_TRADE', 5000),
                            exec_plan.get('buy_limit'),
                            exec_plan.get('take_profit'),
                            exec_plan.get('stop_loss')
                        )
                        if trade: trades_placed += 1
                else:
                    print(f"   ℹ️ No actionable insight for {ticker}.")
            
            except Exception as e:
                print(f"   ❌ Error processing {ticker}: {e}")
                continue

            # Rate Limit Sleep
            time.sleep(5) 
            
        print("\n" + "="*60)
        print(f"🏁 SCAN COMPLETE. Trades Executed: {trades_placed}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ CRITICAL FAILURE IN SCAN JOB: {e}")


@main_routes.route('/tradingbot')
def trigger_good_value_quick_money_scan():
    """
    Triggered by UptimeRobot once per day.
    """
    print("--- /tradingbot route hit! Starting background job... ---")
    thread = threading.Thread(target=run_good_value_quick_money_scan)
    thread.start()
    return jsonify(status="good_value_quick_money_scan_started"), 202

# ----------------------------------------------------
# ROUTE 3: WEBHOOK (Legacy)
# ----------------------------------------------------
@main_routes.route('/webhook', methods=['POST'])
def handle_tradingview_webhook():
    return jsonify(status="webhook_received"), 200

# ----------------------------------------------------
if __name__ == "__main__":
    print("Starting Flask server for local testing...")
    app = Flask(__name__)
    app.register_blueprint(main_routes)
    app.run(host='0.0.0.0', port=10000)