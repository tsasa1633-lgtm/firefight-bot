import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Настройки из Railway
TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) # Твой ID должен быть в Variables!
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Список игроков в очереди
queue = []

# Главное меню
def main_menu(user_id):
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔍 Найти игру")
    kb.button(text="❌ Выйти из очереди")
    kb.button(text="🏁 Завершить матч")
    
    # Если пишет админ, добавляем кнопку управления
    if user_id == ADMIN_ID:
        kb.button(text="⚙️ Админка")
        
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🪖 **Ranked Firefight**\nСистема готова.",
        reply_markup=main_menu(message.from_user.id),
        parse_mode="Markdown"
    )

# --- ЛОГИКА ИГРОКОВ ---

@dp.message(F.text == "🔍 Найти игру")
async def join_queue(message: types.Message):
    user_id = message.from_user.id
    if user_id in queue:
        await message.answer("⚠️ Ты уже в очереди!")
    else:
        queue.append(user_id)
        await message.answer(f"✅ Встал в очередь. В поиске: {len(queue)}")
        
        if len(queue) >= 2:
            p1, p2 = queue.pop(0), queue.pop(0)
            msg = "🎮 **Матч найден!**\nИгроки: {0} и {1}".format(p1, p2)
            for p in [p1, p2]:
                await bot.send_message(p, msg, parse_mode="Markdown")

@dp.message(F.text == "❌ Выйти из очереди")
async def leave_queue(message: types.Message):
    if message.from_user.id in queue:
        queue.remove(message.from_user.id)
        await message.answer("❌ Вышел из очереди.")
    else:
        await message.answer("Тебя нет в списке.")

# --- ЛОГИКА АДМИНА ---

@dp.message(F.text == "⚙️ Админка")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return # Игнорим, если не админ

    status = f"📊 **Статус системы**\n\nВ очереди сейчас: `{len(queue)}` чел.\nСписок ID: `{queue}`"
    
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧹 Очистить очередь")
    kb.button(text="🔙 Назад")
    kb.adjust(1)
    
    await message.answer(status, reply_markup=kb.as_markup(resize_keyboard=True), parse_mode="Markdown")

@dp.message(F.text == "🧹 Очистить очередь")
async def clear_queue(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        queue.clear()
        await message.answer("✅ Очередь полностью очищена!", reply_markup=main_menu(ADMIN_ID))

@dp.message(F.text == "🔙 Назад")
async def go_back(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu(message.from_user.id))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
