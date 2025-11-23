from pybit.unified_trading import HTTP
import time
import logging
from collections import deque
import requests
import os
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify

load_dotenv()
logging.basicConfig(level=logging.INFO)

# === КЛЮЧИ ИЗ ПЕРЕМЕННЫХ RENDER ===
session = HTTP(testnet=False,
               api_key=os.getenv("API_KEY"),
               api_secret=os.getenv("API_SECRET"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === ТВОИ НАСТРОЙКИ ===
symbol = "BTCUSDT"
trade_qty = 10
rsi_period = 14
ma_period = 20
rsi_overbought = 70
rsi_oversold = 30
take_profit_pct = 2.0
stop_loss_pct = 1.0
interval = 60

price_data = deque(maxlen=100)
recent_trades = deque(maxlen=200)
position_opened = False
entry_price = 0

app = Flask(__name__)

def send_telegram(message):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except:
        pass

# ←←←←←←←←←←← ВСТАВЬ СЮДА ВСЕ СВОИ ФУНКЦИИ ←←←←←←←←←←←
# calculate_rsi, calculate_ma, calculate_approx_cvd,
# get_kline_data, get_recent_trades, place_spot_buy,
# close_spot_position, bot_logic
# (просто скопируй их из твоего старого кода без изменений)

# (вставляю только чтобы код был полным — у тебя они уже есть)
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(0, d) for d in deltas[-period:]]
    losses = [max(0, -d) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period or 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ma(prices, period=20):
    if len(prices) < period: return None
    return sum(prices[-period:]) / period

def calculate_approx_cvd(trades):
    if not trades: return 0
    prices = [float(t[4]) for t in trades]
    volumes = [float(t[3]) for t in trades]
    avg_price = sum(prices) / len(prices)
    cvd = sum(volumes[i] if prices[i] > avg_price else -volumes[i] for i in range(len(trades)))
    return cvd

def get_kline_data(symbol, interval="1m", limit=100):
    try: return session.get_kline(category="spot", symbol=symbol, interval=interval, limit=limit)['result']['list']
    except: return []

def get_recent_trades(symbol, limit=50):
    try: return session.get_public_trade_history(category="spot", symbol=symbol, limit=limit)['result']['list']
    except: return []

def place_spot_buy():
    try:
        session.place_order(category="spot", symbol=symbol, side="Buy", order_type="Market", qty=str(trade_qty))
        msg = f"Покупка {symbol} × {trade_qty} USDT"
        logging.info(msg)
        send_telegram(msg)
    except Exception as e: logging.error(f"Buy error: {e}")

def close_spot_position():
    try:
        session.place_order(category="spot", symbol=symbol, side="Sell", order_type="Market", qty=str(trade_qty))
        msg = f"Продажа {symbol}"
        logging.info(msg)
        send_telegram(msg)
    except Exception as e: logging.error(f"Sell error: {e}")

def bot_logic():
    global position_opened, entry_price
    klines = get_kline_data(symbol)
    if not klines: return
    prices = [float(k[4]) for k in klines]
    current_price = prices[-1]
    price_data.extend(prices[-20:])

    if len(price_data) < ma_period: return

    trades = get_recent_trades(symbol)
    if trades: recent_trades.extend(trades)

    rsi = calculate_rsi(list(price_data))
    ma = calculate_ma(list(price_data))
    cvd = calculate_approx_cvd(list(recent_trades))

    if not position_opened and current_price > ma and rsi < rsi_overbought and cvd > 0:
        place_spot_buy()
        position_opened = True
        entry_price = current_price

    elif position_opened:
        if current_price >= entry_price * (1 + take_profit_pct/100):
            close_spot_position(); position_opened = False; send_telegram(f"Take-Profit {current_price}")
        elif current_price <= entry_price * (1 - stop_loss_pct/100):
            close_spot_position(); position_opened = False; send_telegram(f"Stop-Loss {current_price}")
        elif rsi < rsi_oversold:
            close_spot_position(); position_opened = False; send_telegram(f"Закрыто по RSI {rsi:.1f}")

# ←←←←←←←←←←← КОНЕЦ ТВОИХ ФУНКЦИЙ ←←←←←←←←←←←

# Flask-роуты (чтобы Render не усыплял сервис)
@app.route('/')
def home():
    return jsonify({"status": "bot running", "symbol": symbol})

@app.route('/ping')
def ping():
    return "OK", 200

# Фоновая торговая петля
def run_trading_bot():
    logging.info("Торговый бот запущен в фоне")
    send_telegram("Bybit бот запущен на Render (бесплатно)")
    while True:
        try:
            bot_logic()
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            send_telegram(f"Ошибка бота: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    threading.Thread(target=run_trading_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)