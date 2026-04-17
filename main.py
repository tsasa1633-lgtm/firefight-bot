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

# Ссылки на фото
PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# База данных в памяти
queues = {"flexxy": [], "editor": []}
matches = {} 

# --- КНОПКА СТАРТА (Единственная в начале) ---
def get_welcome_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🚀 Начать", callback_data="go_to_mods"))
    return kb.as_markup()

# --- КЛАВИАТУРА 1: Выбор модов ---
def get_mods_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 firefight FLEXXY", callback_data="select_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠️ war editor", callback_data="select_editor"))
    return kb.as_markup()

# --- КЛАВИАТУРА 2: Поиск и управление ---
def get_search_kb(mode):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти противника", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить матч", callback_data="end_match"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="go_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

# ПРИВЕТСТВИЕ
@dp.message(Command("start"))
async def start(message: types.Message):
    # Убираем старые нижние кнопки, если они остались
    await message.answer("Загрузка интерфейса...", reply_markup=ReplyKeyboardRemove())
    
    await message.answer_photo(
        photo=PHOTO_MAIN,
        caption="🪖 **RANKED FIREFIGHT SYSTEM**\n\nДобро пожаловать! Нажми кнопку ниже, чтобы войти в систему.",
        reply_markup=get_welcome_kb(),
        parse_mode="Markdown"
    )

# ПЕРЕХОД К МОДАМ
@dp.callback_query(F.data == "go_to_mods")
async def show_mods(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="🕹 **ВЫБОР РЕЖИМА**\n\nВыбери мод, в котором хочешь сразиться:",
        reply_markup=get_mods_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ВЫБОР КОНКРЕТНОГО МОДА (ВТОРОЙ СЛАЙД)
@dp.callback_query(F.data.startswith("select_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=PHOTO_CHOICE,
            caption=f"✅ **ОТЛИЧНЫЙ ВЫБОР!**\nРежим: `{mode.upper()}`\n\nТеперь нажимай поиск и жди оппонента.",
            parse_mode="Markdown"
        ),
        reply_markup=get_search_kb(mode)
    )
    await callback.answer()

# ПОИСК
@dp.callback_query(F.data.startswith("join_"))
async def join_queue(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    
    if uid in matches:
        await callback.answer("🚨 Ты уже в матче!", show_alert=True)
        return
    if uid in queues["flexxy"] or uid in queues["editor"]:
        await callback.answer("⏳ Поиск уже идет...", show_alert=True)
        return

    queues[mode].append(uid)
    await callback.message.answer(f"🚀 Поиск в {mode.upper()} начат! Людей: {len(queues[mode])}")
    
    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        await bot.send_message(p1, "🔥 **Матч найден! Ты ХОСТ.**\nПиши код комнаты.")
        await bot.send_message(p2, "🔥 **Матч найден!**\nЖди код от хоста.")
    await callback.answer()

# ЗАВЕРШЕНИЕ И ВЫХОД
@dp.callback_query(F.data == "leave")
async def leave(callback: types.CallbackQuery):
    uid = callback.from_user.id
    for q in queues.values():
        if uid in q: q.remove(uid)
    await callback.answer("❌ Очередь покинута.", show_alert=True)

@dp.callback_query(F.data == "end_match")
async def end(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid in matches:
        opp = matches.pop(uid)
        matches.pop(opp, None)
        await callback.message.answer("🏁 Матч завершен.")
        await bot.send_message(opp, "🏁 Противник завершил матч.")
    else:
        await callback.answer("Нет активного боя.", show_alert=True)

# ЧАТ
@dp.message(lambda m: m.from_user.id in matches)
async def chat(message: types.Message):
    if message.text and not message.text.startswith('/'):
        await bot.send_message(matches[message.from_user.id], f"💬 **Сообщение:**\n{message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
