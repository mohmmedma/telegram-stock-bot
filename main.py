import os
import time
import pandas as pd
import yfinance as yf
import pytz
from threading import Thread
from datetime import datetime, time as dt_time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

BOT_TOKEN = os.getenv("BOT_TOKEN") or "ضع_توكن_البوت_هنا_لو_ما_استخدمت_env"
bot = telebot.TeleBot(BOT_TOKEN)

CSV_FILE = "stocks_under_10.csv"

def load_symbols():
    url = 'https://raw.githubusercontent.com/datasets/nasdaq-listings/master/data/nasdaq-listed-symbols.csv'
    df = pd.read_csv(url)
    symbols = df['Symbol'].tolist()
    filtered = []
    for i, sym in enumerate(symbols):
        try:
            stock = yf.Ticker(sym)
            price = stock.info.get('regularMarketPrice', 0)
            if price and price < 10:
                filtered.append(sym)
        except:
            continue
        time.sleep(0.1)
    return filtered[:50]  # نأخذ أول 50 فقط للتجربة

symbols = load_symbols()
subscribers = set()
sent_today = {}

def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    fast_ema = series.ewm(span=fast).mean()
    slow_ema = series.ewm(span=slow).mean()
    macd = fast_ema - slow_ema
    signal_line = macd.ewm(span=signal).mean()
    return macd.iloc[-1], signal_line.iloc[-1]

def analyze_stock(sym):
    df = yf.download(sym, period="1d", interval="1m", progress=False)
    if df.empty or len(df) < 10:
        return None
    price = df["Close"].iloc[-1]
    open_price = df["Open"].iloc[0]
    change = ((price - open_price) / open_price) * 100
    volume = df["Volume"].iloc[-1]
    df_d = yf.download(sym, period="1mo", interval="1d", progress=False)
    if df_d.empty or len(df_d) < 20:
        return None
    ma20 = df_d["Close"].rolling(20).mean().iloc[-1]
    rsi = compute_rsi(df_d["Close"]).iloc[-1]
    macd, macd_sig = compute_macd(df_d["Close"])
    return {
        "sym": sym,
        "price": round(price, 2),
        "change": round(change, 2),
        "vol": volume,
        "ma20": round(ma20, 2),
        "rsi": round(rsi, 2),
        "macd": round(macd, 2),
        "macd_sig": round(macd_sig, 2)
    }

def format_msg(d):
    return (
        f"📌 السهم: {d['sym']}\n"
        f"💰 السعر: ${d['price']} | التغير: {d['change']}%\n"
        f"📉 MA20: {d['ma20']} | RSI: {d['rsi']:.1f}\n"
        f"📟 MACD: {d['macd']:.2f} | Signal: {d['macd_sig']:.2f}\n"
        f"📊 الحجم: {d['vol']:,}"
    )

def create_buttons(sym):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔄 تحديث", callback_data=f"refresh_{sym}"))
    return markup

@bot.message_handler(commands=['start'])
def start_handler(message):
    subscribers.add(message.chat.id)
    bot.send_message(message.chat.id, "✅ تم تفعيل الاشتراك في التوصيات.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("refresh_"))
def callback_refresh(call):
    sym = call.data.split("_")[1]
    d = analyze_stock(sym)
    if d:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=format_msg(d), reply_markup=create_buttons(sym))
    bot.answer_callback_query(call.id, "تم التحديث ✅")

def notify_loop():
    while True:
        for sym in symbols:
            d = analyze_stock(sym)
            if d:
                msg = format_msg(d)
                for user in subscribers:
                    key = f"{user}_{sym}"
                    if key not in sent_today:
                        try:
                            bot.send_message(user, msg, reply_markup=create_buttons(sym))
                            sent_today[key] = True
                        except ApiTelegramException:
                            continue
        time.sleep(30)

def run_notify_thread():
    thread = Thread(target=notify_loop, daemon=True)
    thread.start()

if __name__ == "__main__":
    run_notify_thread()
    bot.polling(none_stop=True)
