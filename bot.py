
# -*- coding: utf-8 -*-
"""
Hasan AI Unipin Shop Bot (New From Scratch) - FINAL ALL FEATURES
python-telegram-bot==20.7

Defaults (can be overridden by env):
- ADMIN_IDS: 7793812954
- FORCE_JOIN_CHANNEL: hasan_ahmed_4   (without @)
- DB_PATH: shopbot.db

Run:
  export BOT_TOKEN="xxxx"
  export ADMIN_IDS="7793812954"
  export FORCE_JOIN_CHANNEL="hasan_ahmed_4"
  python bot.py
"""

import os
import re
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Tuple
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# -------------------- CONFIG --------------------

# -------------------- HEALTH SERVER (for Render free uptime ping) --------------------
# Render Free Web Service may sleep when idle. A tiny /health endpoint + UptimeRobot ping keeps it awake.
# Set RUN_HEALTH=1 (default) to enable. Render provides PORT.
def start_health_server():
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.get("/")
        def root():
            return "OK"

        @app.get("/health")
        def health():
            return "OK"

        port = int(os.getenv("PORT", "10000"))
        app.run(host="0.0.0.0", port=port)
    except Exception:
        # If flask isn't installed or any error, skip health server.
        pass

DB_PATH = os.getenv("DB_PATH", "shopbot.db").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_IDS: set = set()
for x in os.getenv("ADMIN_IDS", "7793812954").split(","):
    x = x.strip()
    if x.isdigit():
        ADMIN_IDS.add(int(x))

FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "hasan_ahmed_4").strip().lstrip("@")

# -------------------- FANCY FONT --------------------
# Bold Math Sans mapping for ASCII letters/digits. Bangla stays unchanged.
_ASC_UP = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASC_LO = "abcdefghijklmnopqrstuvwxyz"
_ASC_DG = "0123456789"
_BOLD_UP = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
_BOLD_LO = "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"
_BOLD_DG = "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
_TRANS = str.maketrans(_ASC_UP + _ASC_LO + _ASC_DG, _BOLD_UP + _BOLD_LO + _BOLD_DG)

def F(s: str) -> str:
    s = s or ""
    return s.translate(_TRANS)

def mono(s: str) -> str:
    s = (s or "").replace("<", "&lt;").replace(">", "&gt;")
    return f"<code>{s}</code>"

def now_ts() -> int:
    return int(time.time())

def fmt_time(ts: Optional[int] = None) -> str:
    if ts is None:
        ts = now_ts()
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# -------------------- DB --------------------

class DBSession:
    """Mimics sqlite connection API used in this code.
    Supports: with db() as c: c.execute(...).fetchone()
    - Translates sqlite '?' placeholders to psycopg2 '%s'
    - Returns dict rows so row['col'] works.
    """
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor(cursor_factory=RealDictCursor)

    def execute(self, query, params=None):
        if params is None:
            params = []
        q = query.replace("?", "%s")
        self.cur.execute(q, params)
        return self.cur

    def executemany(self, query, seq_of_params):
        q = query.replace("?", "%s")
        self.cur.executemany(q, seq_of_params)
        return self.cur

    @property
    def rowcount(self):
        return self.cur.rowcount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            try:
                self.cur.close()
            except Exception:
                pass
            try:
                self.conn.close()
            except Exception:
                pass

