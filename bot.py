import os
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")

DB_PATH = os.getenv("DB_PATH", "data.db").strip() or "data.db"

PRODUCTS = {
    "10 UC": 20,
    "25 UC": 45,
    "Diamond 100": 80,
}

MENU = ReplyKeyboardMarkup(
    [["🛒 Products", "💰 Balance"], ["🧾 History"]],
    resize_keyboard=True
)

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
        con.execute("""CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            price INTEGER,
            time TEXT
        )""")
        con.commit()

def ensure_user(uid: int):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)", (uid,))
        con.commit()

def get_balance(uid: int) -> int:
    ensure_user(uid)
    with db() as con:
        return int(con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()[0])

def set_balance(uid: int, bal: int):
    ensure_user(uid)
    with db() as con:
        con.execute("UPDATE users SET balance=? WHERE user_id=?", (bal, uid))
        con.commit()

def add_history(uid: int, item: str, price: int):
    with db() as con:
        con.execute("INSERT INTO history(user_id,item,price,time) VALUES(?,?,?,?)",
                    (uid, item, price, datetime.now().isoformat()))
        con.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    await update.message.reply_text("✅ Demo Shop Bot Running", reply_markup=MENU)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = (update.message.text or "").strip()

    if msg == "💰 Balance":
        await update.message.reply_text(f"💰 Balance: {get_balance(uid)}৳", reply_markup=MENU)
        return

    if msg == "🛒 Products":
        lines = ["🛒 Products (tap item name to buy):"]
        for name, price in PRODUCTS.items():
            lines.append(f"• {name} — {price}৳")
        lines.append("\n👉 কিনতে item নামটা পাঠাও (যেমন: 10 UC)")
        await update.message.reply_text("\n".join(lines), reply_markup=MENU)
        return

    if msg in PRODUCTS:
        price = PRODUCTS[msg]
        bal = get_balance(uid)
        if bal < price:
            await update.message.reply_text(f"❌ Not enough balance.\nYour: {bal}৳\nNeed: {price}৳", reply_markup=MENU)
            return
        set_balance(uid, bal - price)
        add_history(uid, msg, price)
        await update.message.reply_text(f"✅ Bought {msg}\nSpent: {price}৳\nNew: {bal-price}৳", reply_markup=MENU)
        return

    if msg == "🧾 History":
        with db() as con:
            rows = con.execute(
                "SELECT item,price FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5",
                (uid,)
            ).fetchall()
        if not rows:
            await update.message.reply_text("🧾 No history yet.", reply_markup=MENU)
        else:
            t = "🧾 Last 5:\n" + "\n".join([f"• {i} — {p}৳" for i, p in rows])
            await update.message.reply_text(t, reply_markup=MENU)
        return

    await update.message.reply_text("Menu ব্যবহার করো 🙂", reply_markup=MENU)

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
