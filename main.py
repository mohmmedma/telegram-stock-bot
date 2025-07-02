import os
import time
import pandas as pd
import yfinance as yf
import pytz
from threading import Thread
from datetime import datetime, time as dt_time
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

BOT_TOKEN = os.getenv("BOT_TOKEN") or "7563306025:AAFzyi1YUTctuErLH0dZOQH3XoMf9ECjR7Q"
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

CSV_FILE = "stocks_under_10.csv"

def load_symbols_from_file():
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        print(f"📁 تم تحميل {len(df)} سهم من الملف المخزن ✅")
        return df["Symbol"].tolist()
    return None

def load_symbols_below_10():
    saved = load_symbols_from_file()
    if saved:
        return saved
    url = 'https://raw.githubusercontent.com/datasets/nasdaq-listings/master/data/nasdaq-listed-symbols.csv'
    df_symbols = pd.read_csv(url)
    symbols_all = df_symbols['Symbol'].tolist()
    filtered_symbols, temp_data = [], []

    print("⏳ جاري فحص أسعار الأسهم (أقل من 10 دولار)...")
    for i, sym in enumerate(symbols_all):
        try:
            print(f"🔄 ({i+1}/{len(symbols_all)}) فحص: {sym}")
            stock = yf.Ticker(sym)
            price = stock.info.get('regularMarketPrice', None)
            if price and price < 10:
                filtered_symbols.append(sym)
                temp_data.append({"Symbol": sym, "Price": price})
        except Exception as e:
            print(f"⚠️ خطأ عند {sym}: {e}")
        time.sleep(0.1)  # تأخير بسيط لتجنب الحظر من ال API

    df_save = pd.DataFrame(temp_data)
    df_save.to_csv(CSV_FILE, index=False)
    print(f"\n📦 تم حفظ {len(filtered_symbols)} سهم في {CSV_FILE}")
    return filtered_symbols

symbols = load_symbols_below_10()
subscribers, sent_today = set(), {}
history = {"win": [], "lose": []}

def get_market_phase():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est).time()
    if now < dt_time(9, 30):
        return "قبل الافتتاح"
    elif now <= dt_time(16):
        return "أثناء التداول"
    else:
        return "بعد الإغلاق"

def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd = fast_ema - slow_ema
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd.iloc[-1], signal_line.iloc[-1]

def analyze_stock(sym):
    df = yf.download(sym, period="1d", interval="1m", auto_adjust=True, progress=False)
    if df.empty:
        return None

    price_series = df["Close"]
    vol_series = df["Volume"]

    if (price_series > 10).any(axis=None) or (vol_series < 20000).any(axis=None):
        return None

    price = price_series.iloc[-1]
    op = df["Open"].iloc[0]
    change = ((price - op) / op) * 100
    vol = vol_series.iloc[-1]

    df_d = yf.download(sym, period="1mo", interval="1d", auto_adjust=True, progress=False)
    df_d.dropna(inplace=True)
    if df_d.empty:
        return None
    ma20 = df_d["Close"].rolling(20).mean().iloc[-1]

    macd_val, macd_sig = compute_macd(df_d["Close"])
    rsi = compute_rsi(df_d["Close"]).iloc[-1]

    info = yf.Ticker(sym).info
    news = yf.Ticker(sym).news[:3]
    target = round(info.get("targetMeanPrice", 0), 2) if info.get("targetMeanPrice") else "N/A"
    phase = get_market_phase()

    if not (price > ma20) and abs(change) < 1:
        return None

    return {
        "sym": sym, "price": round(price, 2), "change": round(change, 2),
        "vol": vol, "ma20": round(ma20, 2),
        "macd": round(macd_val, 2), "macd_sig": round(macd_sig, 2),
        "rsi": round(rsi, 2), "news": news, "target": target, "phase": phase
    }

def format_msg(d):
    rec = "✅ شراء" if d["change"] > 0 else "❌ بيع"
    history["win" if d["change"] > 0 else "lose"].append(d["sym"])
    lines = [
        f"🚨 توصية | {d['phase']}",
        "━━━━━━━━━━━━━━━━━━",
        f"📌 الرمز: {d['sym']} | 💵 ${d['price']} | 📈 {d['change']}%",
        f"📊 الحجم: {d['vol']:,}",
        f"📉 MA20: ${d['ma20']}",
        f"📟 MACD: {d['macd']} مقابل الإشارة: {d['macd_sig']} | RSI: {d['rsi']}",
        f"🎯 هدف المحللين: ${d['target']}",
        f"📢 {rec}",
        "━━━━━━━━━━━━━━━━━━",
        "📰 أخبار مختارة:"
    ]
    for n in d["news"]:
        lines.append(f"- {n['title']}")
    return "\n".join(lines)

