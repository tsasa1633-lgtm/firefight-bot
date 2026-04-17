import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove

TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Фото
PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# База данных в памяти
queues = {"flexxy": [], "editor": []}
matches = {} 
elo_ratings = {} # {user_id: rating_points}

# Функция получения рейтинга
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

# --- КЛАВИАТУРЫ ---
def get_welcome_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🚀 Начать", callback_data="go_to_mods"))
    return kb.as_markup()

def get_mods_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 firefight FLEXXY", callback_data="select_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠️ war editor", callback_data="select_editor"))
    return kb.as_markup()

def get_search_kb(mode, uid):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти противника", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏆 Сообщить о ПОБЕДЕ", callback_data="win_match"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить (Ничья/Отмена)", callback_data="end_match"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="go_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Синхронизация рейтинга...", reply_markup=ReplyKeyboardRemove())
    await message.answer_photo(
        photo=PHOTO_MAIN,
        caption=f"🪖 **RANKED FIREFIGHT SYSTEM**\n\nТвой текущий рейтинг: `{get_elo(message.from_user.id)}` ELO\n\nНажми кнопку ниже, чтобы войти.",
        reply_markup=get_welcome_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "go_to_mods")
async def show_mods(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="🕹 **ВЫБОР РЕЖИМА**\n\nВыбери мод для игры:",
        reply_markup=get_mods_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("select_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=PHOTO_CHOICE,
            caption=f"✅ **ОТЛИЧНЫЙ ВЫБОР!**\n\n👤 Твой рейтинг: `{get_elo(uid)}` ELO\n🔹 Режим: `{mode.upper()}`\n\nИщи противника и побеждай!",
            parse_mode="Markdown"
        ),
        reply_markup=get_search_kb(mode, uid)
    )

# ЛОГИКА ПОБЕДЫ (ЭЛО СИСТЕМА)
@dp.callback_query(F.data == "win_match")
async def win_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in matches:
        await callback.answer("Ты не в активном матче!", show_alert=True)
        return

    opp_id = matches.pop(uid)
    matches.pop(opp_id, None)

    # Начисляем очки
    elo_ratings[uid] = get_elo(uid) + 25
    elo_ratings[opp_id] = max(0, get_elo(opp_id) - 25) # Чтобы рейтинг не падал ниже 0

    await callback.message.answer(f"🏆 **Победа засчитана!**\nТвой новый рейтинг: `{get_elo(uid)}` (+25)")
    await bot.send_message(opp_id, f"💀 **Поражение!**\nТвой новый рейтинг: `{get_elo(opp_id)}` (-25)")
    await callback.answer()

# Остальная логика поиска и чата
@dp.callback_query(F.data.startswith("join_"))
async def join_q(callback: types.CallbackQuery):
    uid, mode = callback.from_user.id, callback.data.split("_")[1]
    if uid in matches or uid in queues["flexxy"] or uid in queues["editor"]:
        await callback.answer("Уже в системе!", show_alert=True)
        return
    queues[mode].append(uid)
    await callback.message.answer(f"🚀 Поиск начат! Рейтинг: {get_elo(uid)}")
    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        await bot.send_message(p1, "🔥 Матч найден! Ты ХОСТ.")
        await bot.send_message(p2, "🔥 Матч найден! Жди код.")
    await callback.answer()

@dp.callback_query(F.data == "end_match")
async def end(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid in matches:
        opp = matches.pop(uid)
        matches.pop(opp, None)
        await callback.message.answer("🏁 Матч завершен без изменения рейтинга.")
        await bot.send_message(opp, "🏁 Матч завершен/отменен.")
    await callback.answer()

@dp.message(lambda m: m.from_user.id in matches)
async def chat(message: types.Message):
    if message.text and not message.text.startswith('/'):
        await bot.send_message(matches[message.from_user.id], f"💬 **Противник:** {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
