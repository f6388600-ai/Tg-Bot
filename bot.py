
import os
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")

DB_PATH = os.getenv("DB_PATH", "data.db").strip() or "data.db"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or "0")

# ---------- DB ----------
def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with db() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                price INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.commit()

def ensure_user(user_id: int):
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users (user_id, balance, created_at) VALUES (?, ?, ?)",
                (user_id, 0, datetime.utcnow().isoformat()),
            )
        con.commit()

def get_balance(user_id: int) -> int:
    ensure_user(user_id)
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        return int(cur.fetchone()[0])

def set_balance(user_id: int, new_balance: int):
    ensure_user(user_id)
    with db() as con:
        cur = con.cursor()
        cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
        con.commit()

def add_purchase(user_id: int, item: str, price: int):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO purchases (user_id, item, price, created_at) VALUES (?, ?, ?, ?)",
            (user_id, item, price, datetime.utcnow().isoformat()),
        )
        con.commit()

def list_purchases(user_id: int, limit: int = 10):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT item, price, created_at FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return cur.fetchall()

# ---------- Demo products ----------
PRODUCTS = [
    ("10 UC", 20),
    ("25 UC", 45),
    ("60 UC", 99),
    ("Diamond 100", 80),
    ("Diamond 310", 230),
]

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Products", "💰 Balance"],
            ["🧾 History", "ℹ️ Help"],
        ],
        resize_keyboard=True,
    )

def products_menu():
    rows = []
    for name, price in PRODUCTS:
        rows.append([f"🛍️ Buy {name} - {price}৳"])
    rows.append(["⬅️ Back"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure_user(u.id)
    await update.message.reply_text(
        "✅ Demo Shop Bot চালু হয়েছে!\n\nমেনু থেকে Products/Balace টেস্ট করো।",
        reply_markup=main_menu(),
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔧 Demo Commands:\n"
        "• /start\n"
        "• /addbalance <amount>  (admin only)\n\n"
        "Menu:\n"
        "• Products → Buy → Confirm\n"
        "• Balance → current balance\n"
        "• History → last purchases"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

async def addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if ADMIN_ID and u.id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only.", reply_markup=main_menu())

    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("Usage: /addbalance 100", reply_markup=main_menu())

    amt = int(context.args[0])
    if amt <= 0:
        return await update.message.reply_text("❌ Amount must be > 0", reply_markup=main_menu())

    old = get_balance(u.id)
    new = old + amt
    set_balance(u.id, new)
    await update.message.reply_text(f"✅ Balance added: {amt}৳\nOld: {old}৳ → New: {new}৳", reply_markup=main_menu())

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip()
    u = update.effective_user
    ensure_user(u.id)

    if msg == "🛒 Products":
        return await update.message.reply_text("🛒 Product list:", reply_markup=products_menu())

    if msg == "💰 Balance":
        bal = get_balance(u.id)
        return await update.message.reply_text(f"💰 Your balance: {bal}৳", reply_markup=main_menu())

    if msg == "🧾 History":
        rows = list_purchases(u.id, limit=10)
        if not rows:
            return await update.message.reply_text("🧾 No purchases yet.", reply_markup=main_menu())
        lines = ["🧾 Last purchases:"]
        for item, price, t in rows:
            lines.append(f"• {item} — {price}৳")
        return await update.message.reply_text("\n".join(lines), reply_markup=main_menu())

    if msg == "ℹ️ Help":
        return await help_cmd(update, context)

    if msg == "⬅️ Back":
        context.user_data.pop("pending_buy", None)
        return await update.message.reply_text("⬅️ Back to menu.", reply_markup=main_menu())

    # Buy flow
    if msg.startswith("🛍️ Buy "):
        # parse "🛍️ Buy {name} - {price}৳"
        try:
            body = msg.replace("🛍️ Buy ", "", 1)
            name, price_part = body.rsplit(" - ", 1)
            price = int(price_part.replace("৳", "").strip())
        except Exception:
            return await update.message.reply_text("❌ Parse error. Try again.", reply_markup=products_menu())

        context.user_data["pending_buy"] = (name.strip(), price)
        kb = ReplyKeyboardMarkup([["✅ Confirm Buy", "❌ Cancel"], ["⬅️ Back"]], resize_keyboard=True)
        return await update.message.reply_text(
            f"🧾 Confirm?\nItem: {name}\nPrice: {price}৳",
            reply_markup=kb,
        )

    if msg == "❌ Cancel":
        context.user_data.pop("pending_buy", None)
        return await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu())

    if msg == "✅ Confirm Buy":
        pending = context.user_data.get("pending_buy")
        if not pending:
            return await update.message.reply_text("❌ Nothing to confirm.", reply_markup=main_menu())

        name, price = pending
        bal = get_balance(u.id)
        if bal < price:
            context.user_data.pop("pending_buy", None)
            return await update.message.reply_text(
                f"❌ Not enough balance.\nYour balance: {bal}৳\nNeed: {price}৳",
                reply_markup=main_menu(),
            )

        set_balance(u.id, bal - price)
        add_purchase(u.id, name, price)
        context.user_data.pop("pending_buy", None)
        return await update.message.reply_text(
            f"✅ Purchased!\nItem: {name}\nSpent: {price}৳\nNew balance: {bal - price}৳",
            reply_markup=main_menu(),
        )

    # default
    await update.message.reply_text("কম্যান্ড বুঝিনি। Menu ব্যবহার করো 🙂", reply_markup=main_menu())

def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addbalance", addbalance))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app

def main():
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