def db():
    """Prefer Postgres when DATABASE_URL is set; fallback to SQLite for local use."""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return DBSession(conn)
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db() -> None:

    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS settings(
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id BIGINT PRIMARY KEY,
            name TEXT,
            created_ts BIGINT,
            last_active_ts BIGINT,
            approved INTEGER DEFAULT 1,
            banned INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 0,
            bonus INTEGER DEFAULT 0,
            due INTEGER DEFAULT 0,
            due_limit INTEGER DEFAULT 0,
            total_purchase INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0,
            referral_bonus_earned INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS products(
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            cat TEXT NOT NULL CHECK(cat IN ('UC','DM'))
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS codes(
            id SERIAL PRIMARY KEY,
            pkey TEXT NOT NULL,
            code TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            used_by INTEGER DEFAULT NULL,
            used_ts BIGINT DEFAULT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS dm_stock(
            pkey TEXT PRIMARY KEY,
            qty INTEGER NOT NULL DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            cat TEXT NOT NULL,
            pkey TEXT NOT NULL,
            pname TEXT NOT NULL,
            price INTEGER NOT NULL,
            uid TEXT DEFAULT NULL,
            status TEXT NOT NULL,
            created_ts BIGINT NOT NULL,
            updated_ts BIGINT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments(
            pay_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            method TEXT NOT NULL,
            txid TEXT NOT NULL,
            status TEXT NOT NULL,
            created_ts BIGINT NOT NULL,
            updated_ts BIGINT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS payment_methods(
            name TEXT PRIMARY KEY,
            details TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS history(
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            text TEXT NOT NULL,
            ts BIGINT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS redeem_codes(
            code TEXT PRIMARY KEY,
            amount INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            used_by INTEGER DEFAULT NULL,
            used_ts BIGINT DEFAULT NULL,
            created_ts BIGINT NOT NULL
        )""")
        # default settings
        def set_default(k: str, v: str):
            c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k, v))
        set_default("maintenance", "OFF")
        set_default("notifications", "ON")
        set_default("ss_must", "ON")
        set_default("bonus_on", "ON")
        set_default("ref_on", "ON")
        set_default("ref_bonus", "20")
        set_default("ref_min_purchase", "1000")  # Tk 1000 threshold
        set_default("low_stock_threshold", "3")

def sget(k: str, default: str = "") -> str:
    with db() as c:
        r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

def sset(k: str, v: str) -> None:
    with db() as c:
        c.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))

def cleanup_history() -> None:
    cutoff = now_ts() - 24 * 3600
    with db() as c:
        c.execute("DELETE FROM history WHERE ts < ?", (cutoff,))

def ensure_user(u) -> None:
    uid = u.id
    name = (u.full_name or "").strip()
    ts = now_ts()
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(user_id,name,created_ts,last_active_ts) VALUES(?,?,?,?)",
            (uid, name, ts, ts),
        )
        c.execute(
            "UPDATE users SET name=?, last_active_ts=? WHERE user_id=?",
            (name, ts, uid),
        )

def uget(uid: int):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def uupdate(uid: int, **kwargs) -> None:
    if not kwargs:
        return
    cols = []
    vals = []
    for k, v in kwargs.items():
        cols.append(f"{k}=?")
        vals.append(v)
    vals.append(uid)
    with db() as c:
        c.execute(f"UPDATE users SET {', '.join(cols)} WHERE user_id=?", vals)

def add_history(uid: int, htype: str, text: str) -> None:
    with db() as c:
        c.execute("INSERT INTO history(user_id,type,text,ts) VALUES(?,?,?,?)", (uid, htype, text, now_ts()))

def get_uc_stock(pkey: str) -> int:
    with db() as c:
        r = c.execute("SELECT COUNT(*) AS n FROM codes WHERE pkey=? AND used=0", (pkey,)).fetchone()
        return int(r["n"])

def get_dm_stock(pkey: str) -> int:
    with db() as c:
        r = c.execute("SELECT qty FROM dm_stock WHERE pkey=?", (pkey,)).fetchone()
        return int(r["qty"]) if r else 0

def set_dm_stock(pkey: str, qty: int) -> None:
    with db() as c:
        c.execute("INSERT INTO dm_stock(pkey,qty) VALUES(?,?) ON CONFLICT(pkey) DO UPDATE SET qty=excluded.qty", (pkey, int(qty)))

def get_products(cat: str) -> List[sqlite3.Row]:
    with db() as c:
        return list(c.execute("SELECT * FROM products WHERE cat=? ORDER BY price ASC", (cat,)).fetchall())

def get_product(pkey: str):
    with db() as c:
        return c.execute("SELECT * FROM products WHERE key=?", (pkey,)).fetchone()

def add_product(pkey: str, name: str, price: int, cat: str) -> None:
    with db() as c:
        c.execute(
            "INSERT INTO products(key,name,price,cat) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, price=excluded.price, cat=excluded.cat",
            (pkey, name, int(price), cat),
        )
        if cat == "DM":
            c.execute("INSERT OR IGNORE INTO dm_stock(pkey,qty) VALUES(?,0)", (pkey,))

def delete_product(pkey: str) -> None:
    with db() as c:
        c.execute("DELETE FROM products WHERE key=?", (pkey,))
        c.execute("DELETE FROM codes WHERE pkey=?", (pkey,))
        c.execute("DELETE FROM dm_stock WHERE pkey=?", (pkey,))

def add_codes(pkey: str, codes: List[str]) -> Tuple[int,int]:
    # returns (added, dup_skipped)
    cleaned = []
    for x in codes:
        x = (x or "").strip()
        if x:
            cleaned.append(x)
    if not cleaned:
        return (0, 0)
    added = 0
    dup = 0
    with db() as c:
        existing = set([r["code"] for r in c.execute("SELECT code FROM codes WHERE pkey=?", (pkey,)).fetchall()])
        for code in cleaned:
            if code in existing:
                dup += 1
                continue
            c.execute("INSERT INTO codes(pkey,code,used) VALUES(?,?,0)", (pkey, code))
            existing.add(code)
            added += 1
    return (added, dup)

def pop_one_code(pkey: str, buyer_id: int) -> Optional[str]:
    with db() as c:
        r = c.execute("SELECT id,code FROM codes WHERE pkey=? AND used=0 ORDER BY id ASC LIMIT 1", (pkey,)).fetchone()
        if not r:
            return None
        c.execute("UPDATE codes SET used=1, used_by=?, used_ts=? WHERE id=?", (buyer_id, now_ts(), r["id"]))
        return r["code"]

def remove_codes(pkey: str, codes: List[str]) -> int:
    cleaned = [x.strip() for x in codes if x.strip()]
    if not cleaned:
        return 0
    with db() as c:
        q = "DELETE FROM codes WHERE pkey=? AND code IN (%s)" % (",".join(["?"] * len(cleaned)))
        cur = c.execute(q, [pkey] + cleaned)
        return cur.rowcount

def get_all_codes(pkey: str) -> List[str]:
    with db() as c:
        rows = c.execute("SELECT code,used FROM codes WHERE pkey=? ORDER BY id ASC", (pkey,)).fetchall()
        out = []
        for r in rows:
            tag = "USED" if int(r["used"]) == 1 else "NEW"
            out.append(f"{r['code']} ({tag})")
        return out

# -------------------- UI KEYBOARDS --------------------

def kb(rows: List[List[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(x) for x in row] for row in rows], resize_keyboard=True)

def home_kb(uid: int) -> ReplyKeyboardMarkup:
    rows = [
        ["🎫 Unipin", "💎 Diamond"],
        ["➕ Add Money", "🎁 Gift Coin"],
        ["🎟 Redeem Code", "📜 History"],
        ["📦 Orders", "👥 Refer & Earn"],
        ["👤 My Account", "🆘 Support"],
        ["ℹ️ Dev & Info"],
    ]
    if is_admin(uid):
        rows.append(["🛠 Admin Panel"])
    return kb(rows)

def banned_kb(uid: int) -> ReplyKeyboardMarkup:
    rows = [["🆘 Support", "ℹ️ Dev & Info"]]
    if is_admin(uid):
        rows.append(["🛠 Admin Panel"])
    return kb(rows)

def back_kb() -> ReplyKeyboardMarkup:
    return kb([["⬅ Back"]])

def admin_kb() -> ReplyKeyboardMarkup:
    return kb([
        ["➕ Add UC List", "➕ Add DM List"],
        ["➕ Add Code", "➕ Add DM Qty"],
        ["🧹 Code Remove", "📤 Code Return"],
        ["🗑 Delete Product", "📦 Stock"],
        ["💳 Payment Methods", "🔔 Notifications"],
        ["📸 SS Must ON/OFF", "🎁 Bonus Settings"],
        ["🎟 Redeem Manage", "👥 Referral Settings"],
        ["💰 Add Balance", "➖ Cut Balance"],
        ["⚠ Warn User", "⛔ Ban User", "♻ Unban User"],
        ["📋 Get All User ID"],
        ["📣 Send All Msg", "👤 Send User Msg"],
        ["📨 Multi ID Msg"],
        ["🛠 Bot ON/OFF"],
        ["⬅ Back"],
    ])

# -------------------- JOIN/VERIFY + LOADING --------------------

async def is_joined(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if not FORCE_JOIN_CHANNEL:
        return True
    uid = update.effective_user.id
    if is_admin(uid):
        return True
    try:
        cm = await ctx.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        return cm.status in ("member", "administrator", "creator")
    except Exception:
        return False

def join_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")],
            [KeyboardButton("✅ Verify")],
        ],
        resize_keyboard=True,
    )

async def python_loading(msg: Message) -> None:
    # 3 sec / 3 steps
    steps = [
        "𝐏𝐘𝐓𝐇𝐎𝐍\n[░░░░░░░░░░] 0%\n{'status':'starting'}",
        "𝐏𝐘𝐓𝐇𝐎𝐍\n[██████░░░░] 60%\n{'status':'loading'}",
        "𝐏𝐘𝐓𝐇𝐎𝐍\n[██████████] 100%\n{'status':'ready ✅'}",
    ]
    m = await msg.reply_text(f"<pre>{steps[0]}</pre>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await m.edit_text(f"<pre>{steps[1]}</pre>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await m.edit_text(f"<pre>{steps[2]}</pre>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)

WELCOME_MSG = (
    "🌟 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐀𝐈 𝐔𝐍𝐈𝐏𝐈𝐍 𝐒𝐇𝐎𝐏 🌟\n\n"
    "🎮 𝐘𝐨𝐮𝐫 𝐓𝐫𝐮𝐬𝐭𝐞𝐝 𝐔𝐧𝐢𝐩𝐢𝐧 & 𝐃𝐢𝐚𝐦𝐨𝐧𝐝 𝐌𝐚𝐫𝐤𝐞𝐭\n\n"
    "✨ 𝐇𝐞𝐫𝐞 𝐲𝐨𝐮 𝐠𝐞𝐭 —\n"
    "• ⚡ 𝐈𝐧𝐬𝐭𝐚𝐧𝐭 𝐔𝐧𝐢𝐩𝐢𝐧 𝐂𝐨𝐝𝐞𝐬\n"
    "• 💎 𝐒𝐞𝐜𝐮𝐫𝐞 𝐃𝐢𝐚𝐦𝐨𝐧𝐝 𝐎𝐫𝐝𝐞𝐫 (𝐀𝐝𝐦𝐢𝐧-𝐕𝐞𝐫𝐢𝐟𝐢𝐞𝐝)\n"
    "• 💳 𝐒𝐚𝐟𝐞 𝐀𝐝𝐝 𝐌𝐨𝐧𝐞𝐲 𝐒𝐲𝐬𝐭𝐞𝐦\n"
    "• 🎁 𝐑𝐞𝐟𝐞𝐫 & 𝐄𝐚𝐫𝐧 𝐁𝐨𝐧𝐮𝐬\n\n"
    "🚀 𝐅𝐚𝐬𝐭 • 𝐒𝐞𝐜𝐮𝐫𝐞 • 𝐏𝐫𝐨𝐟𝐞𝐬𝐬𝐢𝐨𝐧𝐚𝐥\n\n"
    "👇 𝐍𝐢𝐜𝐡𝐞𝐫 𝐌𝐞𝐧𝐮 𝐭𝐡𝐞𝐤𝐞 𝐬𝐭𝐚𝐫𝐭 𝐤𝐨𝐫𝐮𝐧"
)

# -------------------- NOTIFY HELPERS --------------------

async def notify_admin(ctx: ContextTypes.DEFAULT_TYPE, text: str, parse_html: bool = False, kb_inline: InlineKeyboardMarkup = None, photo_message: Message = None) -> None:
    if sget("notifications", "ON") != "ON":
        return
    for aid in ADMIN_IDS:
        try:
            if photo_message and photo_message.photo:
                file_id = photo_message.photo[-1].file_id
                await ctx.bot.send_photo(chat_id=aid, photo=file_id, caption=text, parse_mode=ParseMode.HTML if parse_html else None, reply_markup=kb_inline)
            else:
                await ctx.bot.send_message(chat_id=aid, text=text, parse_mode=ParseMode.HTML if parse_html else None, reply_markup=kb_inline)
        except Exception:
            pass

# -------------------- STATE MACHINE --------------------

def set_state(ctx: ContextTypes.DEFAULT_TYPE, uid: int, st: str, data: Optional[dict] = None) -> None:
    if data is None:
        data = {}
    ctx.application.bot_data.setdefault("state", {})
    ctx.application.bot_data["state"][uid] = {"st": st, "data": data, "ts": now_ts()}

def get_state(ctx: ContextTypes.DEFAULT_TYPE, uid: int) -> Tuple[str, dict]:
    st = ctx.application.bot_data.get("state", {}).get(uid)
    if not st:
        return ("", {})
    return (st.get("st", ""), st.get("data", {}) or {})

def clear_state(ctx: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    if "state" in ctx.application.bot_data and uid in ctx.application.bot_data["state"]:
        del ctx.application.bot_data["state"][uid]

# -------------------- HANDLERS --------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user(update.effective_user)
    cleanup_history()

    u = uget(update.effective_user.id)
    if u and int(u["banned"]) == 1 and not is_admin(update.effective_user.id):
        await update.message.reply_text(F("You are banned. Use Support to contact admin."), reply_markup=banned_kb(update.effective_user.id))
        return

    if sget("maintenance", "OFF") == "ON" and not is_admin(update.effective_user.id):
        await update.message.reply_text(F("Maintenance mode is ON. Please use Support."), reply_markup=banned_kb(update.effective_user.id))
        return

    # referral start param
    if ctx.args and len(ctx.args) >= 1 and ctx.args[0].startswith("ref_"):
        try:
            refid = int(ctx.args[0].split("_", 1)[1])
            uid = update.effective_user.id
            if refid != uid:
                cur = uget(uid)
                if cur and cur["referrer_id"] is None:
                    uupdate(uid, referrer_id=refid)
                    # increment referral count for referrer (if exists)
                    if uget(refid):
                        uupdate(refid, referral_count=int(uget(refid)["referral_count"]) + 1)
        except Exception:
            pass

    if not await is_joined(update, ctx):
        await update.message.reply_text(F("Access locked. Join channel then press Verify."), reply_markup=join_kb())
        return

    await python_loading(update.message)
    await update.message.reply_text(WELCOME_MSG, reply_markup=home_kb(update.effective_user.id))
    clear_state(ctx, update.effective_user.id)

async def handle_verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user(update.effective_user)
    if await is_joined(update, ctx):
        await python_loading(update.message)
        await update.message.reply_text(WELCOME_MSG, reply_markup=home_kb(update.effective_user.id))
    else:
        await update.message.reply_text(F("Join channel first, then press Verify."), reply_markup=join_kb())

# -------------------- MENU VIEWS --------------------

def rank_from_total(total: int) -> str:
    if total >= 5000:
        return "Gold"
    if total >= 1000:
        return "Silver"
    return "Bronze"

async def show_unipin_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    prods = get_products("UC")
    if not prods:
        await update.message.reply_text(F("No products. Admin will add soon."), reply_markup=home_kb(update.effective_user.id))
        return
    lines = [f"<b>{F('UNIPIN PACKAGES')}</b>", "━━━━━━━━━━━━━━━━━━"]
    for p in prods:
        stock = get_uc_stock(p["key"])
        if stock <= 0:
            lines.append(f"• <b>{F(\'PRODUCT\')}</b>: <b>{F(p[\'name\'])}</b>\n  {F('PRICE')}: {F('Tk')} {F(str(p['price']))}\n  {F('STOCK')}: {F('0')} ({F('Out Of Stock')})")
        else:
            lines.append(f"• <b>{F(\'PRODUCT\')}</b>: <b>{F(p[\'name\'])}</b>\n  {F('PRICE')}: {F('Tk')} {F(str(p['price']))}\n  {F('STOCK')}: {F(str(stock))}")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(F("Select a package from buttons below."))
    # buttons
    rows = []
    row = []
    for p in prods:
        row.append(f"🎫 {p['name']}")
        if len(row) == 2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append(["⬅ Back"])
    await update.message.reply_text("\n".join(lines), reply_markup=kb(rows))

async def show_diamond_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    prods = get_products("DM")
    if not prods:
        await update.message.reply_text(F("No diamond packages. Admin will add soon."), reply_markup=home_kb(update.effective_user.id))
        return
    lines = [f"<b>{F('AVAILABLE DIAMOND PACKAGES')}</b>", "━━━━━━━━━━━━━━━━━━"]
    for p in prods:
        stock = get_dm_stock(p["key"])
        if stock <= 0:
            lines.append(f"• <b>{F(p[\'name\'])}</b> → {F('Tk')} {F(str(p['price']))} ({F('Stock')}: {F('0')})")
        else:
            lines.append(f"• <b>{F(p[\'name\'])}</b> → {F('Tk')} {F(str(p['price']))} ({F('Stock')}: {F(str(stock))})")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(F("Select a package from buttons below."))
    rows = []
    row=[]
    for p in prods:
        row.append(f"💎 {p['name']}")
        if len(row)==2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append(["⬅ Back"])
    await update.message.reply_text("\n".join(lines), reply_markup=kb(rows))

async def show_my_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = uget(update.effective_user.id)
    total = int(u["total_purchase"])
    rank = rank_from_total(total)
    msg = (
        f"👤 {F('My Account')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{F('ID')}: {mono(str(u['user_id']))}\n"
        f"{F('Name')}: {F(u['name'] or '')}\n"
        f"{F('Balance')}: {F('Tk')} {F(str(u['balance']))}\n"
        f"{F('Bonus')}: {F('Tk')} {F(str(u['bonus']))}\n"
        f"{F('Due')}: {F('Tk')} {F(str(u['due']))}\n"
        f"{F('Due Limit')}: {F('Tk')} {F(str(u['due_limit']))}\n"
        f"{F('Rank')}: {F(rank)}\n"
        f"{F('Warnings')}: {F(str(u['warnings']))}\n"
        f"{F('Last Active')}: {F(fmt_time(int(u['last_active_ts']))) }\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=home_kb(update.effective_user.id))

async def show_dev_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        f"ℹ️ {F('DEV & INFO')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🤖 {F('Bot Name')}: {F('Hasan Shop Bot')}\n"
        f"🟢 {F('Status')}: {F('Online & Working')}\n"
        f"⚙️ {F('Version')}: {F('Final')}\n"
        f"👨‍💻 {F('Developer')}: {F('@hasan_34')}\n"
        f"📢 {F('Official Channel')}: {F('@'+FORCE_JOIN_CHANNEL)}\n"
        f"🕒 {F('Time')}: {F(fmt_time())}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, reply_markup=home_kb(update.effective_user.id))

async def show_refer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = uget(update.effective_user.id)
    bonus = int(sget("ref_bonus","20"))
    msg = (
        f"👥 {F('REFER & EARN')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {F('Your Referral Link')}:\n"
        f"{mono(f'https://t.me/{ctx.bot.username}?start=ref_{update.effective_user.id}')}\n\n"
        f"👤 {F('Total Refers')}: {F(str(u['referral_count']))}\n"
        f"💰 {F('Total Bonus Earned')}: {F('Tk')} {F(str(u['referral_bonus_earned']))}\n\n"
        f"🎁 {F('Refer Bonus')}: {F('Tk')} {F(str(bonus))}\n"
        f"ℹ️ {F('Condition')}: {F('Referred user buys Tk 1000+ first time.')}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=home_kb(update.effective_user.id))

# -------------------- ORDERS (User) --------------------

async def orders_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        F("Orders: choose option"),
        reply_markup=kb([["⏳ Pending Orders", "🔎 Check Order by ID"], ["⬅ Back"]])
    )

async def show_pending_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    with db() as c:
        rows = c.execute(
            "SELECT order_id,pname,status,created_ts FROM orders WHERE user_id=? AND status='PENDING' ORDER BY created_ts DESC LIMIT 30",
            (uid,),
        ).fetchall()
    if not rows:
        await update.message.reply_text(F("No pending orders."), reply_markup=home_kb(uid))
        return
    out = [F("PENDING ORDERS"), "━━━━━━━━━━━━━━━━━━"]
    for r in rows:
        out.append(f"🆔 {r['order_id']} | {r['pname']} | {r['status']} | {fmt_time(int(r['created_ts']))}")
    await update.message.reply_text("\n".join(out), reply_markup=home_kb(uid))

async def start_check_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(ctx, update.effective_user.id, "ORDER_CHECK", {})
    await update.message.reply_text(F("Send Order ID (example: ORD-123456)"), reply_markup=back_kb())

async def handle_order_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, _ = get_state(ctx, uid)
    if st != "ORDER_CHECK":
        return
    oid = (update.message.text or "").strip()
    if not oid:
        await update.message.reply_text(F("Invalid Order ID."), reply_markup=back_kb())
        return
    with db() as c:
        r = c.execute(
            "SELECT order_id,pname,status,uid,price,created_ts,updated_ts FROM orders WHERE order_id=?",
            (oid,),
        ).fetchone()
    if not r:
        await update.message.reply_text(F("Order not found."), reply_markup=home_kb(uid))
        clear_state(ctx, uid)
        return
    # user can only see own order unless admin
    if int(r.get("order_id") is not None) and (not is_admin(uid)):
        with db() as c:
            owner = c.execute("SELECT user_id FROM orders WHERE order_id=?", (oid,)).fetchone()
        if owner and int(owner["user_id"]) != uid:
            await update.message.reply_text(F("Order not found."), reply_markup=home_kb(uid))
            clear_state(ctx, uid)
            return

    msg = (
        f"📦 {F('ORDER INFO')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 {F('Order ID')}: {mono(r['order_id'])}\n"
        f"📦 {F('Order')}: {F(r['pname'])}\n"
        f"✅ {F('Status')}: {F(r['status'])}\n"
        f"🆔 {F('UID')}: {mono(r.get('uid') or '-') }\n"
        f"💰 {F('Price')}: {F('Tk')} {F(str(r['price']))}\n"
        f"🕒 {F('Created')}: {F(fmt_time(int(r['created_ts'])))}\n"
        f"🕒 {F('Updated')}: {F(fmt_time(int(r['updated_ts'])))}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=home_kb(uid))
    clear_state(ctx, uid)


# -------------------- PURCHASE FLOWS --------------------

def gen_order_id() -> str:
    return f"ORD-{secrets.randbelow(900000)+100000}"

def gen_pay_id() -> str:
    return f"PAY-{secrets.randbelow(900000)+100000}"

async def start_unipin_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pname: str) -> None:
    # pname is button text like "🎫 80 UC" -> match product by name
    name = pname.replace("🎫", "").strip()
    p = None
    for x in get_products("UC"):
        if x["name"].strip().lower() == name.lower():
            p = x
            break
    if not p:
        await update.message.reply_text(F("Product not found."), reply_markup=home_kb(update.effective_user.id))
        return
    stock = get_uc_stock(p["key"])
    msg = (
        f"⚠️ {F('CONFIRM PURCHASE')}\n\n"
        f"{F('Product')}: {F(p['name'])}\n"
        f"{F('Price')}: {F('Tk')} {F(str(p['price']))}\n"
        f"{F('Stock')}: {F(str(stock))}\n\n"
        f"{F('Confirm to buy 1 code. Balance will be deducted only after confirm.')}"
    )
    set_state(ctx, update.effective_user.id, "UC_CONFIRM", {"pkey": p["key"]})
    await update.message.reply_text(msg, reply_markup=kb([["✅ Confirm Buy"], ["⬅ Back"]]))

async def do_unipin_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "UC_CONFIRM":
        return
    pkey = data.get("pkey","")
    p = get_product(pkey)
    if not p:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Product not found."), reply_markup=home_kb(uid))
        return
    stock = get_uc_stock(pkey)
    if stock <= 0:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Out of stock."), reply_markup=home_kb(uid))
        await notify_admin(ctx, F(f"Out of stock attempt: {p['name']} by {uid}"))
        return

    u = uget(uid)
    price = int(p["price"])
    bal = int(u["balance"])
    due = int(u["due"])
    due_limit = int(u["due_limit"])
    old_bal = bal
    old_due = due

    # pay with balance first, then due if needed
    need = price
    pay_from_bal = min(bal, need)
    need -= pay_from_bal
    new_bal = bal - pay_from_bal
    new_due = due
    if need > 0:
        # use due if within limit
        if due + need > due_limit:
            clear_state(ctx, uid)
            await update.message.reply_text(F("Insufficient balance. Please Add Money."), reply_markup=home_kb(uid))
            return
        new_due = due + need
        need = 0

    # pop code
    code = pop_one_code(pkey, uid)
    if not code:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Out of stock."), reply_markup=home_kb(uid))
        return

    # commit user update + total_purchase
    uupdate(uid, balance=new_bal, due=new_due, total_purchase=int(u["total_purchase"]) + price)

    # referral bonus check (threshold on first purchase >= min and not yet credited)
    await maybe_referral_credit(ctx, uid, price)

    # history
    add_history(uid, "code", f"Unipin {p['name']} Tk {price} Code: {code}")
    add_history(uid, "purchase", f"Spent Tk {price} on {p['name']}")

    # user messages
    tmsg = (
        f"✅ {F('PURCHASE SUCCESS')}\n\n"
        f"{F('You bought')}: {F(p['name'])}\n"
        f"{F('Amount')}: {F('Tk')} {F(str(price))}\n"
        f"{F('Time')}: {F(fmt_time())}\n\n"
        f"🔐 {F('YOUR CODE')}:\n{mono(code)}\n\n"
        f"👉 {F('Tap code to copy')}"
    )
    await update.message.reply_text(tmsg, parse_mode=ParseMode.HTML, reply_markup=home_kb(uid))

    bal_msg = (
        f"💳 {F('BALANCE UPDATE')}\n\n"
        f"{F('Old Balance')}: {F('Tk')} {F(str(old_bal))}\n"
        f"{F('Spent')}: {F('Tk')} {F(str(price))}\n"
        f"{F('New Balance')}: {F('Tk')} {F(str(new_bal))}\n"
    )
    await update.message.reply_text(bal_msg, reply_markup=home_kb(uid))

    # due change note
    if new_due != old_due:
        await update.message.reply_text(
            f"💳 {F('DUE UPDATE')}\n\n{F('Old Due')}: {F('Tk')} {F(str(old_due))}\n{F('New Due')}: {F('Tk')} {F(str(new_due))}",
            reply_markup=home_kb(uid)
        )

    # admin sold notification with remaining stock
    remain = get_uc_stock(pkey)
    sold = (
        f"🛒 {F('SOLD')}\n\n"
        f"👤 {F('User')}: {mono(str(uid))}\n"
        f"📦 {F('Product')}: {F(p['name'])}\n"
        f"💰 {F('Price')}: {F('Tk')} {F(str(price))}\n"
        f"🔐 {F('Code')}: {mono(code)}\n"
        f"📦 {F('Remaining Stock')}: {F(str(remain))}\n"
        f"⏰ {F('Time')}: {F(fmt_time())}"
    )
    await notify_admin(ctx, sold, parse_html=True)

    # low stock alert
    try:
        thr = int(sget("low_stock_threshold","3"))
        if remain <= thr:
            await notify_admin(ctx, f"⚠️ {F('LOW STOCK ALERT')}\n\n{F(p['name'])} → {F('Stock')}: {F(str(remain))}")
    except Exception:
        pass

    clear_state(ctx, uid)

async def start_diamond_uid(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pname: str) -> None:
    name = pname.replace("💎", "").strip()
    p = None
    for x in get_products("DM"):
        if x["name"].strip().lower() == name.lower():
            p = x
            break
    if not p:
        await update.message.reply_text(F("Package not found."), reply_markup=home_kb(update.effective_user.id))
        return
    set_state(ctx, update.effective_user.id, "DM_WAIT_UID", {"pkey": p["key"]})
    await update.message.reply_text(F("Send your Free Fire UID."), reply_markup=back_kb())

async def start_diamond_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid_txt: str) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "DM_WAIT_UID":
        return
    ffuid = uid_txt.strip()
    if not re.fullmatch(r"[0-9]{10,12}", ffuid):
        await update.message.reply_text("❌ ভুল UID
১০–১২ digit নাম্বার দিন", reply_markup=back_kb())
        return
    pkey = data.get("pkey","")
    p = get_product(pkey)
    if not p:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Package not found."), reply_markup=home_kb(uid))
        return
    stock = get_dm_stock(pkey)
    msg = (
        f"⚠️ {F('CONFIRM ORDER')}\n\n"
        f"{F('Package')}: {F(p['name'])}\n"
        f"{F('Price')}: {F('Tk')} {F(str(p['price']))}\n"
        f"{F('UID')}: {mono(ffuid)}\n"
        f"{F('Stock')}: {F(str(stock))}\n\n"
        f"{F('Confirm to place order. Admin will approve/reject.')}"
    )
    set_state(ctx, uid, "DM_CONFIRM", {"pkey": pkey, "ffuid": ffuid})
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb([["✅ Confirm Order"], ["⬅ Back"]]))

async def do_diamond_place(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "DM_CONFIRM":
        return
    pkey = data.get("pkey","")
    ffuid = data.get("ffuid","")
    p = get_product(pkey)
    if not p:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Package not found."), reply_markup=home_kb(uid))
        return
    stock = get_dm_stock(pkey)
    price = int(p["price"])
    if stock <= 0:
        clear_state(ctx, uid)
        await update.message.reply_text(F("Out of stock."), reply_markup=home_kb(uid))
        await notify_admin(ctx, F(f"Out of stock diamond attempt: {p['name']} by {uid}"))
        return

    u = uget(uid)
    bal = int(u["balance"])
    due = int(u["due"])
    due_limit = int(u["due_limit"])
    old_bal = bal
    old_due = due

    need = price
    pay_from_bal = min(bal, need)
    need -= pay_from_bal
    new_bal = bal - pay_from_bal
    new_due = due
    if need > 0:
        if due + need > due_limit:
            clear_state(ctx, uid)
            await update.message.reply_text(F("Insufficient balance. Please Add Money."), reply_markup=home_kb(uid))
            return
        new_due = due + need

    # reserve by deducting now; refund on reject
    uupdate(uid, balance=new_bal, due=new_due, total_purchase=int(u["total_purchase"]) + price)

    order_id = gen_order_id()
    ts = now_ts()
    with db() as c:
        c.execute(
            "INSERT INTO orders(order_id,user_id,cat,pkey,pname,price,uid,status,created_ts,updated_ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (order_id, uid, "DM", pkey, p["name"], price, ffuid, "PENDING", ts, ts),
        )
    add_history(uid, "purchase", f"Diamond order {p['name']} Tk {price} UID {ffuid} Order {order_id}")

    await maybe_referral_credit(ctx, uid, price)

    user_msg = (
        f"⏳ {F('ORDER PLACED')}\n\n"
        f"{F('Package')}: {F(p['name'])}\n"
        f"{F('UID')}: {mono(ffuid)}\n"
        f"{F('Order ID')}: {mono(order_id)}\n"
        f"{F('Time')}: {F(fmt_time())}\n\n"
        f"{F('Admin will review your order.')}"
    )
    await update.message.reply_text(user_msg, parse_mode=ParseMode.HTML, reply_markup=home_kb(uid))

    # admin inline approve/reject
    kb_inline = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"dm_app|{order_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"dm_rej|{order_id}")],
    ])
    admin_msg = (
        f"💎 {F('DIAMOND ORDER')}\n\n"
        f"👤 {F('User')}: {mono(str(uid))}\n"
        f"📦 {F('Package')}: {F(p['name'])}\n"
        f"🆔 {F('UID')}: {mono(ffuid)}\n"
        f"💰 {F('Price')}: {F('Tk')} {F(str(price))}\n"
        f"🆔 {F('Order ID')}: {mono(order_id)}\n"
        f"⏰ {F('Time')}: {F(fmt_time(ts))}"
    )
    await notify_admin(ctx, admin_msg, parse_html=True, kb_inline=kb_inline)

    bal_msg = (
        f"💳 {F('BALANCE UPDATE')}\n\n"
        f"{F('Old Balance')}: {F('Tk')} {F(str(old_bal))}\n"
        f"{F('Spent')}: {F('Tk')} {F(str(price))}\n"
        f"{F('New Balance')}: {F('Tk')} {F(str(new_bal))}\n"
    )
    await update.message.reply_text(bal_msg, reply_markup=home_kb(uid))
    if new_due != old_due:
        await update.message.reply_text(
            f"💳 {F('DUE UPDATE')}\n\n{F('Old Due')}: {F('Tk')} {F(str(old_due))}\n{F('New Due')}: {F('Tk')} {F(str(new_due))}",
            reply_markup=home_kb(uid)
        )

    clear_state(ctx, uid)

# -------------------- REFERRAL CREDIT --------------------

async def maybe_referral_credit(ctx: ContextTypes.DEFAULT_TYPE, buyer_id: int, purchase_amount: int) -> None:
    # If buyer has referrer and this is buyer's first qualifying purchase, credit bonus once.
    if sget("ref_on","ON") != "ON":
        return
    min_amt = int(sget("ref_min_purchase","1000"))
    if purchase_amount < min_amt:
        return
    buyer = uget(buyer_id)
    if not buyer:
        return
    refid = buyer["referrer_id"]
    if refid is None:
        return
    # ensure not already credited via referral_bonus_earned for this buyer:
    # We'll store a history marker "ref_credit:<buyer>"
    marker = f"ref_credit:{buyer_id}"
    with db() as c:
        r = c.execute("SELECT 1 FROM history WHERE user_id=? AND type='sys' AND text=?", (int(refid), marker)).fetchone()
        if r:
            return
        bonus = int(sget("ref_bonus","20"))
        refu = uget(int(refid))
        if not refu:
            return
        uupdate(int(refid), bonus=int(refu["bonus"]) + bonus, referral_bonus_earned=int(refu["referral_bonus_earned"]) + bonus)
        # marker
        c.execute("INSERT INTO history(user_id,type,text,ts) VALUES(?,?,?,?)", (int(refid), "sys", marker, now_ts()))
    # notify referrer + admin
    try:
        await ctx.bot.send_message(
            chat_id=int(refid),
            text=f"🎉 {F('REFERRAL BONUS RECEIVED')}\n\n{F('Buyer')}: {mono(str(buyer_id))}\n{F('Bonus')}: {F('Tk')} {F(str(bonus))}\n{F('Time')}: {F(fmt_time())}",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass
    await notify_admin(ctx, f"🎯 {F('REFERRAL BONUS')}\n\n{F('Referrer')}: {mono(str(refid))}\n{F('Buyer')}: {mono(str(buyer_id))}\n{F('Bonus')}: {F('Tk')} {F(str(bonus))}", parse_html=True)

# -------------------- ADD MONEY FLOW --------------------

async def start_add_money(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(ctx, update.effective_user.id, "AMT_WAIT_AMOUNT", {})
    await update.message.reply_text(F("How much Add Money? Send amount in Tk."), reply_markup=back_kb())

def list_methods() -> List[str]:
    with db() as c:
        rows = c.execute("SELECT name FROM payment_methods ORDER BY name ASC").fetchall()
        return [r["name"] for r in rows]

def get_method_details(name: str) -> Optional[str]:
    with db() as c:
        r = c.execute("SELECT details FROM payment_methods WHERE name=?", (name,)).fetchone()
        return r["details"] if r else None

async def handle_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "AMT_WAIT_AMOUNT":
        return
    txt = update.message.text.strip()
    if not txt.isdigit():
        await update.message.reply_text(F("Send amount number only."), reply_markup=back_kb())
        return
    amt = int(txt)
    if amt <= 0:
        await update.message.reply_text(F("Invalid amount."), reply_markup=back_kb())
        return
    methods = list_methods()
    if not methods:
        clear_state(ctx, uid)
        await update.message.reply_text(F("No payment methods. Ask admin."), reply_markup=home_kb(uid))
        return
    set_state(ctx, uid, "AMT_PICK_METHOD", {"amount": amt})
    rows = []
    row=[]
    for m in methods:
        row.append(f"💳 {m}")
        if len(row)==2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append(["⬅ Back"])
    await update.message.reply_text(F("Select payment method."), reply_markup=kb(rows))

async def handle_method_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "AMT_PICK_METHOD":
        return
    mname = update.message.text.replace("💳","").strip()
    details = get_method_details(mname)
    if not details:
        await update.message.reply_text(F("Method not found."), reply_markup=home_kb(uid))
        clear_state(ctx, uid)
        return
    data["method"] = mname
    set_state(ctx, uid, "AMT_SHOW_DETAILS", data)
    msg = f"💳 {F('PAYMENT DETAILS')}\n\n{mono(details)}\n\n{F('Press Next then send TxID and Screenshot.')}"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb([["➡ Next"], ["⬅ Back"]]))

async def handle_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "AMT_SHOW_DETAILS":
        return
    set_state(ctx, uid, "AMT_WAIT_TXID", data)
    await update.message.reply_text(F("Send TxID now."), reply_markup=back_kb())

async def handle_txid(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "AMT_WAIT_TXID":
        return
    txid = update.message.text.strip()
    if len(txid) < 4:
        await update.message.reply_text(F("Invalid TxID."), reply_markup=back_kb())
        return
    data["txid"] = txid
    ss_on = (sget("ss_must","ON") == "ON")
    if ss_on:
        set_state(ctx, uid, "AMT_WAIT_SS", data)
        await update.message.reply_text(F("Send screenshot photo now."), reply_markup=back_kb())
    else:
        # submit without screenshot
        await submit_payment(update, ctx, data, photo_message=None)

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "AMT_WAIT_SS":
        return
    await submit_payment(update, ctx, data, photo_message=update.message)

async def submit_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE, data: dict, photo_message: Optional[Message]) -> None:
    uid = update.effective_user.id
    amt = int(data["amount"])
    method = data["method"]
    txid = data["txid"]
    pay_id = gen_pay_id()
    ts = now_ts()
    with db() as c:
        c.execute(
            "INSERT INTO payments(pay_id,user_id,amount,method,txid,status,created_ts,updated_ts) VALUES(?,?,?,?,?,?,?,?)",
            (pay_id, uid, amt, method, txid, "PENDING", ts, ts),
        )
    add_history(uid, "payment", f"Add Money Tk {amt} Method {method} TxID {txid} Status PENDING")

    kb_inline = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"pay_app|{pay_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej|{pay_id}")],
    ])
    admin_msg = (
        f"💳 {F('ADD MONEY REQUEST')}\n\n"
        f"👤 {F('User')}: {mono(str(uid))}\n"
        f"💰 {F('Amount')}: {F('Tk')} {F(str(amt))}\n"
        f"💳 {F('Method')}: {F(method)}\n"
        f"🧾 {F('TxID')}: {mono(txid)}\n"
        f"⏰ {F('Time')}: {F(fmt_time(ts))}"
    )
    await notify_admin(ctx, admin_msg, parse_html=True, kb_inline=kb_inline, photo_message=photo_message)

    await update.message.reply_text(F("Request submitted. Admin will review."), reply_markup=home_kb(uid))
    clear_state(ctx, uid)

# -------------------- ADMIN CALLBACKS (approve/reject) --------------------

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    uid = q.from_user.id
    if not is_admin(uid):
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    data = q.data or ""
    try:
        typ, oid = data.split("|", 1)
    except ValueError:
        return

    if typ in ("dm_app","dm_rej"):
        await handle_dm_decision(q, ctx, oid, approve=(typ=="dm_app"))
    elif typ in ("pay_app","pay_rej"):
        await handle_pay_decision(q, ctx, oid, approve=(typ=="pay_app"))

async def handle_dm_decision(q, ctx, order_id: str, approve: bool) -> None:
    with db() as c:
        od = c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not od:
            await q.edit_message_text(F("Order not found."))
            return
        if od["status"] not in ("PENDING",):
            await q.edit_message_text(F("Already handled."))
            return
        # update status
        new_status = "COMPLETED" if approve else "REJECTED"
        c.execute("UPDATE orders SET status=?, updated_ts=? WHERE order_id=?", (new_status, now_ts(), order_id))
    buyer_id = int(od["user_id"])
    price = int(od["price"])
    pkey = od["pkey"]
    pname = od["pname"]
    ffuid = od["uid"] or ""
    if approve:
        # reduce dm stock by 1 (if possible)
        stock = get_dm_stock(pkey)
        if stock > 0:
            set_dm_stock(pkey, stock-1)
        user_msg = (
            f"✅ {F('ORDER COMPLETE')}\n\n"
            f"{F('Order')}: {F(pname)}\n"
            f"{F('Status')}: {F('Completed')}\n"
            f"{F('Time')}: {F(fmt_time())}\n"
            f"{F('Order ID')}: {mono(order_id)}"
        )
        try:
            await ctx.bot.send_message(buyer_id, user_msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await q.edit_message_text(F("Approved ✅"))
    else:
        # refund: add back to balance (and reduce due if it was used; simplest: refund to balance)
        bu = uget(buyer_id)
        if bu:
            uupdate(buyer_id, balance=int(bu["balance"]) + price)
        user_msg = (
            f"❌ {F('ORDER CANCELLED')}\n\n"
            f"{F('Order')}: {F(pname)}\n"
            f"{F('Status')}: {F('Cancelled')}\n"
            f"{F('Refund')}: {F('Tk')} {F(str(price))}\n"
            f"{F('Time')}: {F(fmt_time())}\n"
            f"{F('Order ID')}: {mono(order_id)}"
        )
        try:
            await ctx.bot.send_message(buyer_id, user_msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await q.edit_message_text(F("Rejected ❌ (Refunded)"))

async def handle_pay_decision(q, ctx, pay_id: str, approve: bool) -> None:
    with db() as c:
        p = c.execute("SELECT * FROM payments WHERE pay_id=?", (pay_id,)).fetchone()
        if not p:
            await q.edit_message_text(F("Payment not found."))
            return
        if p["status"] not in ("PENDING",):
            await q.edit_message_text(F("Already handled."))
            return
        new_status = "APPROVED" if approve else "REJECTED"
        c.execute("UPDATE payments SET status=?, updated_ts=? WHERE pay_id=?", (new_status, now_ts(), pay_id))
    buyer_id = int(p["user_id"])
    amt = int(p["amount"])
    bu = uget(buyer_id)
    if not bu:
        await q.edit_message_text(F("User missing."))
        return
    old_bal = int(bu["balance"])
    old_due = int(bu["due"])
    if approve:
        # add balance then auto-cut due
        new_bal = old_bal + amt
        new_due = old_due
        if old_due > 0:
            cut = min(new_bal, old_due)
            new_bal -= cut
            new_due = old_due - cut
        uupdate(buyer_id, balance=new_bal, due=new_due)
        add_history(buyer_id, "payment", f"Add Money approved Tk {amt}")
        user_msg = (
            f"✅ {F('ADD MONEY APPROVED')}\n\n"
            f"{F('Amount')}: {F('Tk')} {F(str(amt))}\n"
            f"{F('Old Balance')}: {F('Tk')} {F(str(old_bal))}\n"
            f"{F('New Balance')}: {F('Tk')} {F(str(new_bal))}\n"
            f"{F('Time')}: {F(fmt_time())}\n"
            f"{F('Pay ID')}: {mono(pay_id)}"
        )
        try:
            await ctx.bot.send_message(buyer_id, user_msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        # due update notify
        if new_due != old_due:
            try:
                await ctx.bot.send_message(
                    buyer_id,
                    f"💳 {F('DUE AUTO-CUT')}\n\n{F('Old Due')}: {F('Tk')} {F(str(old_due))}\n{F('New Due')}: {F('Tk')} {F(str(new_due))}",
                )
            except Exception:
                pass
        await q.edit_message_text(F("Approved ✅"))
    else:
        add_history(buyer_id, "payment", f"Add Money rejected Tk {amt}")
        try:
            await ctx.bot.send_message(buyer_id, f"❌ {F('ADD MONEY REJECTED')}\n\n{F('Pay ID')}: {mono(pay_id)}", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await q.edit_message_text(F("Rejected ❌"))

# -------------------- ADMIN TOGGLES / SETTINGS --------------------

async def toggle_notifications(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    newv = "OFF" if sget("notifications","ON") == "ON" else "ON"
    sset("notifications", newv)
    await update.message.reply_text(F(f"Notifications: {newv}"), reply_markup=admin_kb())

async def toggle_ss_must(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    newv = "OFF" if sget("ss_must","ON") == "ON" else "ON"
    sset("ss_must", newv)
    await update.message.reply_text(F(f"SS Must: {newv}"), reply_markup=admin_kb())

async def toggle_maintenance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    newv = "OFF" if sget("maintenance","OFF") == "ON" else "ON"
    sset("maintenance", newv)
    await update.message.reply_text(F(f"Maintenance: {newv}"), reply_markup=admin_kb())
    # broadcast to users
    with db() as c:
        users = [r["user_id"] for r in c.execute("SELECT user_id FROM users").fetchall()]
    for uid in users:
        if is_admin(int(uid)):
            continue
        try:
            await ctx.bot.send_message(int(uid), F(f"Bot maintenance is now {newv}"))
        except Exception:
            pass

async def bonus_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        F("Bonus Settings: choose option"),
        reply_markup=kb([["🎁 Bonus ON/OFF", "🎁 All User Bonus Set"], ["🎁 Custom User Bonus"], ["⬅ Back"]])
    )

async def bonus_on_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    newv = "OFF" if sget("bonus_on","ON") == "ON" else "ON"
    sset("bonus_on", newv)
    await update.message.reply_text(F(f"Bonus system: {newv}"), reply_markup=admin_kb())

async def bonus_all_set_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "BONUS_ALL_WAIT", {})
    await update.message.reply_text(F("Send bonus amount (Tk) for ALL users."), reply_markup=back_kb())

async def bonus_custom_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "BONUS_CUST_UID", {})
    await update.message.reply_text(F("Send target user ID."), reply_markup=back_kb())

async def handle_bonus_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if not is_admin(uid):
        return
    txt = update.message.text.strip()
    if st == "BONUS_ALL_WAIT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return
        amt = int(txt)
        with db() as c:
            users = c.execute("SELECT user_id,bonus FROM users").fetchall()
            for r in users:
                c.execute("UPDATE users SET bonus=? WHERE user_id=?", (int(r["bonus"]) + amt, int(r["user_id"])))
        await update.message.reply_text(F(f"All user bonus added: Tk {amt}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
    elif st == "BONUS_CUST_UID":
        if not txt.isdigit():
            await update.message.reply_text(F("Send valid user ID."), reply_markup=back_kb()); return
        data["target"] = int(txt)
        set_state(ctx, uid, "BONUS_CUST_AMT", data)
        await update.message.reply_text(F("Send bonus amount (Tk)."), reply_markup=back_kb())
    elif st == "BONUS_CUST_AMT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return
        amt = int(txt)
        target = int(data["target"])
        tu = uget(target)
        if not tu:
            await update.message.reply_text(F("User not found."), reply_markup=admin_kb()); clear_state(ctx, uid); return
        uupdate(target, bonus=int(tu["bonus"]) + amt)
        await update.message.reply_text(F(f"Bonus added to {target}: Tk {amt}"), reply_markup=admin_kb())
        try:
            await ctx.bot.send_message(target, F(f"Bonus received: Tk {amt}"))
        except Exception:
            pass
        clear_state(ctx, uid)

# -------------------- REDEEM MANAGE --------------------

async def redeem_manage_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "RDM_AMT", {})
    await update.message.reply_text(F("Redeem amount (Tk) ?"), reply_markup=back_kb())

async def handle_redeem_admin_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if not is_admin(uid):
        return
    txt = update.message.text.strip()
    if st == "RDM_AMT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return
        data["amt"] = int(txt)
        set_state(ctx, uid, "RDM_CNT", data)
        await update.message.reply_text(F("How many codes generate?"), reply_markup=back_kb())
    elif st == "RDM_CNT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return
        cnt = int(txt)
        amt = int(data["amt"])
        codes_out = []
        with db() as c:
            for _ in range(max(1, min(cnt, 200))):
                code = "RDM-" + secrets.token_hex(3).upper()
                c.execute("INSERT INTO redeem_codes(code,amount,used,created_ts) VALUES(?,?,0,?)", (code, amt, now_ts()))
                codes_out.append(code)
        msg = F("Redeem codes generated:") + "\n" + "\n".join(codes_out)
        await update.message.reply_text(msg, reply_markup=admin_kb())
        clear_state(ctx, uid)

async def redeem_claim(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(ctx, update.effective_user.id, "RDM_CLAIM", {})
    await update.message.reply_text(F("Send your redeem code."), reply_markup=back_kb())

async def handle_redeem_claim_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, _ = get_state(ctx, uid)
    if st != "RDM_CLAIM":
        return
    code = update.message.text.strip().upper()
    with db() as c:
        r = c.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
        if not r or int(r["used"]) == 1:
            await update.message.reply_text(F("Invalid or used code."), reply_markup=home_kb(uid))
            clear_state(ctx, uid)
            return
        amt = int(r["amount"])
        c.execute("UPDATE redeem_codes SET used=1, used_by=?, used_ts=? WHERE code=?", (uid, now_ts(), code))
    u = uget(uid)
    uupdate(uid, bonus=int(u["bonus"]) + amt)
    add_history(uid, "redeem", f"Redeem {code} Tk {amt}")
    await update.message.reply_text(F(f"Redeem success: Tk {amt} added to bonus."), reply_markup=home_kb(uid))
    await notify_admin(ctx, f"🎟 {F('REDEEM CLAIMED')}\n\n{F('User')}: {mono(str(uid))}\n{F('Amount')}: {F('Tk')} {F(str(amt))}\n{F('Code')}: {mono(code)}", parse_html=True)
    clear_state(ctx, uid)

# -------------------- GIFT COIN --------------------

async def gift_coin_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        F("Gift Coin: choose option"),
        reply_markup=kb([["✅ Check Bonus", "🎁 Gift Balance"], ["⬅ Back"]])
    )

async def check_bonus(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if sget("bonus_on","ON") != "ON":
        await update.message.reply_text(F("Bonus system is OFF."), reply_markup=home_kb(update.effective_user.id))
        return
    u = uget(update.effective_user.id)
    await update.message.reply_text(F(f"Your bonus: Tk {u['bonus']}"), reply_markup=home_kb(update.effective_user.id))

async def gift_balance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(ctx, update.effective_user.id, "GIFT_UID", {})
    await update.message.reply_text(F("Send receiver user ID."), reply_markup=back_kb())

async def handle_gift_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    txt = update.message.text.strip()
    if st == "GIFT_UID":
        if not txt.isdigit():
            await update.message.reply_text(F("Send valid user ID."), reply_markup=back_kb()); return
        rid = int(txt)
        if rid == uid:
            await update.message.reply_text(F("Cannot gift to yourself."), reply_markup=back_kb()); return
        if not uget(rid):
            await update.message.reply_text(F("User not found."), reply_markup=back_kb()); return
        data["rid"] = rid
        set_state(ctx, uid, "GIFT_AMT", data)
        await update.message.reply_text(F("Send gift amount (Tk)."), reply_markup=back_kb())
    elif st == "GIFT_AMT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return
        amt = int(txt)
        if amt <= 0:
            await update.message.reply_text(F("Invalid amount."), reply_markup=back_kb()); return
        su = uget(uid)
        if int(su["balance"]) < amt:
            await update.message.reply_text(F("Insufficient balance. Please Add Money."), reply_markup=home_kb(uid))
            clear_state(ctx, uid)
            return
        rid = int(data["rid"])
        ru = uget(rid)
        uupdate(uid, balance=int(su["balance"]) - amt)
        uupdate(rid, balance=int(ru["balance"]) + amt)
        await update.message.reply_text(F(f"Gift sent to {rid}: Tk {amt}"), reply_markup=home_kb(uid))
        try:
            await ctx.bot.send_message(rid, F(f"You received gift: Tk {amt} from {uid}"))
        except Exception:
            pass
        clear_state(ctx, uid)

# -------------------- HISTORY --------------------

async def history_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(F("History: choose option"), reply_markup=kb([["📦 Code History", "💳 Payment History"], ["⬅ Back"]]))

async def show_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE, htype: str) -> None:
    cleanup_history()
    uid = update.effective_user.id
    with db() as c:
        rows = c.execute("SELECT text,ts FROM history WHERE user_id=? AND type=? ORDER BY ts DESC LIMIT 30", (uid, htype)).fetchall()
    if not rows:
        await update.message.reply_text(F("No history."), reply_markup=home_kb(uid))
        return
    out = [F("HISTORY"), "━━━━━━━━━━━━━━━━━━"]
    for r in rows:
        out.append(f"{F(fmt_time(int(r['ts'])))}\n{r['text']}\n")
    await update.message.reply_text("\n".join(out), reply_markup=home_kb(uid))

# -------------------- SUPPORT --------------------

async def support_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(ctx, update.effective_user.id, "SUPPORT_MSG", {})
    await update.message.reply_text(F("Write your message. Admin will reply."), reply_markup=back_kb())

async def handle_support_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, _ = get_state(ctx, uid)
    if st != "SUPPORT_MSG":
        return
    text = update.message.text
    await notify_admin(ctx, f"🆘 {F('SUPPORT')}\n\n{F('From')}: {mono(str(uid))}\n{F('Message')}: {F(text)}", parse_html=True)
    await update.message.reply_text(F("Sent to admin."), reply_markup=home_kb(uid))
    clear_state(ctx, uid)

# -------------------- ADMIN PANEL ACTIONS --------------------

async def open_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(F("Admin Panel"), reply_markup=admin_kb())

async def add_list_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cat: str) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "ADD_LIST", {"cat": cat})
    await update.message.reply_text(F("Paste lines format: KEY.NAME.PRICE (dot separated)\nBulk lines supported. No Done needed.\nUse ⬅ Back to exit."), reply_markup=back_kb())

async def add_list_collect(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "ADD_LIST":
        return
    if not is_admin(uid):
        return

    cat = data.get("cat", "UC")
    raw = (update.message.text or "").strip()
    if "|" in raw:
        await update.message.reply_text(F("Wrong format. Use: KEY.NAME.PRICE (dot separated)."), reply_markup=back_kb())
        return

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    added = 0
    failed = 0
    for ln in lines:
        parts = ln.split(".", 2)
        if len(parts) != 3:
            failed += 1
            continue
        k, n, pr = [p.strip() for p in parts]
        if not k or not n or not pr.isdigit():
            failed += 1
            continue
        add_product(k, n, int(pr), "UC" if cat == "UC" else "DM")
        added += 1

    await update.message.reply_text(
        F(f"Saved ✅ Items added: {added} | Failed: {failed}\nSend more lines or press ⬅ Back."),
        reply_markup=back_kb()
    )

async def add_list_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # Done button removed (locked). Kept for backward safety.
    clear_state(ctx, update.effective_user.id)
    await update.message.reply_text(F('Done.'), reply_markup=admin_kb())
(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    st, data = get_state(ctx, uid)
    if st != "ADD_LIST":
        return
    cat = data.get("cat","UC")
    raw_lines = []
    for chunk in data.get("lines", []):
        raw_lines.extend(chunk.splitlines())
    added = 0
    for ln in raw_lines:
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) != 3:
            continue
        k, n, pr = parts
        if not k or not n or not pr.isdigit():
            continue
        add_product(k, n, int(pr), "UC" if cat=="UC" else "DM")
        added += 1
    clear_state(ctx, uid)
    await update.message.reply_text(F(f"List saved. Items: {added}"), reply_markup=admin_kb())

async def add_code_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "ADD_CODE_KEY", {})
    await update.message.reply_text(F("Send product KEY for codes."), reply_markup=back_kb())

async def add_dm_qty_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "DMQ_KEY", {})
    await update.message.reply_text(F("Send Diamond product KEY."), reply_markup=back_kb())

async def code_remove_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "RM_KEY", {})
    await update.message.reply_text(F("Send product KEY to remove codes."), reply_markup=back_kb())

async def code_return_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "RT_KEY", {})
    await update.message.reply_text(F("Send product KEY to retrieve codes."), reply_markup=back_kb())

async def delete_product_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "DEL_KEY", {})
    await update.message.reply_text(F("Send product KEY to delete."), reply_markup=back_kb())

async def add_balance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cut: bool=False) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "BAL_UID", {"cut": cut})
    await update.message.reply_text(F("Send target user ID."), reply_markup=back_kb())

async def warn_ban_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "MOD_UID", {"mode": mode})
    await update.message.reply_text(F("Send target user ID."), reply_markup=back_kb())

async def send_all_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "SEND_ALL", {})
    await update.message.reply_text(F("Send message text to broadcast."), reply_markup=back_kb())

async def send_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "SEND_UID", {})
    await update.message.reply_text(F("Send user ID."), reply_markup=back_kb())

async def multi_id_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "MULTI_IDS", {})
    await update.message.reply_text(F("Send IDs (newline or comma)."), reply_markup=back_kb())

async def get_all_user_ids(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    with db() as c:
        ids = [str(r["user_id"]) for r in c.execute("SELECT user_id FROM users ORDER BY user_id ASC").fetchall()]
    if not ids:
        await update.message.reply_text(F("No users."), reply_markup=admin_kb()); return
    # chunk
    chunk = []
    size = 50
    for i in range(0, len(ids), size):
        chunk.append("\n".join(ids[i:i+size]))
    for part in chunk:
        await update.message.reply_text(part, reply_markup=admin_kb())

async def show_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    uc = get_products("UC")
    dm = get_products("DM")
    out = [F("STOCK"), "━━━━━━━━━━━━━━━━━━", F("UNIPIN")]
    for p in uc:
        out.append(f"{p['key']} - {p['name']} : {get_uc_stock(p['key'])}")
    out.append("━━━━━━━━━━━━━━━━━━")
    out.append(F("DIAMOND"))
    for p in dm:
        out.append(f"{p['key']} - {p['name']} : {get_dm_stock(p['key'])}")
    await update.message.reply_text("\n".join(out), reply_markup=admin_kb())

async def payment_methods_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    methods = list_methods()
    txt = F("Payment Methods:") + "\n" + "\n".join([f"- {m}" for m in methods]) if methods else F("No payment methods.")
    await update.message.reply_text(txt, reply_markup=kb([["➕ Set Method"], ["⬅ Back"]]))

async def set_method_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "PM_NAME", {})
    await update.message.reply_text(F("Send method name (e.g. bkash)."), reply_markup=back_kb())

async def referral_settings_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    on = sget("ref_on","ON")
    bonus = sget("ref_bonus","20")
    mn = sget("ref_min_purchase","1000")
    msg = f"{F('Referral Settings')}\n\n{F('Status')}: {F(on)}\n{F('Bonus')}: {F('Tk')} {F(bonus)}\n{F('Min Purchase')}: {F('Tk')} {F(mn)}"
    await update.message.reply_text(msg, reply_markup=kb([["🔁 Referral ON/OFF", "💰 Set Ref Bonus"], ["📉 Set Ref Min"], ["⬅ Back"]]))

async def referral_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    newv = "OFF" if sget("ref_on","ON") == "ON" else "ON"
    sset("ref_on", newv)
    await update.message.reply_text(F(f"Referral: {newv}"), reply_markup=admin_kb())

async def set_ref_bonus_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "REF_BONUS", {})
    await update.message.reply_text(F("Send referral bonus amount (Tk)."), reply_markup=back_kb())

async def set_ref_min_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_state(ctx, update.effective_user.id, "REF_MIN", {})
    await update.message.reply_text(F("Send referral min purchase amount (Tk)."), reply_markup=back_kb())

# -------------------- ADMIN TEXT FLOW HANDLER --------------------

async def handle_admin_flows(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if not is_admin(uid):
        return False
    st, data = get_state(ctx, uid)
    txt = update.message.text.strip()

    if st == "ADD_CODE_KEY":
        pkey = txt
        p = get_product(pkey)
        if not p or p["cat"] != "UC":
            await update.message.reply_text(F("Invalid UC key."), reply_markup=admin_kb())
            clear_state(ctx, uid)
            return True
        set_state(ctx, uid, "ADD_CODE_PASTE", {"pkey": pkey})
        await update.message.reply_text(F("Paste codes (one per line)."), reply_markup=back_kb())
        return True

    if st == "ADD_CODE_PASTE":
        pkey = data["pkey"]
        codes = [x.strip() for x in update.message.text.splitlines() if x.strip()]
        added, dup = add_codes(pkey, codes)
        await update.message.reply_text(F(f"Codes added: {added}, dup skipped: {dup}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "DMQ_KEY":
        pkey = txt
        p = get_product(pkey)
        if not p or p["cat"] != "DM":
            await update.message.reply_text(F("Invalid DM key."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        set_state(ctx, uid, "DMQ_QTY", {"pkey": pkey})
        await update.message.reply_text(F("Send qty number."), reply_markup=back_kb())
        return True

    if st == "DMQ_QTY":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return True
        qty = int(txt)
        pkey = data["pkey"]
        cur = get_dm_stock(pkey)
        set_dm_stock(pkey, cur + qty)
        await update.message.reply_text(F(f"DM stock updated. New stock: {cur+qty}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "RM_KEY":
        pkey = txt
        p = get_product(pkey)
        if not p or p["cat"] != "UC":
            await update.message.reply_text(F("Invalid UC key."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        set_state(ctx, uid, "RM_CODES", {"pkey": pkey})
        await update.message.reply_text(F("Paste codes to remove (one per line)."), reply_markup=back_kb())
        return True

    if st == "RM_CODES":
        pkey = data["pkey"]
        codes = [x.strip() for x in update.message.text.splitlines() if x.strip()]
        removed = remove_codes(pkey, codes)
        await update.message.reply_text(F(f"Removed: {removed}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "RT_KEY":
        pkey = txt
        p = get_product(pkey)
        if not p:
            await update.message.reply_text(F("Key not found."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        codes = get_all_codes(pkey)
        if not codes:
            await update.message.reply_text(F("No codes for this key."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        # chunk
        chunk = []
        size = 40
        for i in range(0, len(codes), size):
            chunk.append("\n".join(codes[i:i+size]))
        for part in chunk:
            await update.message.reply_text(part, reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "DEL_KEY":
        pkey = txt
        if not get_product(pkey):
            await update.message.reply_text(F("Key not found."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        delete_product(pkey)
        await update.message.reply_text(F(f"Deleted product: {pkey}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "BAL_UID":
        if not txt.isdigit():
            await update.message.reply_text(F("Send valid user ID."), reply_markup=back_kb()); return True
        data["target"] = int(txt)
        set_state(ctx, uid, "BAL_AMT", data)
        await update.message.reply_text(F("Send amount (Tk)."), reply_markup=back_kb())
        return True

    if st == "BAL_AMT":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return True
        amt = int(txt)
        target = int(data["target"])
        tu = uget(target)
        if not tu:
            await update.message.reply_text(F("User not found."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        old = int(tu["balance"])
        cut = bool(data.get("cut", False))
        new = old - amt if cut else old + amt
        if new < 0:
            new = 0
        uupdate(target, balance=new)
        await update.message.reply_text(F(f"Balance updated for {target}."), reply_markup=admin_kb())
        try:
            await ctx.bot.send_message(target, f"💳 {F('BALANCE UPDATE')}\n\n{F('Old Balance')}: {F('Tk')} {F(str(old))}\n{F('Change')}: {F('-' if cut else '+')}{F('Tk')} {F(str(amt))}\n{F('New Balance')}: {F('Tk')} {F(str(new))}")
        except Exception:
            pass
        clear_state(ctx, uid)
        return True

    if st == "MOD_UID":
        if not txt.isdigit():
            await update.message.reply_text(F("Send valid user ID."), reply_markup=back_kb()); return True
        target = int(txt)
        tu = uget(target)
        if not tu:
            await update.message.reply_text(F("User not found."), reply_markup=admin_kb()); clear_state(ctx, uid); return True
        mode = data.get("mode","warn")
        if mode == "warn":
            uupdate(target, warnings=int(tu["warnings"]) + 1)
            await update.message.reply_text(F("Warned."), reply_markup=admin_kb())
            try: await ctx.bot.send_message(target, F("You received a warning.")); 
            except Exception: pass
        elif mode == "ban":
            uupdate(target, banned=1)
            await update.message.reply_text(F("Banned."), reply_markup=admin_kb())
            try: await ctx.bot.send_message(target, F("You are banned. Support only.")); 
            except Exception: pass
        elif mode == "unban":
            uupdate(target, banned=0)
            await update.message.reply_text(F("Unbanned."), reply_markup=admin_kb())
            try: await ctx.bot.send_message(target, F("You are unbanned.")); 
            except Exception: pass
        clear_state(ctx, uid)
        return True

    if st == "SEND_ALL":
        msg = update.message.text
        with db() as c:
            ids = [int(r["user_id"]) for r in c.execute("SELECT user_id FROM users").fetchall()]
        sent = 0; fail = 0
        for tid in ids:
            try:
                await ctx.bot.send_message(tid, msg)
                sent += 1
            except Exception:
                fail += 1
        await update.message.reply_text(F(f"Broadcast done. Sent {sent}, failed {fail}."), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "SEND_UID":
        if not txt.isdigit():
            await update.message.reply_text(F("Send valid user ID."), reply_markup=back_kb()); return True
        data["target"] = int(txt)
        set_state(ctx, uid, "SEND_TEXT", data)
        await update.message.reply_text(F("Send message text."), reply_markup=back_kb())
        return True

    if st == "SEND_TEXT":
        target = int(data["target"])
        msg = update.message.text
        ok = True
        try:
            await ctx.bot.send_message(target, msg)
        except Exception:
            ok = False
        await update.message.reply_text(F("Sent ✅" if ok else "Failed ❌"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "MULTI_IDS":
        ids_raw = update.message.text
        ids = []
        for part in re.split(r"[,\s]+", ids_raw.strip()):
            if part.isdigit():
                ids.append(int(part))
        if not ids:
            await update.message.reply_text(F("No valid IDs."), reply_markup=back_kb()); return True
        data["ids"] = ids
        set_state(ctx, uid, "MULTI_TEXT", data)
        await update.message.reply_text(F("Send message text."), reply_markup=back_kb())
        return True

    if st == "MULTI_TEXT":
        ids = data.get("ids", [])
        msg = update.message.text
        sent_ids = []
        fail_ids = []
        for tid in ids:
            try:
                await ctx.bot.send_message(tid, msg)
                sent_ids.append(tid)
            except Exception:
                fail_ids.append(tid)
        rep = F("Multi send done.") + f"\n{F('Sent')}: {len(sent_ids)}\n{F('Failed')}: {len(fail_ids)}"
        await update.message.reply_text(rep, reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "PM_NAME":
        data["name"] = txt
        set_state(ctx, uid, "PM_DETAILS", data)
        await update.message.reply_text(F("Send method details (number/account)."), reply_markup=back_kb())
        return True

    if st == "PM_DETAILS":
        name = data["name"]
        details = update.message.text
        with db() as c:
            c.execute("INSERT INTO payment_methods(name,details) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET details=excluded.details", (name, details))
        await update.message.reply_text(F(f"Payment method saved: {name}"), reply_markup=admin_kb())
        clear_state(ctx, uid)
        return True

    if st == "REF_BONUS":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return True
        sset("ref_bonus", txt)
        await update.message.reply_text(F("Referral bonus updated."), reply_markup=admin_kb())
        clear_state(ctx, uid); return True

    if st == "REF_MIN":
        if not txt.isdigit():
            await update.message.reply_text(F("Send number only."), reply_markup=back_kb()); return True
        sset("ref_min_purchase", txt)
        await update.message.reply_text(F("Referral min purchase updated."), reply_markup=admin_kb())
        clear_state(ctx, uid); return True

    return False

# -------------------- MAIN TEXT ROUTER --------------------

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user(update.effective_user)
    cleanup_history()
    uid = update.effective_user.id
    u = uget(uid)
    if u and int(u["banned"]) == 1 and not is_admin(uid):
        if update.message.text == "🆘 Support":
            await support_start(update, ctx); return
        if update.message.text == "ℹ️ Dev & Info":
            await show_dev_info(update, ctx); return
        await update.message.reply_text(F("You are banned. Use Support."), reply_markup=banned_kb(uid))
        return
    if sget("maintenance","OFF") == "ON" and not is_admin(uid):
        if update.message.text == "🆘 Support":
            await support_start(update, ctx); return
        await update.message.reply_text(F("Maintenance ON. Use Support."), reply_markup=banned_kb(uid))
        return

    # state-driven handlers first
    # admin flows
    if await handle_admin_flows(update, ctx):
        return

    # redeem admin flow
    st, _ = get_state(ctx, uid)
    if is_admin(uid) and st.startswith("RDM_"):
        await handle_redeem_admin_flow(update, ctx); return
    if st == "RDM_CLAIM":
        await handle_redeem_claim_flow(update, ctx); return
    if st.startswith("BONUS_"):
        await handle_bonus_flow(update, ctx); return
    if st.startswith("GIFT_"):
        await handle_gift_flow(update, ctx); return
    if st == "SUPPORT_MSG":
        await handle_support_msg(update, ctx); return
    if st.startswith("AMT_"):
        # add money flow stages
        if st == "AMT_WAIT_AMOUNT": await handle_amount(update, ctx); return
        if st == "AMT_PICK_METHOD": await handle_method_pick(update, ctx); return
        if st == "AMT_WAIT_TXID": await handle_txid(update, ctx); return
    if st == "DM_WAIT_UID":
        await start_diamond_confirm(update, ctx, update.message.text); return

    # button routing
    t = update.message.text

    if t == "✅ Verify":
        await handle_verify(update, ctx); return
    if t == "⬅ Back":
        clear_state(ctx, uid)
        await update.message.reply_text(F("Back to menu."), reply_markup=home_kb(uid))
        return

    # user buttons
    if t == "🎫 Unipin":
        await show_unipin_list(update, ctx); return
    if t.startswith("🎫 "):
        await start_unipin_confirm(update, ctx, t); return
    if t == "✅ Confirm Buy":
        await do_unipin_buy(update, ctx); return

    if t == "💎 Diamond":
        await show_diamond_list(update, ctx); return
    if t.startswith("💎 "):
        await start_diamond_uid(update, ctx, t); return
    if t == "✅ Confirm Order":
        await do_diamond_place(update, ctx); return

    if t == "➕ Add Money":
        await start_add_money(update, ctx); return
    if t == "➡ Next":
        await handle_next(update, ctx); return

    if t == "🎁 Gift Coin":
        await gift_coin_menu(update, ctx); return
    if t == "✅ Check Bonus":
        await check_bonus(update, ctx); return
    if t == "🎁 Gift Balance":
        await gift_balance_start(update, ctx); return

    if t == "🎟 Redeem Code":
        await redeem_claim(update, ctx); return

    if t == "📜 History":
        await history_menu(update, ctx); return
    if t == "📦 Code History":
        await show_history(update, ctx, "code"); return
    if t == "💳 Payment History":
        await show_history(update, ctx, "payment"); return

    if t == "👥 Refer & Earn":
        await show_refer(update, ctx); return

    if t == "👤 My Account":
        await show_my_account(update, ctx); return

    if t == "🆘 Support":
        await support_start(update, ctx); return

    if t == "ℹ️ Dev & Info":
        await show_dev_info(update, ctx); return

    # admin panel
    if t == "🛠 Admin Panel":
        await open_admin_panel(update, ctx); return

    if is_admin(uid):
        if t == "🔔 Notifications":
            await toggle_notifications(update, ctx); return
        if t == "📸 SS Must ON/OFF":
            await toggle_ss_must(update, ctx); return
        if t == "🛠 Bot ON/OFF":
            await toggle_maintenance(update, ctx); return
        if t == "🎁 Bonus Settings":
            await bonus_settings(update, ctx); return
        if t == "🎁 Bonus ON/OFF":
            await bonus_on_off(update, ctx); return
        if t == "🎁 All User Bonus Set":
            await bonus_all_set_start(update, ctx); return
        if t == "🎁 Custom User Bonus":
            await bonus_custom_start(update, ctx); return
        if t == "🎟 Redeem Manage":
            await redeem_manage_start(update, ctx); return
        if t == "👥 Referral Settings":
            await referral_settings_menu(update, ctx); return
        if t == "🔁 Referral ON/OFF":
            await referral_toggle(update, ctx); return
        if t == "💰 Set Ref Bonus":
            await set_ref_bonus_start(update, ctx); return
        if t == "📉 Set Ref Min":
            await set_ref_min_start(update, ctx); return
        if t == "📦 Stock":
            await show_stock(update, ctx); return
        if t == "💳 Payment Methods":
            await payment_methods_menu(update, ctx); return
        if t == "➕ Set Method":
            await set_method_start(update, ctx); return
        if t == "➕ Add UC List":
            await add_list_start(update, ctx, "UC"); return
        if t == "➕ Add DM List":
            await add_list_start(update, ctx, "DM"); return
        if t == "✅ Done":
            await add_list_done(update, ctx); return
        if t == "➕ Add Code":
            await add_code_start(update, ctx); return
        if t == "➕ Add DM Qty":
            await add_dm_qty_start(update, ctx); return
        if t == "🧹 Code Remove":
            await code_remove_start(update, ctx); return
        if t == "📤 Code Return":
            await code_return_start(update, ctx); return
        if t == "🗑 Delete Product":
            await delete_product_start(update, ctx); return
        if t == "💰 Add Balance":
            await add_balance_start(update, ctx, cut=False); return
        if t == "➖ Cut Balance":
            await add_balance_start(update, ctx, cut=True); return
        if t == "⚠ Warn User":
            await warn_ban_start(update, ctx, "warn"); return
        if t == "⛔ Ban User":
            await warn_ban_start(update, ctx, "ban"); return
        if t == "♻ Unban User":
            await warn_ban_start(update, ctx, "unban"); return
        if t == "📋 Get All User ID":
            await get_all_user_ids(update, ctx); return
        if t == "📣 Send All Msg":
            await send_all_start(update, ctx); return
        if t == "👤 Send User Msg":
            await send_user_start(update, ctx); return
        if t == "📨 Multi ID Msg":
            await multi_id_start(update, ctx); return

    # default
    await update.message.reply_text(F("Use menu buttons."), reply_markup=home_kb(uid))

async def on_nontext(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # handle photo for add money if waiting
    if update.message and update.message.photo:
        await handle_photo(update, ctx)

def main() -> None:
    init_db()
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text(F("Use menu. Admin: /start"))))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_nontext))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    if RUN_HEALTH:
        threading.Thread(target=start_health_server, daemon=True).start()
    import asyncio
    main()
