import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Ссылки на фото
PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# Очереди и матчи
queues = {"flexxy": [], "editor": []}
matches = {} 

# --- КЛАВИАТУРА 1: Только моды ---
def get_mods_keyboard():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 firefight FLEXXY", callback_data="select_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠️ war editor", callback_data="select_editor"))
    kb.adjust(1)
    return kb.as_markup()

# --- КЛАВИАТУРА 2: Поиск и управление ---
def get_search_keyboard(mode):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти противника", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить матч", callback_data="end_match"))
    kb.row(InlineKeyboardButton(text="🔙 Назад к модам", callback_data="back_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer_photo(
        photo=PHOTO_MAIN,
        caption="🪖 **RANKED FIREFIGHT SYSTEM**\n\nВыбери режим игры для начала:",
        reply_markup=get_mods_keyboard(),
        parse_mode="Markdown"
    )

# Обработка выбора мода (Переход ко 2-му слайду)
@dp.callback_query(F.data.startswith("select_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    
    # Редактируем сообщение: меняем фото, текст и кнопки
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=PHOTO_CHOICE,
            caption=f"✅ **ОТЛИЧНЫЙ ВЫБОР!**\nРежим: `{mode.upper()}`\n\nТеперь нажимай кнопку ниже и ищи своего противника!",
            parse_mode="Markdown"
        ),
        reply_markup=get_search_keyboard(mode)
    )
    await callback.answer()

# Возврат назад
@dp.callback_query(F.data == "back_to_mods")
async def back_to_mods(callback: types.CallbackQuery):
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=PHOTO_MAIN,
            caption="🪖 **RANKED FIREFIGHT SYSTEM**\n\nВыбери режим игры для начала:",
            parse_mode="Markdown"
        ),
        reply_markup=get_mods_keyboard()
    )
    await callback.answer()

# Логика поиска (когда нажали "Найти противника")
@dp.callback_query(F.data.startswith("join_"))
async def join_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    
    if uid in matches:
        await callback.answer("⚠️ Ты уже в матче!", show_alert=True)
        return
    if uid in queues["flexxy"] or uid in queues["editor"]:
        await callback.answer("⏳ Ты уже ищешь игру.", show_alert=True)
        return

    queues[mode].append(uid)
    await callback.message.answer(f"🚀 Поиск начат! Игроков в очереди: {len(queues[mode])}")
    
    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        await bot.send_message(p1, "🔥 **Матч найден! Ты — ХОСТ.**\nПиши код лобби сюда.")
        await bot.send_message(p2, "🔥 **Матч найден!**\nЖди код от хоста.")
    await callback.answer()

# Остальные обработчики (чат, выход, завершение) оставляем как были...
@dp.message(lambda msg: msg.from_user.id in matches)
async def chat_handler(message: types.Message):
    if message.text and not message.text.startswith('/'):
        opp_id = matches[message.from_user.id]
        await bot.send_message(opp_id, f"💬 **Сообщение:**\n{message.text}")

@dp.callback_query(F.data == "leave")
async def leave_q(callback: types.CallbackQuery):
    uid = callback.from_user.id
    for q in queues.values():
        if uid in q: q.remove(uid)
    await callback.answer("❌ Ты покинул очередь.", show_alert=True)

@dp.callback_query(F.data == "end_match")
async def end_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid in matches:
        opp_id = matches.pop(uid)
        matches.pop(opp_id, None)
        await callback.message.answer("🏁 Матч завершен.")
        await bot.send_message(opp_id, "🏁 Противник завершил матч.")
    else:
        await callback.answer("Нет активного матча.", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
