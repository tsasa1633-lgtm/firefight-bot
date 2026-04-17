import os
import asyncio
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("API_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

PHOTO_MAIN = "https://i.yapx.ru/dZgZW.jpg"
PHOTO_CHOICE = "https://i.yapx.ru/dZgaO.jpg"

# БД в памяти
queues = {"flexxy": [], "editor": []}
matches = {}      
elo_ratings = {}  

# --- FACEIT МАТЕМАТИКА ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    if elo <= 500: return "1️⃣"
    if elo <= 750: return "2️⃣"
    if elo <= 900: return "3️⃣"
    if elo <= 1050: return "4️⃣" # Дефолт
    if elo <= 1200: return "5️⃣"
    if elo <= 1350: return "6️⃣"
    if elo <= 1500: return "7️⃣"
    if elo <= 1650: return "8️⃣"
    if elo <= 1850: return "9️⃣"
    return "🔟"

def calculate_elo(winner_elo, loser_elo):
    # Упрощенная формула Faceit: если равны — по 25 очков.
    # Если ты выиграл у того, кто сильнее тебя — получишь больше.
    diff = (loser_elo - winner_elo) * 0.1
    gain = round(25 + diff)
    return max(10, min(50, gain)) # Минимум 10, максимум 50 за катку

# --- КЛАВИАТУРЫ ---
def get_search_kb(mode, uid):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Найти матч", callback_data=f"join_{mode}"))
    kb.row(InlineKeyboardButton(text="🏆 Я ВЫИГРАЛ", callback_data="win_report"))
    kb.row(InlineKeyboardButton(text="🏳️ Сдаться (L)", callback_data="lose_report"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="go_to_mods"))
    kb.adjust(1)
    return kb.as_markup()

# --- ЛОГИКА ---

@dp.callback_query(F.data == "win_report")
async def win_report(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in matches: return
    
    opp_id = matches[uid]
    # Сообщаем противнику, что он должен подтвердить
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Подтверждаю (L)", callback_data=f"confirm_loss_{uid}"))
    await bot.send_message(opp_id, "❗ Твой оппонент нажал «Победа». Если ты проиграл, нажми подтверждение для списания ELO.")
    await callback.answer("Запрос отправлен оппоненту. Ждем подтверждения.")

@dp.callback_query(F.data == "lose_report")
async def lose_report(callback: types.CallbackQuery):
    # Если игрок сам признал поражение - всё быстро
    loser_id = callback.from_user.id
    if loser_id not in matches: return
    
    winner_id = matches[loser_id]
    await process_match_result(winner_id, loser_id)

async def process_match_result(winner_id, loser_id):
    w_elo = get_elo(winner_id)
    l_elo = get_elo(loser_id)
    
    points = calculate_elo(w_elo, l_elo)
    
    elo_ratings[winner_id] = w_elo + points
    elo_ratings[loser_id] = max(0, l_elo - points)
    
    matches.pop(winner_id, None)
    matches.pop(loser_id, None)
    
    await bot.send_message(winner_id, f"📈 **MATCH WIN!**\n+{points} ELO. Новый рейтинг: `{get_elo(winner_id)}` {get_lvl(get_elo(winner_id))}")
    await bot.send_message(loser_id, f"📉 **MATCH LOSS!**\n-{points} ELO. Новый рейтинг: `{get_elo(loser_id)}` {get_lvl(get_elo(loser_id))}")

@dp.callback_query(F.data.startswith("confirm_loss_"))
async def confirm_loss(callback: types.CallbackQuery):
    winner_id = int(callback.data.split("_")[2])
    loser_id = callback.from_user.id
    if loser_id in matches and matches[loser_id] == winner_id:
        await process_match_result(winner_id, loser_id)
        await callback.message.delete()

# --- ПОИСК МАТЧА (FACEIT STYLE) ---
@dp.callback_query(F.data.startswith("join_"))
async def join(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_")[1]
    queues[mode].append(uid)
    await callback.answer("В очереди...")

    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        matches[p1], matches[p2] = p2, p1
        
        # Красивая карточка матча
        card = (
            f"🎮 **MATCH START**\n\n"
            f"🔴 {get_lvl(get_elo(p1))} Player 1 (Elo: {get_elo(p1)})\n"
            f"🔵 {get_lvl(get_elo(p2))} Player 2 (Elo: {get_elo(p2)})\n\n"
            f"🗺 Карта: По договоренности\n"
            f"💎 Награда: ~25 ELO"
        )
        await bot.send_message(p1, card + "\n\n**ТЫ ХОСТ**")
        await bot.send_message(p2, card + "\n\n**ЖДИ КОД**")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
