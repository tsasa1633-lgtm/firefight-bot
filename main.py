import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("API_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Твои фото
PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# БД в памяти
queues = {"flexxy": [], "editor": []}
matches = {}      
elo_ratings = {}  
user_last_msg = {} 

# --- СИСТЕМА FACEIT (LVL & ELO) ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    if elo < 800: return "1️⃣"
    if elo < 950: return "2️⃣"
    if elo < 1100: return "3️⃣"
    if elo < 1250: return "4️⃣"
    if elo < 1400: return "5️⃣"
    if elo < 1550: return "6️⃣"
    if elo < 1700: return "7️⃣"
    if elo < 1850: return "8️⃣"
    if elo < 2000: return "9️⃣"
    return "🔟"

async def ui_update(uid, text, kb, photo=PHOTO_MAIN):
    """Обновляет интерфейс, чтобы не было спама"""
    if uid in user_last_msg:
        try: await bot.delete_message(uid, user_last_msg[uid])
        except: pass
    msg = await bot.send_photo(uid, photo=photo, caption=text, reply_markup=kb, parse_mode="Markdown")
    user_last_msg[uid] = msg.message_id

# --- КНОПКИ ---
def kb_start():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🕹 ИГРАТЬ (FACEIT)", callback_data="show_mods"))
    return builder.as_markup()

def kb_mods():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔥 FLEXXY ХАБ", callback_data="setmode_flexxy"))
    builder.row(InlineKeyboardButton(text="🛠 EDITOR ХАБ", callback_data="setmode_editor"))
    return builder.as_markup()

def kb_game(mode, uid):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 НАЙТИ МАТЧ", callback_data=f"find_{mode}"))
    builder.row(InlineKeyboardButton(text="🏆 Я ПОБЕДИЛ", callback_data="report_win"))
    builder.row(InlineKeyboardButton(text="🏳️ Я ПРОИГРАЛ (Сдаться)", callback_data="report_loss"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="show_mods"))
    builder.adjust(1)
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    elo = get_elo(uid)
    text = f"⚔️ **ДОБРО ПОЖАЛОВАТЬ НА FACEIT**\n\n👤 Твой LVL: {get_lvl(elo)}\n📊 Твой ELO: `{elo}`\n\nГотов начать поиск?"
    await ui_update(uid, text, kb_start())
    try: await message.delete()
    except: pass

@dp.callback_query(F.data == "show_mods")
async def mods_menu(call: types.CallbackQuery):
    await ui_update(call.from_user.id, "🕹 **ВЫБЕРИ ХАБ ДЛЯ ИГРЫ:**", kb_mods())

@dp.callback_query(F.data.startswith("setmode_"))
async def select_hub(call: types.CallbackQuery):
    mode = call.data.split("_")[1]
    uid = call.from_user.id
    elo = get_elo(uid)
    text = f"✅ **ВЫБРАН ХАБ: {mode.upper()}**\n\nТвой LVL: {get_lvl(elo)} | ELO: `{elo}`\n\nНажимай поиск, когда будешь готов."
    await ui_update(uid, text, kb_game(mode, uid), PHOTO_CHOICE)

@dp.callback_query(F.data.startswith("find_"))
async def find_match(call: types.CallbackQuery):
    uid = call.from_user.id
    mode = call.data.split("_")[1]
    
    if uid in matches or any(uid in q for q in queues.values()):
        return await call.answer("Ты уже в поиске или в игре!", show_alert=True)

    queues[mode].append(uid)
    await call.answer("🔍 Поиск начат...", show_alert=False)

    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        for p, opp in [(p1, p2), (p2, p1)]:
            role = "ХОСТ (Создавай лобби)" if p == p1 else "ГОСТЬ (Жди код)"
            card = (f"🎮 **МАТЧ НАЙДЕН!**\n\n"
                    f"🔴 P1: {get_lvl(get_elo(p1))} (ELO: {get_elo(p1)})\n"
                    f"🔵 P2: {get_lvl(get_elo(p2))} (ELO: {get_elo(p2)})\n\n"
                    f"Твоя роль: **{role}**")
            await bot.send_message(p, card)

# Финал матча
async def apply_result(win_id, loss_id):
    # Расчет ELO (Faceit Style)
    gain = 25 + round((get_elo(loss_id) - get_elo(win_id)) * 0.1)
    points = max(10, min(50, gain))
    
    elo_ratings[win_id] = get_elo(win_id) + points
    elo_ratings[loss_id] = max(0, get_elo(loss_id) - points)
    
    matches.pop(win_id, None); matches.pop(loss_id, None)
    
    await bot.send_message(win_id, f"🏆 **ПОБЕДА!**\n+{points} ELO. Новый рейтинг: `{get_elo(win_id)}` {get_lvl(get_elo(win_id))}")
    await bot.send_message(loss_id, f"💀 **ПОРАЖЕНИЕ!**\n-{points} ELO. Новый рейтинг: `{get_elo(loss_id)}` {get_lvl(get_elo(loss_id))}")

@dp.callback_query(F.data == "report_win")
async def report_win(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid not in matches: return await call.answer("Ты не в матче!")
    
    opp = matches[uid]
    kb = InlineKeyboardBuilder().row(InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ ПОРАЖЕНИЕ", callback_data=f"confirm_{uid}")).as_markup()
    await bot.send_message(opp, "❗ Твой противник заявил о своей победе. Подтверждаешь?", reply_markup=kb)
    await call.answer("Запрос отправлен оппоненту.")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_res(call: types.CallbackQuery):
    winner_id = int(call.data.split("_")[1])
    loser_id = call.from_user.id
    if loser_id in matches and matches[loser_id] == winner_id:
        await apply_result(winner_id, loser_id)
        await call.message.delete()

@dp.callback_query(F.data == "report_loss")
async def report_loss(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid in matches: await apply_result(matches[uid], uid)
    else: await call.answer("Матч не найден.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
