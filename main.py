import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# База данных
queues = {"flexxy": [], "editor": []}
matches = {}      # {id: opp_id}
elo_ratings = {}  # {id: points}
user_messages = {} # {id: last_message_id} для удаления

# --- ФУНКЦИИ FACEIT ---

def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    if elo <= 800: return "1️⃣"
    if elo <= 950: return "2️⃣"
    if elo <= 1100: return "3️⃣"
    if elo <= 1250: return "4️⃣"
    if elo <= 1400: return "5️⃣"
    if elo <= 1550: return "6️⃣"
    if elo <= 1700: return "7️⃣"
    if elo <= 1850: return "8️⃣"
    if elo <= 2000: return "9️⃣"
    return "🔟"

async def delete_old_msg(uid):
    """Удаляет предыдущее сообщение бота, чтобы не было мусора"""
    if uid in user_messages:
        try:
            await bot.delete_message(uid, user_messages[uid])
        except:
            pass

# --- КЛАВИАТУРЫ ---

def get_welcome_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🕹 ИГРАТЬ (FACEIT)", callback_data="go_to_mods"))
    return kb.as_markup()

def get_mods_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 FLEXXY (Ranked)", callback_data="select_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠 War Editor", callback_data="select_editor"))
    return kb.as_markup()

def get_search_kb(mode, uid):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти матч", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="❌ Покинуть очередь", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏆 Я ВЫИГРАЛ", callback_data="win_request"))
    kb.row(InlineKeyboardButton(text="🏳️ Отмена", callback_data="end_match"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="go_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

# --- ЛОГИКА ---

@dp.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    await delete_old_msg(uid) # Очистка
    
    elo = get_elo(uid)
    msg = await message.answer_photo(
        photo=PHOTO_MAIN,
        caption=f"⚔️ **FACEIT FIREFIGHT**\n\n👤 Твой уровень: {get_lvl(elo)}\n📊 Твой ELO: `{elo}`\n\nГотов к калибровке?",
        reply_markup=get_welcome_kb(),
        parse_mode="Markdown"
    )
    user_messages[uid] = msg.message_id
    try: await message.delete() # Удаляем команду /start от пользователя
    except: pass

@dp.callback_query(F.data == "go_to_mods")
async def show_mods(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="🕹 **ВЫБОР ХАБА**\n\nВыбери режим для поиска матча:",
        reply_markup=get_mods_kb()
    )

@dp.callback_query(F.data.startswith("select_"))
async def select_mode(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    elo = get_elo(uid)
    
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=PHOTO_CHOICE,
            caption=f"✅ **ХАБ ВЫБРАН: {mode.upper()}**\n\nТвой LVL: {get_lvl(elo)} | ELO: `{elo}`\n\nНажми кнопку поиска, чтобы система подобрала оппонента."
        ),
        reply_markup=get_search_kb(mode, uid)
    )

@dp.callback_query(F.data.startswith("join_"))
async def join_queue(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    
    if uid in matches:
        await callback.answer("🚨 Ты уже в игре!", show_alert=True)
        return
    if any(uid in q for q in queues.values()):
        await callback.answer("⏳ Поиск уже запущен.", show_alert=True)
        return

    queues[mode].append(uid)
    await callback.answer("🚀 Поиск начат!")
    
    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        # Уведомления о найденном матче
        await bot.send_message(p1, f"🎮 **МАТЧ НАЙДЕН!**\n\nПротивник: `{get_lvl(get_elo(p2))}` (ELO: {get_elo(p2)})\n🌕 ТЫ — **HOST**\n\nСоздавай лобби и пиши код сюда.")
        await bot.send_message(p2, f"🎮 **МАТЧ НАЙДЕН!**\n\nПротивник: `{get_lvl(get_elo(p1))}` (ELO: {get_elo(p1)})\n🌑 ТЫ — **GUEST**\n\nЖди код от хоста.")

# Система подтверждения (как в прошлом коде, но с LVL)
@dp.callback_query(F.data == "win_request")
async def win_request(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in matches:
        await callback.answer("Матч не найден", show_alert=True)
        return

    opp_id = matches[uid]
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Подтверждаю поражение", callback_data=f"conf_win_{uid}"))
    kb.row(InlineKeyboardButton(text="❌ Оспорить (ADMIN)", callback_data=f"dispute_{uid}"))
    
    await bot.send_message(opp_id, "⚠️ Оппонент прислал результат: **ПОБЕДА**. Подтверждаешь?", reply_markup=kb.as_markup())
    await callback.answer("Ожидаем подтверждения...")

@dp.callback_query(F.data.startswith("conf_win_"))
async def confirm_win(callback: types.CallbackQuery):
    winner_id = int(callback.data.split("_")[2])
    loser_id = callback.from_user.id
    
    if loser_id not in matches: return

    elo_ratings[winner_id] = get_elo(winner_id) + 25
    elo_ratings[loser_id] = max(0, get_elo(loser_id) - 25)

    matches.pop(winner_id, None)
    matches.pop(loser_id, None)

    await bot.send_message(winner_id, f"🏆 **WIN!**\nТвой ELO: `{get_elo(winner_id)}` (+25)\nLVL: {get_lvl(get_elo(winner_id))}")
    await callback.message.edit_text(f"💀 **LOSS!**\nТвой ELO: `{get_elo(loser_id)}` (-25)\nLVL: {get_lvl(get_elo(loser_id))}")

# Чат пересылка
@dp.message(lambda m: m.from_user.id in matches)
async def chat(message: types.Message):
    if message.text and not message.text.startswith('/'):
        try:
            await bot.send_message(matches[message.from_user.id], f"💬 **Сообщение:** {message.text}")
        except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
