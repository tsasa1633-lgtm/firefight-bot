import os
import asyncio
import random
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
API_TOKEN = os.environ.get('TOKEN')
DB_URL = os.environ.get('DATABASE_URL')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
queue = []
active_matches = {}

async def init_db():
    conn = await asyncpg.connect(DB_URL)
    await conn.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)')
    await conn.close()

async def add_user_to_db(user_id):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute('INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING', user_id)
    await conn.close()

async def get_all_users_from_db():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch('SELECT user_id FROM users')
    await conn.close()
    return [row['user_id'] for row in rows]

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔍 Найти игру"))
    builder.row(types.KeyboardButton(text="❌ Выйти из очереди"), types.KeyboardButton(text="🏁 Завершить матч"))
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await add_user_to_db(message.from_user.id)
    await message.answer("🪖 **Ranked Firefight**\nБот запущен!", reply_markup=main_menu(), parse_mode="Markdown")

@dp.message(F.text == "🔍 Найти игру")
async def find_match(message: types.Message):
    uid = message.from_user.id
    if uid in active_matches or uid in queue: return
    if queue:
        opp_id = queue.pop(0)
        active_matches[uid], active_matches[opp_id] = opp_id, uid
        host = random.choice([uid, opp_id])
        guest = opp_id if host == uid else uid
        await bot.send_message(host, "🔥 Ты — ХОСТ. Создавай лобби и пиши код сюда.")
        await bot.send_message(guest, "🔥 Ты — ГОСТЬ. Жди код.")
    else:
        queue.append(uid)
        await message.answer("🔎 Поиск...")

@dp.message(F.text == "🏁 Завершить матч")
async def finish_match(message: types.Message):
    uid = message.from_user.id
    if uid in active_matches:
        opp_id = active_matches[uid]
        del active_matches[uid], active_matches[opp_id]
        await message.answer("🏁 Матч завершен.")
        await bot.send_message(opp_id, "🏁 Противник завершил матч.")

@dp.message(F.text & ~F.text.startswith('/'))
async def game_chat(message: types.Message):
    if message.from_user.id in active_matches:
        await bot.send_message(active_matches[message.from_user.id], f"💬: `{message.text}`", parse_mode="Markdown")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
          
