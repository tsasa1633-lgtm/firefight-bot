import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

# --- CONFIG ---
TOKEN = os.getenv("API_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# Названия карт для бана
ALL_MAPS = ["🏙 City", "🌲 Forest", "🏜 Desert", "🏭 Factory", "❄️ Snow"]

# БД в памяти
queues = {"flexxy": [], "editor": []}
matches = {}      
elo_ratings = {}  
user_last_msg = {} 
veto_sessions = {}

# --- FACEIT LOGIC ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    if elo < 800: return "1️⃣"
    if elo < 1100: return "3️⃣"
    if elo < 1400: return "5️⃣"
    if elo < 2000: return "9️⃣"
    return "🔟"

async def ui_update(uid, text, kb, photo=PHOTO_MAIN):
    """Надежное обновление интерфейса"""
    if uid in user_last_msg:
        try:
            await bot.delete_message(uid, user_last_msg[uid])
        except TelegramBadRequest:
            pass # Если сообщение слишком старое или уже удалено
    
    try:
        msg = await bot.send_photo(uid, photo=photo, caption=text, reply_markup=kb, parse_mode="Markdown")
        user_last_msg[uid] = msg.message_id
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# --- KEYBOARDS ---
def kb_start():
    return InlineKeyboardBuilder().row(InlineKeyboardButton(text="🕹 ИГРАТЬ (FACEIT)", callback_data="main_menu")).as_markup()

def kb_mods():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔥 FLEXXY ХАБ", callback_data="hub_flexxy"))
    builder.row(InlineKeyboardButton(text="🛠 EDITOR ХАБ", callback_data="hub_editor"))
    return builder.as_markup()

def kb_game(mode):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 НАЙТИ МАТЧ", callback_data=f"search_{mode}"))
    builder.row(InlineKeyboardButton(text="🏆 Я ПОБЕДИЛ", callback_data="win"))
    builder.row(InlineKeyboardButton(text="🏳️ СДАТЬСЯ", callback_data="loss"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="main_menu"))
    builder.adjust(1)
    return builder.as_markup()

def kb_veto(match_id, maps):
    builder = InlineKeyboardBuilder()
    for m in maps:
        builder.row(InlineKeyboardButton(text=f"❌ Бан {m}", callback_data=f"v_{match_id}_{m}"))
    builder.adjust(1)
    return builder.as_markup()

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    elo = get_elo(uid)
    text = f"⚔️ **FACEIT SYSTEM**\n\n👤 LVL: {get_lvl(elo)}\n📊 ELO: `{elo}`"
    await ui_update(uid, text, kb_start())
    try: await message.delete()
    except: pass

@dp.callback_query(F.data == "main_menu")
async def call_main(call: types.CallbackQuery):
    await ui_update(call.from_user.id, "🕹 **ВЫБЕРИ ХАБ:**", kb_mods())
    await call.answer()

@dp.callback_query(F.data.startswith("hub_"))
async def call_hub(call: types.CallbackQuery):
    mode = call.data.split("_")[1]
    elo = get_elo(call.from_user.id)
    text = f"✅ **ХАБ: {mode.upper()}**\n\nТвой рейтинг: `{elo}` {get_lvl(elo)}"
    await ui_update(call.from_user.id, text, kb_game(mode), PHOTO_CHOICE)
    await call.answer()

@dp.callback_query(F.data.startswith("search_"))
async def call_search(call: types.CallbackQuery):
    uid, mode = call.from_user.id, call.data.split("_")[1]
    
    if uid in matches or any(uid in q for q in queues.values()):
        return await call.answer("Ты уже в системе!", show_alert=True)

    queues[mode].append(uid)
    await call.answer("Поиск начат...")

    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        match_id = f"{p1}_{p2}"
        matches[p1], matches[p2] = p2, p1
        veto_sessions[match_id] = {"maps": ALL_MAPS.copy(), "turn": p1, "p1": p1, "p2": p2}
        
        await bot.send_message(p1, "🎮 **Матч найден!** Твой ход банить карту.", reply_markup=kb_veto(match_id, ALL_MAPS))
        await bot.send_message(p2, "🎮 **Матч найден!** Ожидай хода противника.")

@dp.callback_query(F.data.startswith("v_"))
async def call_veto(call: types.CallbackQuery):
    _, mid, mname = call.data.split("_")
    uid = call.from_user.id
    s = veto_sessions.get(mid)

    if not s or uid != s["turn"]:
        return await call.answer("Не твой ход!", show_alert=True)

    s["maps"].remove(mname)
    next_p = s["p2"] if uid == s["p1"] else s["p1"]
    s["turn"] = next_p

    if len(s["maps"]) > 1:
        await bot.send_message(next_p, f"🚫 Бан: {mname}. Твой черед!", reply_markup=kb_veto(mid, s["maps"]))
        await call.message.edit_text(f"✅ Ты забанил {mname}. Ждем противника...")
    else:
        final = s["maps"][0]
        res = f"🏁 **ВЕТО ЗАВЕРШЕНО!**\n🗺 Карта: **{final}**\n\nХост: {get_lvl(get_elo(s['p1']))} P1"
        await bot.send_message(s["p1"], res)
        await bot.send_message(s["p2"], res.replace("P1", "P2"))
        del veto_sessions[mid]
    await call.answer()

# --- РЕЗУЛЬТАТЫ ---
async def finish(win_id, loss_id):
    elo_ratings[win_id] = get_elo(win_id) + 25
    elo_ratings[loss_id] = max(0, get_elo(loss_id) - 25)
    matches.pop(win_id, None); matches.pop(loss_id, None)
    await bot.send_message(win_id, f"🏆 WIN! ELO: `{get_elo(win_id)}`")
    await bot.send_message(loss_id, f"💀 LOSS! ELO: `{get_elo(loss_id)}`")

@dp.callback_query(F.data == "win")
async def call_win(call: types.CallbackQuery):
    if call.from_user.id not in matches: return
    opp = matches[call.from_user.id]
    kb = InlineKeyboardBuilder().row(InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"c_{call.from_user.id}")).as_markup()
    await bot.send_message(opp, "⚠️ Оппонент жмет WIN. Подтверждаешь?", reply_markup=kb)
    await call.answer("Запрос отправлен.")

@dp.callback_query(F.data.startswith("c_"))
async def call_confirm(call: types.CallbackQuery):
    win_id = int(call.data.split("_")[1])
    if call.from_user.id in matches:
        await finish(win_id, call.from_user.id)
        await call.message.delete()

@dp.callback_query(F.data == "loss")
async def call_loss(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid in matches: await finish(matches[uid], uid)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
