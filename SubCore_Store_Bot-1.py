import os, sqlite3, logging
from datetime import datetime, timezone
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "6454961191").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "subcore_store.db")
CURRENCY = os.getenv("CURRENCY", "USD")
PAYMENT = """💳 <b>SUBCORE PAYMENT METHODS</b>

💰 <b>Binance UID:</b> <code>1286477278</code>

✅ <b>USDT BEP20:</b>
<code>0x38A9503d42350239C55819C1f40728C2e0781ef8</code>

🪙 <b>USDT TRC20:</b>
<code>TXSgyu6sSi55WVpiRH2LVT2wokyMgFZWz6</code>

⚠️ Select the correct network. Wrong-network transfers may be lost.
After payment, submit your TxID or screenshot. Admin verifies deposits manually."""
PRODUCTS = [
("claude_max_5x","🟠","Claude Max 5×",85,"1 month","Confirm with shop","Manual activation","Premium Claude Max 5× usage tier. Monthly subscription. Exact availability and activation method are confirmed by SubCore."),
("claude_max_20x","🟠","Claude Max 20×",125,"1 month","Confirm with shop","Manual activation","Premium Claude Max 20× usage tier, priority access during high traffic and advanced features where available. Monthly subscription."),
("higgsfield_pro_12m","🎬","Higgsfield Pro 12M",92,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official coupon code • 4,500 credits/month • On your account • New accounts that have never had Premium only. Redeem within 7 days. Use a desktop browser at higgsfield.ai/s/lenny, complete onboarding, then Manage Account → Promocode → Claim. Payment method required."),
("cursor_pro_12m","⚫","Cursor Pro 12M",88,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official coupon/redeem link • On your account. Redeem within 7 days. Log into the intended Cursor account, open the link only from that account, click Get Started and complete checkout. Do not open the link just to inspect it; it may become invalid."),
("runway_pro_12m","🎥","Runway Pro 12M",55,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official coupon code • 2,250 credits/month • On your account. Redeem within 7 days. Sign up at app.runwayml.com, complete onboarding, choose Pro yearly billing, select Add Promotion Code and enter code. Payment method required."),
("railway_hobby_12m","🚆","Railway Hobby 12M",18,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official offer • New accounts only • Use within 7 days. Create account at Railway, then Profile → Workspace Settings → Plans, select the eligible offer and upgrade to Hobby. Billing details required. Seller describes $20 monthly credits for 12 months; provider eligibility applies."),
("factory_pro_12m","🏭","Factory Pro 12M",60,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official voucher • Create account at app.factory.ai, complete onboarding, visit app.factory.ai/voucher, enter voucher code and click Redeem Voucher."),
("supabase_pro_12m","🟩","Supabase Pro 12M",65,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official offer • Redeem within 7 days. Sign up at supabase.com, open offer page, choose/create an organization and redeem. Seller describes $450 one-time credits, approximately a year of Pro usage; credits do not renew and usage may exhaust them sooner."),
("notion_business_12m","📝","Notion Business 12M",30,"12 months","Full warranty; seller terms apply","Automatic after payment confirmation if stock is available","Official offer • Plus features, Notion Agent and more subject to provider terms. Open offer link, Apply Now, sign in/create account, complete onboarding, select workspace and finish checkout. Seller describes a one-year offer."),
("linkedin_business_12m","🔵","LinkedIn Business Premium 12M",58,"12 months","Full warranty after activation; seller terms apply","Manual; typically within 12 hours","Business insights, profile-view insights, advanced search, 15 monthly InMail credits, LinkedIn Learning and profile features where included. Requires account access and approval in LinkedIn app. Do not change password during activation. Manual service, not instant code."),
("linkedin_career_12m","🔵","LinkedIn Career Premium 12M",40,"12 months","Full warranty after activation; seller terms apply","Manual; typically within 12 hours","Career insights, profile-view insights, advanced job search, applicant tools, monthly InMail credits and LinkedIn Learning where included. Requires account access and approval in LinkedIn app. Do not change password during activation. Manual service."),
("grok_heavy","𝕏","Grok Heavy",95,"1 month","Confirm with shop","Confirm delivery with shop","Monthly plan as described by seller: AI teammates, high usage/speed, advanced problem solving, early feature access and X Premium+ benefits where included. Provider terms apply."),
("chatgpt_pro_20x","🤖","ChatGPT Pro 20×",75,"1 month","Confirm with shop","Confirm delivery with shop","Monthly offer as described by seller: higher usage, advanced models, multi-step work agent, coding agent and experimental features where available. Exact features/limits depend on provider plan terms."),
]
def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def admin(uid): return uid in ADMIN_IDS
def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,username TEXT,balance REAL DEFAULT 0,created_at TEXT);
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,emoji TEXT,name TEXT,price REAL,duration TEXT,warranty TEXT,delivery TEXT,details TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id TEXT,payload TEXT,used INTEGER DEFAULT 0,used_by INTEGER,used_at TEXT);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,proof TEXT,status TEXT DEFAULT 'pending',created_at TEXT);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,product_id TEXT,amount REAL,status TEXT,delivery TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS stock_display(product_id TEXT PRIMARY KEY, quantity INTEGER NOT NULL DEFAULT 0);
        """)
        for p in PRODUCTS:
            c.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET emoji=excluded.emoji,name=excluded.name,price=excluded.price,duration=excluded.duration,warranty=excluded.warranty,delivery=excluded.delivery,details=excluded.details",p)
        c.execute("INSERT OR IGNORE INTO settings VALUES('support','Contact @SubCore_store for support.')")
MENU=ReplyKeyboardMarkup([[KeyboardButton("🛍️ All Products"),KeyboardButton("👛 Wallet")],[KeyboardButton("➕ Deposit"),KeyboardButton("📦 My Orders")],[KeyboardButton("💳 Payment Methods"),KeyboardButton("🆘 Support")]],resize_keyboard=True)
def products():
    with db() as c: return c.execute("SELECT * FROM products WHERE active=1 ORDER BY rowid").fetchall()
def count(pid):
    with db() as c: return c.execute("SELECT COUNT(*) FROM stock WHERE product_id=? AND used=0",(pid,)).fetchone()[0]
def display_count(pid):
    """Return the stock quantity set by the admin for display."""
    with db() as c:
        row = c.execute("SELECT quantity FROM stock_display WHERE product_id=?", (pid,)).fetchone()
    return row["quantity"] if row else 0
def product_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f'{p["emoji"]} {p["name"]} — ${p["price"]:.2f} | 📦 Stock: {display_count(p["id"])}',callback_data="p:"+p["id"])] for p in products()])
async def start(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=u.effective_user
    with db() as c: c.execute("INSERT INTO users(user_id,username,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",(user.id,user.username or "",now()))
    await u.effective_message.reply_text("🟢 <b>SUBCORE STORE</b>\nPremium Digital Products\n\nBrowse products, wallet, deposits and orders below.",parse_mode=ParseMode.HTML,reply_markup=MENU)
async def show_products(u,ctx):
    await u.effective_message.reply_text("🟢 <b>ALL PRODUCTS</b>\nChoose a product to view details:",parse_mode=ParseMode.HTML,reply_markup=product_buttons())
async def wallet(u,ctx):
    with db() as c: r=c.execute("SELECT balance FROM users WHERE user_id=?",(u.effective_user.id,)).fetchone()
    await u.effective_message.reply_text(f'👛 Wallet balance: <b>${(r["balance"] if r else 0):.2f}</b>',parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Deposit",callback_data="deposit")]]))
async def deposit_start(u,ctx):
    ctx.user_data["dep_amount"]=True
    await u.effective_message.reply_text(PAYMENT+"\n\nEnter deposit amount in USD/USDT (numbers only).",parse_mode=ParseMode.HTML)
async def callback(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=u.callback_query; d=q.data
    if d=="products": await q.answer(); await q.edit_message_text("🟢 <b>ALL PRODUCTS</b>",parse_mode=ParseMode.HTML,reply_markup=product_buttons()); return
    if d.startswith("p:"):
        pid=d[2:]
        with db() as c: p=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if not p: await q.answer("Product not found",show_alert=True); return
        n=count(pid); shown=display_count(pid)
        stock=f"📦 Stock: {shown} accounts"
        msg=f'{p["emoji"]} <b>{escape(p["name"])}</b>\n━━━━━━━━━━━━\n💰 Price: <b>${p["price"]:.2f} {CURRENCY}</b>\n📅 Duration: {escape(p["duration"])}\n🛡 Warranty: Full Warranty\n🚚 Delivery: {escape(p["delivery"])}\n{stock}\n\n📌 <b>Details</b>\n{escape(p["details"])}'
        await q.answer()
        await q.edit_message_text(msg,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Buy Now",callback_data="buy:"+pid)],[InlineKeyboardButton("⬅️ All Products",callback_data="products")]]),disable_web_page_preview=True)
    elif d=="deposit":
        await q.answer(); ctx.user_data["dep_amount"]=True; await q.message.reply_text(PAYMENT+"\n\nEnter deposit amount in USD/USDT.",parse_mode=ParseMode.HTML)
    elif d.startswith("buy:"):
        pid=d[4:]; uid=q.from_user.id
        with db() as c:
            p=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
            usr=c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()
            item=c.execute("SELECT * FROM stock WHERE product_id=? AND used=0 ORDER BY id LIMIT 1",(pid,)).fetchone()
            if not p: await q.answer("Product not found",show_alert=True); return
            if usr is None or usr["balance"]<p["price"]:
                await q.answer("Insufficient wallet balance. Deposit first.",show_alert=True); return
            automatic="automatic" in p["delivery"].lower()
            if automatic and not item:
                await q.answer("No preloaded stock; contact support.",show_alert=True); return
            cur=c.execute("INSERT INTO orders(user_id,product_id,amount,status,created_at) VALUES(?,?,?,?,?)",(uid,pid,p["price"],"processing",now())); oid=cur.lastrowid
            c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(p["price"],uid))
            payload=None
            if item:
                payload=item["payload"]; c.execute("UPDATE stock SET used=1,used_by=?,used_at=? WHERE id=?",(uid,now(),item["id"]))
                c.execute("UPDATE orders SET status='delivered',delivery=? WHERE id=?",(payload,oid))
            else: c.execute("UPDATE orders SET status='pending_manual' WHERE id=?",(oid,))
        await q.answer("Order created")
        if payload:
            await ctx.bot.send_message(uid,f"✅ <b>Order #{oid} delivered</b>\n{escape(p['name'])}\n\n<code>{escape(payload)}</code>",parse_mode=ParseMode.HTML)
        else:
            await ctx.bot.send_message(uid,f"✅ Order #{oid} received. Manual activation is pending; SubCore will contact you.")
            for aid in ADMIN_IDS:
                await ctx.bot.send_message(aid,f"📦 Manual order #{oid}\nUser: {uid}\nProduct: {p['name']}\nUse /complete_order {oid} DELIVERY_NOTE")
    elif d.startswith("approve:") or d.startswith("reject:"):
        if not admin(q.from_user.id): await q.answer("Admins only",show_alert=True); return
        did=int(d.split(":")[1]); ok=d.startswith("approve:")
        with db() as c:
            dep=c.execute("SELECT * FROM deposits WHERE id=?",(did,)).fetchone()
            if not dep or dep["status"]!="pending": await q.answer("Already reviewed",show_alert=True); return
            c.execute("UPDATE deposits SET status=? WHERE id=?",("approved" if ok else "rejected",did))
            if ok: c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(dep["amount"],dep["user_id"]))
        await q.answer("Approved" if ok else "Rejected"); await q.edit_message_reply_markup(reply_markup=None)
        await ctx.bot.send_message(dep["user_id"],f'{"✅ Deposit approved" if ok else "❌ Deposit rejected"}: ${dep["amount"]:.2f}'+(" Wallet credited." if ok else " Contact support if needed."))
async def messages(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
    m=u.effective_message; user=u.effective_user; t=(m.text or "").strip()
    with db() as c: c.execute("INSERT INTO users(user_id,username,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",(user.id,user.username or "",now()))
    if t=="🛍️ All Products": await show_products(u,ctx); return
    if t=="👛 Wallet":
        await wallet(u,ctx); return
    if t=="➕ Deposit": await deposit_start(u,ctx); return
    if t=="💳 Payment Methods": await m.reply_text(PAYMENT,parse_mode=ParseMode.HTML); return
    if t=="🆘 Support":
        with db() as c: s=c.execute("SELECT value FROM settings WHERE key='support'").fetchone()
        await m.reply_text(s["value"] if s else "Contact @SubCore_store"); return
    if t=="📦 My Orders":
        with db() as c: rows=c.execute("SELECT o.*,p.name FROM orders o JOIN products p ON p.id=o.product_id WHERE user_id=? ORDER BY o.id DESC LIMIT 10",(user.id,)).fetchall()
        await m.reply_text("\n".join([f'#{r["id"]} {r["name"]} — ${r["amount"]:.2f} — {r["status"]}' for r in rows]) or "No orders yet."); return
    if ctx.user_data.get("dep_amount"):
        try: amt=float(t.replace("$","").replace(",","")); assert 0<amt<=100000
        except Exception: await m.reply_text("Enter a valid amount, e.g. 25"); return
        ctx.user_data["dep_amount"]=False; ctx.user_data["dep_proof"]=amt
        await m.reply_text("Now send payment TxID/reference as text or send a screenshot/photo."); return
    if "dep_proof" in ctx.user_data and (t or m.photo):
        amt=ctx.user_data.pop("dep_proof"); proof=t or "Screenshot attached"
        with db() as c: cur=c.execute("INSERT INTO deposits(user_id,amount,proof,created_at) VALUES(?,?,?,?)",(user.id,amt,proof,now())); did=cur.lastrowid
        await m.reply_text(f"Deposit request #{did} submitted. Wallet credits after admin verification.")
        for aid in ADMIN_IDS:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f"approve:{did}"),InlineKeyboardButton("❌ Reject",callback_data=f"reject:{did}")]])
            cap=f"Deposit #{did}\nUser: {user.id}\nAmount: ${amt:.2f}\nProof: {escape(proof)}"
            if m.photo: await ctx.bot.send_photo(aid,m.photo[-1].file_id,caption=cap,reply_markup=kb)
            else: await ctx.bot.send_message(aid,cap,reply_markup=kb)
        return
    await m.reply_text("Choose an option from the menu.",reply_markup=MENU)
async def admin_cmd(u,ctx):
    if not admin(u.effective_user.id): return
    await u.message.reply_text("Admin commands:\n/products_admin\n/setprice PRODUCT_ID PRICE\n/setstock PRODUCT_ID NUMBER\n/addstock PRODUCT_ID | CODE_OR_TEXT\n/setdetails PRODUCT_ID | DURATION | WARRANTY | DELIVERY | DETAILS\n/deposits\n/orders_admin\n/complete_order ORDER_ID DELIVERY_NOTE\n/set_support CONTACT_TEXT")
async def products_admin(u,ctx):
    if not admin(u.effective_user.id): return
    await u.message.reply_text("\n".join(f'{p["id"]} — ${p["price"]:.2f} — 📦 Stock: {display_count(p["id"])} accounts' for p in products()))
async def setprice(u,ctx):
    if not admin(u.effective_user.id): return
    try: pid,price=ctx.args[0],float(ctx.args[1]); assert price>=0
    except Exception: await u.message.reply_text("Usage: /setprice PRODUCT_ID PRICE"); return
    with db() as c: cur=c.execute("UPDATE products SET price=? WHERE id=?",(price,pid))
    await u.message.reply_text("Price updated." if cur.rowcount else "Product ID not found.")
async def setstock(u, ctx):
    if not admin(u.effective_user.id):
        return
    try:
        pid = ctx.args[0].strip()
        qty = int(ctx.args[1])
        if qty < 0:
            raise ValueError
    except (IndexError, ValueError):
        await u.message.reply_text("Usage: /setstock PRODUCT_ID NUMBER\nExample: /setstock claude_max_5x 10")
        return
    with db() as c:
        exists = c.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone()
        if not exists:
            await u.message.reply_text("Product ID not found. Use /products_admin to see exact IDs.")
            return
        c.execute("INSERT INTO stock_display(product_id, quantity) VALUES(?, ?) ON CONFLICT(product_id) DO UPDATE SET quantity=excluded.quantity", (pid, qty))
    await u.message.reply_text(f"📦 Stock updated: {pid} = {qty} accounts")
async def addstock(u,ctx):
    if not admin(u.effective_user.id): return
    parts=u.message.text.partition(" ")[2].split("|",1)
    if len(parts)!=2: await u.message.reply_text("Usage: /addstock PRODUCT_ID | CODE_OR_TEXT"); return
    pid,payload=parts[0].strip(),parts[1].strip()
    with db() as c:
        if not c.execute("SELECT 1 FROM products WHERE id=?",(pid,)).fetchone(): await u.message.reply_text("Unknown product ID. Use /products_admin."); return
        c.execute("INSERT INTO stock(product_id,payload) VALUES(?,?)",(pid,payload))
    await u.message.reply_text(f"Stock added. Remaining: {count(pid)}")
async def stock_cmd(u,ctx):
    if not admin(u.effective_user.id) or len(ctx.args)!=1: return
    await u.message.reply_text(f'{ctx.args[0]} stock: {count(ctx.args[0])}')
async def setdetails(u,ctx):
    if not admin(u.effective_user.id): return
    parts=u.message.text.partition(" ")[2].split("|",4)
    if len(parts)!=5: await u.message.reply_text("Usage: /setdetails PRODUCT_ID | DURATION | WARRANTY | DELIVERY | DETAILS"); return
    pid,dur,war,delivery,details=[x.strip() for x in parts]
    with db() as c: cur=c.execute("UPDATE products SET duration=?,warranty=?,delivery=?,details=? WHERE id=?",(dur,war,delivery,details,pid))
    await u.message.reply_text("Details updated." if cur.rowcount else "Product ID not found.")
async def deposits_cmd(u,ctx):
    if not admin(u.effective_user.id): return
    with db() as c: rows=c.execute("SELECT * FROM deposits WHERE status='pending'").fetchall()
    if not rows: await u.message.reply_text("No pending deposits."); return
    for r in rows:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f'approve:{r["id"]}'),InlineKeyboardButton("❌ Reject",callback_data=f'reject:{r["id"]}')]])
        await u.message.reply_text(f'Deposit #{r["id"]}\nUser {r["user_id"]}\n${r["amount"]:.2f}\n{r["proof"]}',reply_markup=kb)
async def orders_admin(u,ctx):
    if not admin(u.effective_user.id): return
    with db() as c: rows=c.execute("SELECT o.*,p.name FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 20").fetchall()
    await u.message.reply_text("\n".join(f'#{r["id"]} user={r["user_id"]} {r["name"]} ${r["amount"]:.2f} {r["status"]}' for r in rows) or "No orders.")
async def complete_order(u,ctx):
    if not admin(u.effective_user.id): return
    try: oid=int(ctx.args[0]); note=" ".join(ctx.args[1:]); assert note
    except Exception: await u.message.reply_text("Usage: /complete_order ORDER_ID DELIVERY_NOTE"); return
    with db() as c:
        r=c.execute("SELECT user_id FROM orders WHERE id=?",(oid,)).fetchone()
        if not r: await u.message.reply_text("Order not found."); return
        c.execute("UPDATE orders SET status='completed',delivery=? WHERE id=?",(note,oid))
    await ctx.bot.send_message(r["user_id"],f"✅ Order #{oid} completed\n{note}"); await u.message.reply_text("Order completed.")
async def set_support(u,ctx):
    if not admin(u.effective_user.id): return
    val=u.message.text.partition(" ")[2].strip()
    if not val: await u.message.reply_text("Usage: /set_support CONTACT_TEXT"); return
    with db() as c: c.execute("INSERT INTO settings VALUES('support',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(val,))
    await u.message.reply_text("Support contact updated.")
def main():
    if not BOT_TOKEN: raise SystemExit("Missing BOT_TOKEN environment variable")
    init_db(); app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("admin",admin_cmd))
    app.add_handler(CommandHandler("products_admin",products_admin)); app.add_handler(CommandHandler("setprice",setprice))
    app.add_handler(CommandHandler("addstock",addstock)); app.add_handler(CommandHandler("stock",stock_cmd)); app.add_handler(CommandHandler("setstock",setstock))
    app.add_handler(CommandHandler("setdetails",setdetails)); app.add_handler(CommandHandler("deposits",deposits_cmd))
    app.add_handler(CommandHandler("orders_admin",orders_admin)); app.add_handler(CommandHandler("complete_order",complete_order))
    app.add_handler(CommandHandler("set_support",set_support)); app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, messages))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=="__main__": main()
