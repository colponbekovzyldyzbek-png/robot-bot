
from pybit.unified_trading import HTTP
import time
import logging
import os
from dotenv import load_dotenv
import requests

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# === ТВОИ КЛЮЧИ (уже есть в Render) ===
session = HTTP(
    testnet=False,                     # False = реальный счёт
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)

SYMBOL = "BTCUSDT"
QTY_USDT = 100          # Сколько USDT держать в позиции (от 50 до скольки хочешь)
CHECK_INTERVAL = 300    # Проверять каждые 5 минут (funding каждые 8 ч)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except: pass

# Получаем текущий funding rate
def get_funding_rate():
    try:
        resp = session.get_tickers(category="linear", symbol=SYMBOL)
        rate = float(resp["result"]["list"][0]["fundingRate"])
        return rate
    except Exception as e:
        logging.error(f"Ошибка funding: {e}")
        return 0

# Позиции
def get_spot_qty():
    try:
        bal = session.get_wallet_balance(accountType="SPOT", coin="USDT")
        return float(bal["result"]["balances"][0]["free"])
    except: return 0

def get_futures_position():
    try:
        pos = session.get_positions(category="linear", symbol=SYMBOL)
        for p in pos["result"]["list"]:
            if p["symbol"] == SYMBOL:
                return float(p["size"]), p["side"]  # размер и сторона
        return 0, None
    except: return 0, None

# Открываем/поддерживаем хедж
def hedge():
    funding = get_funding_rate()
    spot_usdt = get_spot_qty()
    fut_size, fut_side = get_futures_position()

    target_spot = QTY_USDT
    target_fut = QTY_USDT / float(session.get_tickers(category="linear", symbol=SYMBOL)["result"]["list"][0]["lastPrice"])

    msg = f"Funding Rate: {funding:+.5%}\nSpot USDT: {spot_usdt:.1f}\nFutures {fut_side}: {fut_size:.5f} BTC"

    # Если funding положительный → шортим фьючерс, держим спот
    if funding > 0:
        if fut_side != "Sell" or abs(fut_size - target_fut) > 0.0005:
            session.place_order(category="linear", symbol=SYMBOL, side="Sell", order_type="Market", qty=round(target_fut, 5))
            msg += "\nОткрыт/обновлён SHORT на фьючерсах"
    # Если funding отрицательный → лонгим фьючерс (редко, но бывает)
    else:
        if fut_side != "Buy" or abs(fut_size - target_fut) > 0.0005:
            session.place_order(category="linear", symbol=SYMBOL, side="Buy", order_type="Market", qty=round(target_fut, 5))
            msg += "\nОткрыт/обновлён LONG на фьючерсах"

    logging.info(msg)
    send_telegram(msg)

# Главный цикл
send_telegram("Funding Arbitrage бот запущен!\nСобираю funding каждые 8 часов")
while True:
    try:
        hedge()
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        send_telegram(f"Ошибка арбитража: {e}")
    time.sleep(CHECK_INTERVAL)
