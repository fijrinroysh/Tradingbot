from flask import Flask
from routes import main_routes  # <-- Import the Blueprint from your routes.py file
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

# Register all the routes from routes.py with our app
app.register_blueprint(main_routes)

# This block still runs the server when you run "python main_bot.py" locally
# or when Gunicorn runs it on Render.
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)