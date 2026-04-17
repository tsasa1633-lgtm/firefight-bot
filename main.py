import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# Настройки Railway
TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Твоя ссылка на фото
PHOTO_URL = "https://i.yapx.ru/dZgZW.jpg"

# Очереди и матчи
queues = {"flexxy": [], "editor": []}
matches = {} # {id_игрока: id_противника}

# --- МЕНЮ (Инлайн под фото) ---
def get_main_menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 firefight FLEXXY", callback_data="join_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠️ war editor", callback_data="join_editor"))
    kb.row(InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить матч", callback_data="end_match"))
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    caption = (
        "🪖 **RANKED FIREFIGHT SYSTEM**\n\n"
        "Выбирай режим и начинай поиск. После нахождения матча бот назначит хоста.\n\n"
        "💬 **Чат с противником** работает прямо здесь."
    )
    await message.answer_photo(
        photo=PHOTO_URL,
        caption=caption,
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

# --- ЛОГИКА ПОИСКА ---
@dp.callback_query(F.data.startswith("join_"))
async def join_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    
    if uid in matches:
        await callback.answer("⚠️ Ты уже в матче!", show_alert=True)
        return
    
    # Проверка, нет ли игрока уже в какой-либо очереди
    if uid in queues["flexxy"] or uid in queues["editor"]:
        await callback.answer("⏳ Ты уже ищешь игру.", show_alert=True)
        return

    queues[mode].append(uid)
    await callback.message.answer(f"✅ Поиск в режиме {mode.upper()} начат. В очереди: {len(queues[mode])}")
    await callback.answer()

    if len(queues[mode]) >= 2:
        p1 = queues[mode].pop(0)
        p2 = queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        await bot.send_message(p1, "🔥 **Матч найден! Ты — ХОСТ.**\nНапиши код лобби и правила сюда, я перешлю их.", parse_mode="Markdown")
        await bot.send_message(p2, "🔥 **Матч найден!**\nТвой противник — хост. Жди код здесь.", parse_mode="Markdown")

# --- ЧАТ И ПЕРЕСЫЛКА ---
@dp.message(lambda msg: msg.from_user.id in matches)
async def chat_handler(message: types.Message):
    if message.text and not message.text.startswith('/'):
        opp_id = matches[message.from_user.id]
        await bot.send_message(opp_id, f"💬 **Сообщение от противника:**\n{message.text}", parse_mode="Markdown")
        await message.answer("✅ Сообщение доставлено.")

# --- ВЫХОД И ЗАВЕРШЕНИЕ ---
@dp.callback_query(F.data == "leave")
async def leave_q(callback: types.CallbackQuery):
    uid = callback.from_user.id
    removed = False
    for q in queues.values():
        if uid in q:
            q.remove(uid)
            removed = True
    
    msg = "❌ Ты покинул очередь." if removed else "Ты не был в очереди."
    await callback.answer(msg, show_alert=True)

@dp.callback_query(F.data == "end_match")
async def end_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid in matches:
        opp_id = matches.pop(uid)
        matches.pop(opp_id, None)
        await callback.message.answer("🏁 Матч завершен.")
        await bot.send_message(opp_id, "🏁 Противник завершил матч.")
    else:
        await callback.answer("У тебя нет активного матча.", show_alert=True)
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
