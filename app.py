from flask import Flask, request
import requests

app = Flask(__name__)

ALPACA_API_KEY = 'your_key'
ALPACA_SECRET_KEY = 'your_secret'
BASE_URL = 'https://paper-api.alpaca.markets'

@app.route('/webhook', methods=['POST'])
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

    r = requests.post(f"{BASE_URL}/v2/orders", json=order, headers={
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    })


    return {"status": "order sent", "response": r.json()}