def create_buttons(sym):
    m = InlineKeyboardMarkup()
    m.row(
        InlineKeyboardButton("🔄 تحديث", callback_data=f"refresh_{sym}"),
        InlineKeyboardButton("🛑 إلغاء", callback_data="stop")
    )
    m.row(
        InlineKeyboardButton("📊 التوصيات", callback_data="recommendations"),
        InlineKeyboardButton("🔔 التنبيهات", callback_data="alerts"),
        InlineKeyboardButton("🏆 القطاع الأقوى", callback_data="strongest_sector")
    )
    m.row(InlineKeyboardButton("📈 الأعلى صعودًا", callback_data="top_gainers"))
    return m

@bot.message_handler(commands=["start"])
def s(m):
    subscribers.add(m.chat.id)
    sent_today[m.chat.id] = set()
    first_sym = symbols[0] if symbols else "AMD"
    bot.send_message(m.chat.id, "✅ تم تفعيل الاشتراك في التوصيات", reply_markup=create_buttons(first_sym))

@bot.message_handler(commands=["stop"])
def st(m):
    subscribers.discard(m.chat.id)
    bot.send_message(m.chat.id, "🛑 تم إلغاء الاشتراك")

@bot.callback_query_handler(lambda cl: cl.data.startswith("refresh_"))
def cb_ref(cl):
    sym = cl.data.split("_")[1]
    d = analyze_stock(sym)
    if d:
        bot.edit_message_text(cl.message.chat.id, cl.message.message_id, format_msg(d), reply_markup=create_buttons(sym))
    bot.answer_callback_query(cl.id, "تم التحديث")

@bot.callback_query_handler(lambda cl: cl.data == "stop")
def cb_stop(cl):
    subscribers.discard(cl.message.chat.id)
    bot.send_message(cl.message.chat.id, "🛑 تم الإلغاء")
    bot.answer_callback_query(cl.id, "تم")

@bot.callback_query_handler(lambda cl: cl.data == "top_gainers")
def cb_top(cl):
    top_list = []
    for s in symbols:
        d = analyze_stock(s)
        if d:
            top_list.append((s, d["change"]))
    top_sorted = sorted(top_list, key=lambda x: x[1], reverse=True)[:5]
    msg = "📈 الأعلى صعودًا اليوم:\n" + "\n".join([x[0] for x in top_sorted])
    bot.send_message(cl.message.chat.id, msg)
    bot.answer_callback_query(cl.id)

@bot.callback_query_handler(lambda cl: cl.data == "recommendations")
def cb_rec(cl):
    bot.send_message(cl.message.chat.id, "📌 التوصيات قيد التطوير.")
    bot.answer_callback_query(cl.id)

@bot.callback_query_handler(lambda cl: cl.data == "alerts")
def cb_alerts(cl):
    bot.send_message(cl.message.chat.id, "🔔 التنبيهات قيد التطوير.")
    bot.answer_callback_query(cl.id)

@bot.callback_query_handler(lambda cl: cl.data == "strongest_sector")
def cb_sec(cl):
    bot.send_message(cl.message.chat.id, "🏆 القطاع الأقوى قيد التطوير.")
    bot.answer_callback_query(cl.id)

def notify():
    while True:
        for sym in symbols:
            d = analyze_stock(sym)
            if d:
                for u in subscribers.copy():
                    key = f"{d['sym']}_{d['phase']}"
                    if key not in sent_today.get(u, set()):
                        msg = format_msg(d)
                        try:
                            bot.send_message(u, msg, reply_markup=create_buttons(d["sym"]))
                            sent_today.setdefault(u, set()).add(key)
                        except ApiTelegramException as e:
                            print(f"Telegram API error: {e}")
        time.sleep(30)  # تحقق كل 30 ثانية

def run_notify_thread():
    thread = Thread(target=notify, daemon=True)
    thread.start()

@app.route('/')
def home():
    return "✅ البوت يعمل بنجاح!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_update = request.get_json()
    if json_update:
        bot.process_new_updates([telebot.types.Update.de_json(json_update)])
    return '', 200

if __name__ == '__main__':
    run_notify_thread()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
    bot.polling(none_stop=True)
