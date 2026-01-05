import os
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing")

DB = "data.db"

def db():
    return sqlite3.connect(DB)

def init_db():
    with db() as con:
        c = con.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            price INTEGER,
            time TEXT
        )
        """)
        con.commit()

def get_balance(uid):
    with db() as con:
        c = con.cursor()
        c.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)", (uid,))
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        return c.fetchone()[0]

def set_balance(uid, bal):
    with db() as con:
        con.execute("UPDATE users SET balance=? WHERE user_id=?", (bal, uid))
        con.commit()

def add_history(uid, item, price):
    with db() as con:
        con.execute(
            "INSERT INTO history(user_id,item,price,time) VALUES(?,?,?,?)",
            (uid, item, price, datetime.now().isoformat())
        )
        con.commit()

MENU = ReplyKeyboardMarkup(
    [["🛒 Products", "💰 Balance"], ["🧾 History"]],
    resize_keyboard=True
)

PRODUCTS = {
    "10 UC": 20,
    "25 UC": 45,
    "Diamond 100": 80
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_balance(uid)
    await update.message.reply_text("✅ Demo Shop Bot Running", reply_markup=MENU)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text

    if msg == "💰 Balance":
        bal = get_balance(uid)
        await update.message.reply_text(f"💰 Balance: {bal}৳", reply_markup=MENU)

    elif msg == "🛒 Products":
        txt = "🛒 Products:\n"
        for k,v in PRODUCTS.items():
            txt += f"{k} - {v}৳\n"
        await update.message.reply_text(txt, reply_markup=MENU)

    elif msg in PRODUCTS:
        price = PRODUCTS[msg]
        bal = get_balance(uid)
        if bal < price:
            await update.message.reply_text("❌ Not enough balance", reply_markup=MENU)
        else:
            set_balance(uid, bal - price)
            add_history(uid, msg, price)
            await update.message.reply_text(
                f"✅ Bought {msg}\nNew Balance: {bal-price}৳",
                reply_markup=MENU
            )

    elif msg == "🧾 History":
        with db() as con:
            rows = con.execute(
                "SELECT item,price FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5",
                (uid,)
            ).fetchall()
        if not rows:
            await update.message.reply_text("No history", reply_markup=MENU)
        else:
            t = "🧾 History:\n"
            for i,p in rows:
                t += f"{i} - {p}৳\n"
            await update.message.reply_text(t, reply_markup=MENU)

async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
