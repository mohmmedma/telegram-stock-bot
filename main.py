import time
import telebot

BOT_TOKEN = "7563306025:AAFzyi1YUTctuErLH0dZOQH3XoMf9ECjR7Q"
bot = telebot.TeleBot(BOT_TOKEN)

def get_stock_recommendations():
    return [
        {
            "symbol": "AAPL",
            "price": 172.50,
            "target": 180.00,
            "stop_loss": 170.00,
            "recommendation": "شراء",
        },
        {
            "symbol": "TSLA",
            "price": 680.00,
            "target": 720.00,
            "stop_loss": 660.00,
            "recommendation": "انتظار",
        },
    ]

def send_recommendations(chat_id):
    recs = get_stock_recommendations()
    for r in recs:
        text = (
            f"📈 توصية سهم: {r['symbol']}\n"
            f"السعر الحالي: ${r['price']}\n"
            f"الهدف: ${r['target']}\n"
            f"وقف الخسارة: ${r['stop_loss']}\n"
            f"التوصية: {r['recommendation']}\n"
        )
        bot.send_message(chat_id, text)

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "أهلاً! هذا بوت توصيات الأسهم.\nاكتب /recommend لتلقي التوصيات.")

@bot.message_handler(commands=['recommend'])
def recommend(message):
    send_recommendations(message.chat.id)

def main_loop():
    CHAT_ID = "ضع_هنا_رقم_المحادثة_او_القناة"
    while True:
        send_recommendations(CHAT_ID)
        time.sleep(1800)  # كل 30 دقيقة

if __name__ == "__main__":
    from threading import Thread
    Thread(target=bot.infinity_polling).start()
    main_loop()
