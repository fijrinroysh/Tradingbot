Project: Tradingbot — Copilot / AI agent quick guide

Goal
 - Help an AI coding agent become productive quickly by describing high-level architecture, key files, conventions, and exact examples the project expects.

Big picture (what runs where)
 - A small Flask web app (root) exposes endpoints for scheduled daily sentiment jobs and a TradingView webhook: see `main_bot.py` and `routes.py`.
 - `alpaca_trader.py` encapsulates all Alpaca trading calls (paper trading client). Use this module to place, close, or submit notional orders.
 - Sentiment analysis lives in `lib/`:
   - `lib/sentiment_analyzer.py` uses VADER (fast, lightweight).
   - `lib/finbert_analyzer.py` runs a FinBERT model (heavy, torch-based).
   - `lib/live_data_loader.py` contains the Finnhub-based 24h summary used as a trading filter.
 - Backtesting and model training live in `backtesting/` (strategies, run_backtest.py, train_model.py, backtest_utils.py). Backtests expect merged price + sentiment columns.
 - Configuration & secrets are held in `config.py` (current repo convention). Important values: `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`, `TRADINGVIEW_SECRET`, `SENTIMENT_TICKERS`, `SENTIMENT_TRADE_VALUE`, `MIN_SENTIMENT_SCORE`, `MAX_SENTIMENT_SCORE`.

Data & control flow (typical paths)
 - Webhook flow: POST `/webhook` (see `routes.py`) -> validate `secret` -> parse `action/symbol/qty` -> fetch 24h sentiment via `lib.live_data_loader.get_24h_summary_score_finnhub` -> apply sentiment veto -> call `alpaca_trader.place_buy_order` / `place_sell_order` / `close_existing_position`.
 - Daily scheduled job: `/tradingbot` route starts background thread that loops `config.SENTIMENT_TICKERS` and uses `alpaca_trader.place_notional_buy_order` with `config.SENTIMENT_TRADE_VALUE` and thresholds `MIN_SENTIMENT_SCORE` / `MAX_SENTIMENT_SCORE`.
 - Backtesting: `backtesting/run_backtest.py` reads `backtesting/backtest_config.json`, builds features (strategies expect `Sentiment` and `Article_Count` columns), loads `lib/xgb_model.json` for XGBStrategy.

Developer workflows & run commands (what actually works in this repo)
 - Install deps: `pip install -r requirements.txt` (repo uses `alpaca-py`, `finnhub-python`, `vaderSentiment`, `flask`, `gunicorn`).
 - Run app locally (dev): `python main_bot.py` (starts Flask on port 10000).
 - Run as production WSGI: `gunicorn main_bot:app -b 0.0.0.0:10000` (the module provides `app` so Gunicorn can import it).
 - Test webhook locally (example JSON):
   {"action":"BUY","symbol":"AAPL","qty":1,"secret":"IAMIRONMAN"}
   The webhook expects keys: `action`, `symbol`, `qty`, `secret` (secret matches `config.TRADINGVIEW_SECRET`).
 - Run backtests: `python backtesting/run_backtest.py` from repo root. Backtests read `backtesting/backtest_config.json` for test parameters.
 - Train or refresh ML model: `python backtesting/train_model.py` (XGBoost model saved to `lib/xgb_model.json`).

Project-specific conventions & gotchas (do not assume defaults)
 - Secrets live in `config.py` (strings in code). The repo uses `config` imports throughout; when changing to env vars, update all imports.
 - Sentiment thresholds: `MIN_SENTIMENT_SCORE` is the positive threshold (buy), `MAX_SENTIMENT_SCORE` is negative threshold (close). `MAX_SENTIMENT_SCORE` is currently a negative number.
 - `alpaca_trader` exposes both quantity-based and notional-based buy functions: `place_buy_order(ticker, qty)` and `place_notional_buy_order(ticker, trade_value)` — use the latter for dollar-sized buys used by daily sentiment flows.
 - Backtests expect columns named exactly as strategies use (for XGBStrategy: `rsi`, `macd_hist`, `bbl`, `bbu`, `atr`, `Sentiment`, `Article_Count`) — feature names and order matter when making model predictions.
 - Many modules rely on print-based logging to stdout; debugging is often accomplished by reading console output.

Integration points / external services
 - Alpaca (paper trading): uses `alpaca-py` via `alpaca_trader.py`.
 - Finnhub: used for the 24-hour sentiment filter (see `lib/live_data_loader.py`). Finnhub API key resides in `config.FINNHUB_KEY`.
 - NewsAPI / FinBERT: `lib/finbert_analyzer.py` hits NewsAPI using `config.NEWS_API_KEY` and runs a Transformer model (resource-heavy).
 - Polygon: keys in `config.POLYGON_API_KEY` used by backtesting data fetchers.

Files to inspect when making changes (quick links)
 - Request handling / routing: `routes.py`
 - Trading execution: `alpaca_trader.py`
 - Live sentiment & data fetch: `lib/live_data_loader.py`, `lib/finbert_analyzer.py`, `lib/sentiment_analyzer.py`
 - Backtesting suite: `backtesting/run_backtest.py`, `backtesting/strategies.py`, `backtesting/backtest_utils.py`, `backtesting/backtest_config.json`
 - Model artifacts: `lib/xgb_model.json`

Small examples to follow
 - Webhook expected JSON: {"action":"BUY","symbol":"TSLA","qty":2,"secret":"IAMIRONMAN"}
 - A daily notional buy is made with: `alpaca_trader.place_notional_buy_order(ticker, config.SENTIMENT_TRADE_VALUE)` (see `routes.py`).

If anything above is incomplete or you want more detail (e.g. exact unit-test patterns, preferred linting or CI commands, or replacing plain-text secrets with env-vars), tell me which section to expand and I will iterate.
