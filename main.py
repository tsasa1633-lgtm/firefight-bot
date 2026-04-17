import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto

# --- CONFIG ---
TOKEN = os.getenv("API_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# DB IN MEMORY
queues = {"flexxy": [], "editor": []}
matches = {}      
elo_ratings = {}  
user_last_msg = {} # Для чистки чата

# --- FACEIT LOGIC ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    levels = [
        (2000, "🔟"), (1850, "9️⃣"), (1700, "8️⃣"), (1550, "7️⃣"),
        (1400, "6️⃣"), (1250, "5️⃣"), (1100, "4️⃣"), (950, "3️⃣"),
        (800, "2️⃣"), (0, "1️⃣")
    ]
    for threshold, icon in levels:
        if elo >= threshold: return icon

async def refresh_ui(uid, text, kb, photo=PHOTO_MAIN):
    """Обновляет интерфейс, удаляя старое сообщение"""
    if uid in user_last_msg:
        try: await bot.delete_message(uid, user_last_msg[uid])
        except: pass
    
    msg = await bot.send_photo(uid, photo=photo, caption=text, reply_markup=kb, parse_mode="Markdown")
    user_last_msg[uid] = msg.message_id

# --- KEYBOARDS ---
def kb_start():
    return InlineKeyboardBuilder().row(InlineKeyboardButton(text="🕹 PLAY (FACEIT)", callback_data="mods")).as_markup()

def kb_mods():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔥 FLEXXY HUB", callback_data="mode_flexxy"))
    builder.row(InlineKeyboardButton(text="🛠 EDITOR HUB", callback_data="mode_editor"))
    return builder.as_markup()

def kb_match(mode, uid):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 FIND MATCH", callback_data=f"match_{mode}"))
    builder.row(InlineKeyboardButton(text="🏆 REPORT WIN", callback_data="report_win"))
    builder.row(InlineKeyboardButton(text="🏳️ SURRENDER", callback_data="report_loss"))
    builder.row(InlineKeyboardButton(text="🔙 BACK", callback_data="mods"))
    builder.adjust(1)
    return builder.as_markup()

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    elo = get_elo(uid)
    text = f"⚔️ **WELCOME TO FACEIT**\n\n👤 LVL: {get_lvl(elo)}\n📊 ELO: `{elo}`\n\nReady for matchmaking?"
    await refresh_ui(uid, text, kb_start())
    try: await message.delete()
    except: pass

@dp.callback_query(F.data == "mods")
async def call_mods(call: types.CallbackQuery):
    await refresh_ui(call.from_user.id, "🕹 **SELECT HUB**\n\nChoose your battleground:", kb_mods())

@dp.callback_query(F.data.startswith("mode_"))
async def call_select(call: types.CallbackQuery):
    mode = call.data.split("_")[1]
    uid = call.from_user.id
    text = f"✅ **HUB: {mode.upper()}**\n\nLVL: {get_lvl(get_elo(uid))} | ELO: `{get_elo(uid)}`"
    await refresh_ui(uid, text, kb_match(mode, uid), PHOTO_CHOICE)

@dp.callback_query(F.data.startswith("match_"))
async def call_match(call: types.CallbackQuery):
    uid = call.from_user.id
    mode = call.data.split("_")[1]
    
    if uid in matches or any(uid in q for q in queues.values()):
        return await call.answer("Already in system!", show_alert=True)

    queues[mode].append(uid)
    await call.answer("Searching...")

    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        for p, opp in [(p1, p2), (p2, p1)]:
            side = "HOST" if p == p1 else "GUEST"
            card = (f"🎮 **MATCH FOUND**\n\n"
                    f"🔴 {get_lvl(get_elo(p1))} P1: {get_elo(p1)}\n"
                    f"🔵 {get_lvl(get_elo(p2))} P2: {get_elo(p2)}\n\n"
                    f"You are: **{side}**")
            await bot.send_message(p, card)

# Система результатов (ELO Diff)
async def finalize(w_id, l_id):
    diff = (get_elo(l_id) - get_elo(w_id)) * 0.1
    gain = round(25 + diff)
    points = max(10, min(50, gain))
    
    elo_ratings[w_id] = get_elo(w_id) + points
    elo_ratings[l_id] = max(0, get_elo(l_id) - points)
    
    matches.pop(w_id, None); matches.pop(l_id, None)
    
    await bot.send_message(w_id, f"📈 **WIN** (+{points} ELO)\nNew: `{get_elo(w_id)}` {get_lvl(get_elo(w_id))}")
    await bot.send_message(l_id, f"📉 **LOSS** (-{points} ELO)\nNew: `{get_elo(l_id)}` {get_lvl(get_elo(l_id))}")

@dp.callback_query(F.data == "report_win")
async def report_win(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid not in matches: return
    
    opp = matches[uid]
    kb = InlineKeyboardBuilder().row(InlineKeyboardButton(text="✅ CONFIRM LOSS", callback_data=f"confirm_{uid}")).as_markup()
    await bot.send_message(opp, "❗ Opponent reported victory. Confirm?", reply_markup=kb)
    await call.answer("Waiting for confirmation...")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_res(call: types.CallbackQuery):
    w_id = int(call.data.split("_")[1])
    l_id = call.from_user.id
    if l_id in matches and matches[l_id] == w_id:
        await finalize(w_id, l_id)
        await call.message.delete()

@dp.callback_query(F.data == "report_loss")
async def report_loss(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid in matches: await finalize(matches[uid], uid)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
