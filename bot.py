# -*- coding: utf-8 -*-
import os
import re
import secrets

import psycopg2
from psycopg2.extras import RealDictCursor

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")

ADMIN_IDS = set()
for x in os.getenv("ADMIN_IDS", "7793812954").split(","):
    x = x.strip()
    if x.isdigit():
        ADMIN_IDS.add(int(x))

FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "@hasan_ahmed_4").strip()
FORCE_JOIN_CHANNEL_ID = int(os.getenv("FORCE_JOIN_CHANNEL_ID", "-1003252506305").strip() or "-1003252506305")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# 𝐒 font headings
S = {
    "WELCOME": "🌟 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐀𝐈 𝐔𝐍𝐈𝐏𝐈𝐍 𝐒𝐇𝐎𝐏 🌟",
    "MY_ACC": "👤 𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭",
    "ADMIN": "🛠️ 𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥",
    "INFO": "ℹ️ 𝐃𝐞𝐯 & 𝐈𝐧𝐟𝐨",
}

# =========================
# DB helpers (Postgres)
# =========================
def db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Set Render Postgres Internal Database URL in env.")
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)

def db_exec(sql: str, params=None, fetchone=False, fetchall=False):
    params = params or ()
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
            return None

def init_db():
    db_exec("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        balance INTEGER NOT NULL DEFAULT 0,
        bonus INTEGER NOT NULL DEFAULT 0,
        ref_code TEXT UNIQUE,
        referred_by BIGINT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        last_active TIMESTAMP NOT NULL DEFAULT NOW(),
        banned BOOLEAN NOT NULL DEFAULT FALSE
    );
    """)

def ensure_user(u) -> dict:
    row = db_exec("SELECT * FROM users WHERE user_id=%s", (u.id,), fetchone=True)
    if row:
        db_exec("UPDATE users SET last_active=NOW(), first_name=%s, username=%s WHERE user_id=%s",
                (u.first_name or "", u.username or "", u.id))
        return row
    ref_code = secrets.token_hex(4)
    while db_exec("SELECT 1 FROM users WHERE ref_code=%s", (ref_code,), fetchone=True):
        ref_code = secrets.token_hex(4)
    db_exec(
        "INSERT INTO users(user_id, first_name, username, ref_code) VALUES(%s,%s,%s,%s)",
        (u.id, u.first_name or "", u.username or "", ref_code),
    )
    return db_exec("SELECT * FROM users WHERE user_id=%s", (u.id,), fetchone=True)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# =========================
# UI
# =========================
def main_menu(is_admin_user: bool):
    rows = [
        ["🛒 𝐔𝐧𝐢𝐩𝐢𝐧", "💎 𝐃𝐢𝐚𝐦𝐨𝐧𝐝"],
        ["💳 𝐀𝐝𝐝 𝐌𝐨𝐧𝐞𝐲", "👤 𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭"],
        ["📜 𝐇𝐢𝐬𝐭𝐨𝐫𝐲", "ℹ️ 𝐃𝐞𝐯 & 𝐈𝐧𝐟𝐨"],
    ]
    if is_admin_user:
        rows.append(["🛠️ 𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["➕ 𝐀𝐝𝐝 𝐂𝐨𝐝𝐞", "➕ 𝐀𝐝𝐝 𝐃𝐌 𝐐𝐭𝐲"],
        ["⬅️ 𝐁𝐚𝐜𝐤"]
    ], resize_keyboard=True)

# =========================
# Force-join gate
# =========================
async def is_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL_ID, user_id=update.effective_user.id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def send_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 𝐕𝐞𝐫𝐢𝐟𝐲", callback_data="verify_join")],
        [InlineKeyboardButton("📢 𝐉𝐨𝐢𝐧 𝐂𝐡𝐚𝐧𝐧𝐞𝐥", url=f"https://t.me/{FORCE_JOIN_CHANNEL.lstrip('@')}")]
    ])
    await update.message.reply_text(
        f"""{S['WELCOME']}

➡️ Please Join: {FORCE_JOIN_CHANNEL}

✅ Join kore niche Verify cap korun!""",
        reply_markup=kb,
    )

async def on_verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_member(update, context):
        await q.edit_message_text("✅ 𝐕𝐞𝐫𝐢𝐟𝐢𝐞𝐝! 𝐍𝐨𝐰 𝐮𝐬𝐞 /start")
    else:
        await q.edit_message_text(
            f"""❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐣𝐨𝐢𝐧𝐞𝐝 𝐲𝐞𝐭.

