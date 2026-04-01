from flask import Flask, jsonify, request
import threading
import datetime
import logging

# ==========================================
# 🛑 CUSTOM LOG FILTER FOR HEALTH CHECKS
# ==========================================
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        # If the log message contains "/health", drop it completely
        return "/health" not in record.getMessage()

# Create the app instance
app = Flask(__name__)

# Apply the filter to Flask's default logger (for local dev)
logging.getLogger("werkzeug").addFilter(HealthCheckFilter())
# Apply the filter to Gunicorn's access logger (for Render production)
logging.getLogger("gunicorn.access").addFilter(HealthCheckFilter())

# ==========================================
# 🔒 CONCURRENCY LOCK
# ==========================================
pipeline_lock = threading.Lock()
is_pipeline_running = False

# ==========================================
# 🌐 THE LIGHTWEIGHT DOORMAN (ROUTES)
# ==========================================

@app.route('/health')
def health_check():
    # Instantly returns 200 OK in ~3 seconds. No heavy libraries required.
    return jsonify(status="ok"), 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    return jsonify(status="received"), 200

@app.route('/tradingbot')
def trigger_scan():
    global is_pipeline_running
    
    # 1. Check if the bot is already running
    if is_pipeline_running:
        return jsonify({
            "status": "ignored", 
            "message": "Pipeline is already running. Please wait for it to finish.",
            "timestamp": datetime.datetime.now()
        }), 429 

    # 2. Wrap the pipeline in the background thread
    def locked_background_execution():
        global is_pipeline_running
        with pipeline_lock:
            is_pipeline_running = True
            try:
                print("Background thread started. Loading heavy libraries now...")
                
                # 🛑 THE LAZY LOAD MAGIC 🛑
                # By importing routes down here, the 90-second Pandas/Gemini load 
                # happens in the background, completely hidden from cron-job.org!
                import routes 
                routes.run_pipeline()
                
            except Exception as e:
                print(f"❌ CRITICAL ERROR in background execution: {e}")
                import traceback
                traceback.print_exc()
            finally:
                is_pipeline_running = False

    # 3. Start the protected background thread
    thread = threading.Thread(target=locked_background_execution)
    thread.start()
    
    # 4. Instantly hang up the phone with cron-job so it doesn't time out
    return jsonify({
        "status": "success", 
        "message": "Pipeline triggered successfully. Booting heavy AI libraries...", 
        "timestamp": datetime.datetime.now()
    }), 200

# ==========================================
# 🚀 LAUNCH THE SERVER
# ==========================================
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)