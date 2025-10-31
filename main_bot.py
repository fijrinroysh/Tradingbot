from flask import Flask
from routes import main_routes  # <-- Import the Blueprint from your routes.py file

# Create the app instance
app = Flask(__name__)

# Register all the routes from routes.py with our app
app.register_blueprint(main_routes)

# This block still runs the server when you run "python main_bot.py" locally
# or when Gunicorn runs it on Render.
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)