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

# Ссылки на фото
PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# База данных в памяти
queues = {"flexxy": [], "editor": []}
matches = {}      # {id_игрока: id_противника}
elo_ratings = {}  # {user_id: rating}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

# --- КЛАВИАТУРЫ ---

# 1. Начальная кнопка
def get_welcome_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🚀 Начать", callback_data="go_to_mods"))
    return kb.as_markup()

# 2. Выбор модов
def get_mods_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 firefight FLEXXY", callback_data="select_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠️ war editor", callback_data="select_editor"))
    return kb.as_markup()

# 3. Игровое меню
def get_search_kb(mode, uid):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти противника", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏆 Сообщить о ПОБЕДЕ", callback_data="win_request"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить (Ничья/Отмена)", callback_data="end_match"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="go_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

# --- ОБРАБОТЧИКИ КОМАНД ---

@dp.message(Command("start"))
async def start(message: types.Message):
    # Удаляем старые Reply-кнопки
    await message.answer("Вход в систему...", reply_markup=ReplyKeyboardRemove())
    
    await message.answer_photo(
        photo=PHOTO_MAIN,
        caption=f"🪖 **RANKED FIREFIGHT SYSTEM**\n\nТвой рейтинг: `{get_elo(message.from_user.id)}` ELO\n\nНажми кнопку ниже, чтобы начать.",
        reply_markup=get_welcome_kb(),
        parse_mode="Markdown"
    )

# Переход к выбору мода
@dp.callback_query(F.data == "go_to_mods")
async def show_mods(callback: types.CallbackQuery):
    await callback.message.edit_media(
        media=InputMediaPhoto(media=PHOTO_MAIN, caption="🕹 **ВЫБОР РЕЖИМА**\n\nВыбери мод для игры:"),
        reply_markup=get_mods_kb()
    )

# Выбор конкретного мода (второй слайд)
@dp.callback_query(F.data.startswith("select_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=PHOTO_CHOICE,
            caption=f"✅ **ОТЛИЧНЫЙ ВЫБОР!**\n\n👤 Рейтинг: `{get_elo(uid)}` ELO\n🔹 Режим: `{mode.upper()}`\n\nИщи противника и побеждай!"
        ),
        reply_markup=get_search_kb(mode, uid)
    )

# --- ЛОГИКА МАТЧМЕЙКИНГА ---

@dp.callback_query(F.data.startswith("join_"))
async def join_queue(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    
    if uid in matches:
        await callback.answer("🚨 Ты уже в матче!", show_alert=True)
        return
    if any(uid in q for q in queues.values()):
        await callback.answer("⏳ Ты уже ищешь игру.", show_alert=True)
        return

    queues[mode].append(uid)
    await callback.message.answer(f"🚀 Поиск в {mode.upper()} начат! (Ваш ELO: {get_elo(uid)})")
    
    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        await bot.send_message(p1, "🔥 **Матч найден! Ты — ХОСТ.**\nПиши код лобби сюда.")
        await bot.send_message(p2, "🔥 **Матч найден!**\nТвой противник — хост. Жди код здесь.")
    await callback.answer()

# --- СИСТЕМА ПОДТВЕРЖДЕНИЯ ПОБЕДЫ ---

@dp.callback_query(F.data == "win_request")
async def win_request(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in matches:
        await callback.answer("Нет активного матча!", show_alert=True)
        return

    opp_id = matches[uid]
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Да, я проиграл", callback_data=f"conf_win_{uid}"))
    kb.row(InlineKeyboardButton(text="❌ Спор (Вызов Админа)", callback_data=f"dispute_{uid}"))
    
    await bot.send_message(opp_id, "⚠️ Противник заявил о своей победе. Подтверждаешь?", reply_markup=kb.as_markup())
    await callback.message.answer("⏳ Ждем подтверждения от противника...")
    await callback.answer()

@dp.callback_query(F.data.startswith("conf_win_"))
async def confirm_win(callback: types.CallbackQuery):
    winner_id = int(callback.data.split("_")[2])
    loser_id = callback.from_user.id
    
    if loser_id not in matches or matches[loser_id] != winner_id:
        await callback.answer("Ошибка: матч уже завершен.")
        return

    # Начисляем ELO
    elo_ratings[winner_id] = get_elo(winner_id) + 25
    elo_ratings[loser_id] = max(0, get_elo(loser_id) - 25)

    matches.pop(winner_id, None)
    matches.pop(loser_id, None)

    await bot.send_message(winner_id, f"🏆 Победа подтверждена! Рейтинг: `{get_elo(winner_id)}` (+25)")
    await callback.message.edit_text(f"💀 Поражение принято. Рейтинг: `{get_elo(loser_id)}` (-25)")

@dp.callback_query(F.data.startswith("dispute_"))
async def dispute_handler(callback: types.CallbackQuery):
    winner_id = int(callback.data.split("_")[1])
    loser_id = callback.from_user.id
    await bot.send_message(ADMIN_ID, f"⚖️ **СПОР!**\nМатч: {winner_id} vs {loser_id}")
    await callback.message.edit_text("🛰 Админ уведомлен о споре.")
    await bot.send_message(winner_id, "⚠️ Противник оспорил результат. Ждите админа.")

# --- ПРОЧЕЕ ---

@dp.callback_query(F.data == "leave")
async def leave_queue(callback: types.CallbackQuery):
    uid = callback.from_user.id
    for q in queues.values():
        if uid in q: q.remove(uid)
    await callback.answer("❌ Ты покинул поиск.", show_alert=True)

@dp.callback_query(F.data == "end_match")
async def end_match(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid in matches:
        opp = matches.pop(uid)
        matches.pop(opp, None)
        await callback.message.answer("🏁 Матч отменен.")
        await bot.send_message(opp, "🏁 Противник отменил матч.")
    else:
        await callback.answer("Нет активного матча.", show_alert=True)

@dp.message(lambda m: m.from_user.id in matches)
async def chat(message: types.Message):
    if message.text and not message.text.startswith('/'):
        await bot.send_message(matches[message.from_user.id], f"💬 **Противник:** {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
