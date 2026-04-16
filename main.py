import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Переменные из Railway
TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Очередь и активные матчи
queue = []
matches = {} # Тут храним пары: {ID_игрока: ID_противника}

def main_menu(user_id):
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔍 Найти игру")
    kb.button(text="❌ Выйти из очереди")
    kb.button(text="🏁 Завершить матч")
    if user_id == ADMIN_ID:
        kb.button(text="⚙️ Админка")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🪖 **Ranked Firefight**\nЖми поиск!", reply_markup=main_menu(message.from_user.id))

@dp.message(F.text == "🔍 Найти игру")
async def join_queue(message: types.Message):
    uid = message.from_user.id
    if uid in queue:
        await message.answer("⏳ Ты уже ищешь игру.")
    elif uid in matches:
        await message.answer("🎮 Ты уже в матче!")
    else:
        queue.append(uid)
        await message.answer(f"✅ В очереди. Поиск: {len(queue)}")
        
        if len(queue) >= 2:
            p1, p2 = queue.pop(0), queue.pop(0)
            matches[p1], matches[p2] = p2, p1
            
            # Назначаем p1 хостом
            await bot.send_message(p1, "🔥 **Матч найден! Ты — ХОСТ.**\nСоздавай лобби и **просто напиши код сюда**, я перешлю его противнику.")
            await bot.send_message(p2, "🔥 **Матч найден!**\nТвой противник — хост. Жди код лобби здесь.")

@dp.message(F.text == "❌ Выйти из очереди")
async def leave(message: types.Message):
    if message.from_user.id in queue:
        queue.remove(message.from_user.id)
        await message.answer("❌ Вышел из поиска.")

@dp.message(F.text == "🏁 Завершить матч")
async def end(message: types.Message):
    uid = message.from_user.id
    if uid in matches:
        opp = matches.pop(uid)
        matches.pop(opp, None)
        await message.answer("🏁 Матч завершен.")
        await bot.send_message(opp, "🏁 Противник завершил матч.")
    else:
        await message.answer("Ты сейчас не в матче.")

# ПЕРЕСЫЛКА КОДА ЛОББИ
@dp.message(lambda message: message.from_user.id in matches)
async def handle_match_chat(message: types.Message):
    if message.text and not message.text.startswith(('/', '🔍', '❌', '🏁', '⚙️')):
        opponent_id = matches[message.from_user.id]
        await bot.send_message(opponent_id, f"📩 **Код лобби от противника:**\n`{message.text}`", parse_mode="Markdown")
        await message.answer("✅ Код отправлен противнику.")

# Админка
@dp.message(F.text == "⚙️ Админка")
async def admin(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(f"📊 В поиске: {len(queue)}\nВ матчах: {len(matches)//2}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
