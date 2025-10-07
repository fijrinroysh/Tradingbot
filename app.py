from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

ALPACA_API_KEY = 'PKWMQDBXMMYIUO61F9X4'
ALPACA_SECRET_KEY = 'KYfU5eXz4oMhcTdwouYEiDKfKElOoW2S034I4tSU'
BASE_URL = 'https://paper-api.alpaca.markets'

# ----------------------------------------------------
# This route for the health check ✅
# ----------------------------------------------------
@app.route('/health')
def health_check():
    """
    This endpoint is used by keep-alive services like UptimeRobot
    to confirm the app is running.
    """
    # Returns a JSON response with a 200 OK status
    return jsonify(status="ok"), 200
# ----------------------------------------------------


# ----------------------------------------------------
# This route is to place orders with ALPACA✅
# ----------------------------------------------------
@app.route('/', methods=['POST'])
def webhook():
	data = request.json
	symbol = data['symbol']
	qty = data['qty']
	side = data['action']

	order = {
		"symbol": symbol,
		"qty": qty,
		"side": side,
		"type": "market",
		"time_in_force": "gtc"
	}
	
	print("Symbol:", symbol, "   qty:",  qty , "   side:",  side )

	r = requests.post(f"{BASE_URL}/v2/orders", json=order, headers={
		"APCA-API-KEY-ID": ALPACA_API_KEY,
		"APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
	})


	return {"status": "order sent", "response": r.json()}





