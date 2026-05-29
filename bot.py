import os
import re
import logging
from datetime import datetime
import aiosqlite
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from database import init_db, is_allowed, add_user, del_user, list_users, add_trade, add_ledger, get_saldo
from ai_analyzer import analyze_trade_image

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "trading.db"

def usd_til_dkk():
    try:
        r = requests.get("https://api.exchangerate.host/latest?base=USD&symbols=DKK", timeout=3)
        return r.json()["rates"]["DKK"]
    except:
        return 7.0

async def check_access(update: Update):
    uid = update.effective_user.id
    if not await is_allowed(uid):
        await update.message.reply_text("Adgang nægtet. Kontakt admin.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    await update.message.reply_text("Hej! Send et screenshot, eller skriv 'brugt 80$' / 'tjent 100$'")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"/tmp/{photo.file_id}.png"
    await file.download_to_drive(path)

    await update.message.reply_text("Analyserer...")
    analysis = analyze_trade_image(path)

    context.user_data['draft'] = analysis

    txt = f"Jeg ser: {analysis['instrument']} – {analysis['size']}C – {analysis['direction'].upper()}\nEntry {analysis['entry']} | TP {analysis['tp']} | SL {analysis['sl']}"
    kb = [
        [InlineKeyboardButton("✅ Gem", callback_data="save")],
        [InlineKeyboardButton("✏️ Skift instrument", callback_data="change_inst"),
         InlineKeyboardButton("✏️ Skift størrelse", callback_data="change_size")]
    ]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    draft = context.user_data.get('draft', {})

    if data == "save":
        await add_trade(q.from_user.id, draft)
        await q.edit_message_text("Trade gemt!")

    elif data == "change_inst":
        kb = [[InlineKeyboardButton(i, callback_data=f"inst_{i}") for i in ["MGC","GC","ES","NQ","EURUSD"]]]
        await q.edit_message_text("Vælg instrument:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("inst_"):
        draft['instrument'] = data.split("_")[1]
        context.user_data['draft'] = draft
        await q.edit_message_text(f"Instrument: {draft['instrument']}. Tryk ✅ Gem.")

    elif data == "change_size":
        kb = [[InlineKeyboardButton(s, callback_data=f"size_{s}") for s in ["1","2","3","5","10"]]]
        await q.edit_message_text("Vælg størrelse:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("size_"):
        draft['size'] = float(data.split("_")[1])
        context.user_data['draft'] = draft
        await q.edit_message_text(f"Størrelse: {draft['size']}C. Tryk ✅ Gem.")

    elif data == "adm_add":
        context.user_data['awaiting'] = 'add_user'
        await q.edit_message_text("Send Telegram ID på ny bruger:")
    elif data == "adm_del":
        context.user_data['awaiting'] = 'del_user'
        await q.edit_message_text("Send Telegram ID der skal fjernes:")
    elif data == "adm_list":
        users = await list_users()
        txt = "\n".join([f"{u[0]} - {u[1]}" for u in users])
        await q.edit_message_text(f"Brugere:\n{txt}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return

    if context.user_data.get('awaiting') == 'add_user':
        try:
            new_id = int(update.message.text.strip())
            await add_user(new_id, "")
            await update.message.reply_text(f"Bruger {new_id} tilføjet")
        except: await update.message.reply_text("Ugyldigt ID")
        context.user_data.pop('awaiting')
        return
    if context.user_data.get('awaiting') == 'del_user':
        try:
            await del_user(int(update.message.text.strip()))
            await update.message.reply_text("Bruger fjernet")
        except: pass
        context.user_data.pop('awaiting')
        return

    txt = update.message.text.lower()
    m = re.search(r'(\d+\.?\d*)', txt)
    if not m: return
    usd = float(m.group(1))
    kurs = usd_til_dkk()
    dkk = round(usd * kurs)

    if any(w in txt for w in ['brugt','købt','betalt','challenge','køb']):
        await add_ledger(update.effective_user.id, 'out', usd, dkk, txt)
        saldo_usd, saldo_dkk = await get_saldo(update.effective_user.id)
        await update.message.reply_text(f"✅ -{usd}$ (-{dkk} kr) noteret\nSaldo: {saldo_usd}$ ({int(saldo_dkk)} kr)")
    elif any(w in txt for w in ['tjent','payout','modtaget','fået','indtjening']):
        await add_ledger(update.effective_user.id, 'in', usd, dkk, txt)
        saldo_usd, saldo_dkk = await get_saldo(update.effective_user.id)
        await update.message.reply_text(f"✅ +{usd}$ (+{dkk} kr) noteret\nSaldo: {saldo_usd}$ ({int(saldo_dkk)} kr)")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    usd, dkk = await get_saldo(update.effective_user.id)
    await update.message.reply_text(f"Netto: {usd}$ ({int(dkk)} kr)")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    kb = [
        [InlineKeyboardButton("➕ Tilføj bruger", callback_data="adm_add"),
         InlineKeyboardButton("➖ Fjern bruger", callback_data="adm_del")],
        [InlineKeyboardButton("📋 Se brugere", callback_data="adm_list")]
    ]
    await update.message.reply_text("Admin:", reply_markup=InlineKeyboardMarkup(kb))

async def post_init(app):
    await init_db()

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()