➡️ Join: {FORCE_JOIN_CHANNEL}
and try again."""
        )

# =========================
# Referral
# =========================
def parse_start_ref(start_arg: str):
    if not start_arg:
        return None
    s = start_arg.strip().lower()
    if re.fullmatch(r"[a-f0-9]{8}", s):
        return s
    return None

def bind_referral(new_user_id: int, ref_code: str):
    ref_user = db_exec("SELECT user_id FROM users WHERE ref_code=%s", (ref_code,), fetchone=True)
    if not ref_user:
        return
    if int(ref_user["user_id"]) == int(new_user_id):
        return
    me = db_exec("SELECT referred_by FROM users WHERE user_id=%s", (new_user_id,), fetchone=True)
    if me and me["referred_by"] is None:
        db_exec("UPDATE users SET referred_by=%s WHERE user_id=%s", (int(ref_user["user_id"]), int(new_user_id)))

# =========================
# Screens
# =========================
DEV_INFO_TEXT = (
    "✨ 𝐀𝐈 𝐔𝐍𝐈𝐏𝐈𝐍 𝐒𝐇𝐎𝐏 ✨\n"
    "𝐀 𝐒𝐦𝐚𝐫𝐭 • 𝐒𝐞𝐜𝐮𝐫𝐞 • 𝐓𝐫𝐮𝐬𝐭𝐞𝐝 𝐃𝐢𝐠𝐢𝐭𝐚𝐥 𝐒𝐭𝐨𝐫𝐞\n\n"
    "🛒 𝐒𝐞𝐫𝐯𝐢𝐜𝐞𝐬\n"
    "• 𝐔𝐧𝐢𝐩𝐢𝐧 𝐂𝐨𝐝𝐞\n"
    "• 𝐃𝐢𝐚𝐦𝐨𝐧𝐝 (𝐀𝐝𝐦𝐢𝐧 𝐀𝐩𝐩𝐫𝐨𝐯𝐚𝐥)\n"
    "• 𝐀𝐝𝐝 𝐌𝐨𝐧𝐞𝐲 (𝐀𝐝𝐦𝐢𝐧 𝐀𝐩𝐩𝐫𝐨𝐯𝐚𝐥)\n"
    "• 𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥 𝐋𝐢𝐧𝐤\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    u = update.effective_user
    row = ensure_user(u)

    ref = parse_start_ref(context.args[0]) if context.args else None
    if ref:
        bind_referral(u.id, ref)

    if row.get("banned"):
        return await update.message.reply_text("🚫 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐛𝐚𝐧𝐧𝐞𝐝.")

    if not await is_member(update, context):
        return await send_join_gate(update, context)

    welcome = (
        S["WELCOME"]
        + "\n🎮 𝐘𝐨𝐮𝐫 𝐓𝐫𝐮𝐬𝐭𝐞𝐝 𝐔𝐧𝐢𝐩𝐢𝐧 & 𝐃𝐢𝐚𝐦𝐨𝐧𝐝 𝐒𝐭𝐨𝐫𝐞\n\n"
        + "👇 𝐌𝐞𝐧𝐮 𝐭𝐡𝐞𝐤𝐞 𝐨𝐩𝐭𝐢𝐨𝐧 𝐬𝐞𝐥𝐞𝐜𝐭 𝐤𝐨𝐫𝐮𝐧"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu(is_admin(u.id)))

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    u = update.effective_user
    row = ensure_user(u)
    if not await is_member(update, context):
        return await send_join_gate(update, context)

    ref_count = db_exec("SELECT COUNT(*) AS c FROM users WHERE referred_by=%s", (u.id,), fetchone=True)["c"]
    msg = (
        f"""{S['MY_ACC']}

👤 𝐔𝐬𝐞𝐫 𝐈𝐃: {u.id}
💰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞: {row['balance']}৳
🎁 𝐁𝐨𝐧𝐮𝐬: {row['bonus']}৳

🤝 𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥
🔗 𝐘𝐨𝐮𝐫 𝐋𝐢𝐧𝐤:
https://t.me/{context.bot.username}?start={row['ref_code']}
👥 𝐓𝐨𝐭𝐚𝐥 𝐑𝐞𝐟𝐞𝐫𝐬: {ref_count}
"""
    )
    await update.message.reply_text(msg, reply_markup=main_menu(is_admin(u.id)))

async def dev_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_member(update, context):
        return await send_join_gate(update, context)
    await update.message.reply_text(DEV_INFO_TEXT, reply_markup=main_menu(is_admin(update.effective_user.id)))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ 𝐀𝐝𝐦𝐢𝐧 𝐨𝐧𝐥𝐲.")
    await update.message.reply_text(S["ADMIN"], reply_markup=admin_menu())

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    u = update.effective_user

    if txt == "👤 𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭":
        return await my_account(update, context)
    if txt == "ℹ️ 𝐃𝐞𝐯 & 𝐈𝐧𝐟𝐨":
        return await dev_info(update, context)
    if txt == "🛠️ 𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥":
        return await admin_panel(update, context)

    await update.message.reply_text("🙂 𝐌𝐞𝐧𝐮 𝐭𝐡𝐞𝐤𝐞 𝐨𝐩𝐭𝐢𝐨𝐧 𝐧𝐢𝐧।", reply_markup=main_menu(is_admin(u.id)))

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_verify_join, pattern=r"^verify_join$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
