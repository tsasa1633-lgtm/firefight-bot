import asyncio
import logging
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# --- НАСТРОЙКИ ---
API_TOKEN = '8680030204:AAEg8lmgQo9hKanAMC8UsFqSSnpoXWL9mUs'
ADMIN_CHAT_ID = -5288317466
MAPS = ["Village", "Forest", "Bunker", "Outpost", "Desert", "Swamp", "Factory"]
MODS = ["FLEXXY mods", "D.I.W mods"]

ELO_K_FACTOR = 32

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ВРЕМЕННАЯ БД ---
db = {
    "players": {},
    "queue": [],
    "matches": {},
    "banned": set(),
    "reports": {},
}

# --- СОСТОЯНИЯ ---
class MatchState(StatesGroup):
    waiting_for_code = State()
    waiting_for_screenshot = State()
    waiting_for_dispute = State()
    waiting_for_report = State()

# =====================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================

def is_registered(uid: int) -> bool:
    return uid in db["players"]

def elo_change(winner_elo: int, loser_elo: int) -> int:
    expected_win = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    change = round(ELO_K_FACTOR * (1 - expected_win))
    return max(10, min(40, change))

def get_rank(elo: int) -> str:
    if elo < 900:   return "🟤 Бронза"
    if elo < 1100:  return "⚪ Серебро"
    if elo < 1300:  return "🟡 Золото"
    if elo < 1500:  return "💎 Платина"
    if elo < 1800:  return "👑 Мастер"
    return "🔥 Легенда"

def find_opponent(uid: int, selected_mod: str):
    my_elo = db["players"][uid]["elo"]
    # Ищем соперника только в том же моде
    potential_opponents = [e for e in db["queue"] if e["uid"] != uid and e["mod"] == selected_mod]
    
    for entry in potential_opponents:
        candidate = entry["uid"]
        if abs(my_elo - db["players"][candidate]["elo"]) <= 200:
            return candidate
            
    for entry in potential_opponents:
        candidate = entry["uid"]
        if (datetime.now() - entry["joined_at"]).seconds > 60:
            return candidate
    return None

def leave_queue(uid: int):
    db["queue"] = [e for e in db["queue"] if e["uid"] != uid]

# =====================
# КЛАВИАТУРЫ
# =====================

def mod_selection_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 FLEXXY mods", callback_data="select_mod:FLEXXY mods")
    builder.button(text="🛠 D.I.W mods", callback_data="select_mod:D.I.W mods")
    builder.adjust(1)
    return builder.as_markup()

def main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Найти игру", callback_data="choose_mod")
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="🏆 ТОП-10", callback_data="top")
    builder.button(text="📜 История матчей", callback_data="history")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def queue_cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить поиск", callback_data="leave_queue")
    return builder.as_markup()

def ban_keyboard(match_id: str):
    match = db["matches"][match_id]
    builder = InlineKeyboardBuilder()
    for m in match["maps"]:
        builder.button(text=f"❌ {m}", callback_data=f"ban:{match_id}:{m}")
    builder.adjust(2)
    return builder.as_markup()

def match_actions(match_id: str, is_host: bool = False):
    builder = InlineKeyboardBuilder()
    if is_host:
        builder.button(text="📝 Отправить код лобби", callback_data=f"set_code:{match_id}")
    builder.button(text="🏆 Я победил (скриншот)", callback_data=f"win_report:{match_id}")
    builder.button(text="🚩 Репорт на игрока", callback_data=f"report_player:{match_id}")
    builder.adjust(1)
    return builder.as_markup()

def confirm_result_kb(match_id: str, winner_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить победу", callback_data=f"confirm_result:{match_id}:{winner_id}")
    builder.button(text="❌ Оспорить", callback_data=f"dispute_result:{match_id}:{winner_id}")
    builder.adjust(1)
    return builder.as_markup()

def admin_decision_kb(match_id: str, winner_id: int, loser_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Победа {winner_id}", callback_data=f"admin_win:{match_id}:{winner_id}:{loser_id}")
    builder.button(text=f"🔄 Рематч", callback_data=f"admin_rematch:{match_id}")
    builder.button(text=f"🚫 Бан {winner_id}", callback_data=f"admin_ban:{winner_id}")
    builder.button(text=f"🚫 Бан {loser_id}", callback_data=f"admin_ban:{loser_id}")
    builder.adjust(2, 2)
    return builder.as_markup()

def report_reason_kb(match_id: str, reported_id: int):
    builder = InlineKeyboardBuilder()
    reasons = ["Читы/Хак", "Оскорбления", "Намеренный выход", "Фейк победа", "Другое"]
    for r in reasons:
        builder.button(text=r, callback_data=f"report_reason:{match_id}:{reported_id}:{r}")
    builder.adjust(2)
    return builder.as_markup()

# =====================
# ОБРАБОТЧИКИ
# =====================

@dp.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    if uid in db["banned"]:
        return await message.answer("🚫 Ты заблокирован в системе.")

    if uid not in db["players"]:
        db["players"][uid] = {
            "elo": 1000,
            "name": message.from_user.full_name,
            "wins": 0,
            "losses": 0,
            "match_history": [],
            "registered_at": datetime.now(),
            "in_match": False,
            "reports_received": 0,
            "warnings": 0,
        }

    p = db["players"][uid]
    await message.answer_photo(
        photo="https://i.yapx.ru/dffXD.jpg",
        caption=(
            f"⚔️ <b>FIREFIGHT Matchmaking</b>\n\n"
            f"Игрок: <b>{p['name']}</b>\n"
            f"Рейтинг: <code>{p['elo']}</code> {get_rank(p['elo'])}\n"
            f"Побед: <b>{p['wins']}</b> | Поражений: <b>{p['losses']}</b>"
        ),
        reply_markup=main_menu(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "choose_mod")
async def choose_mod(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>ВЫБОР МОДА</b>\n\nВыбери мод для игры:",
        reply_markup=mod_selection_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("select_mod:"))
async def join_queue(callback: types.CallbackQuery):
    selected_mod = callback.data.split(":")[1]
    uid = callback.from_user.id
    
    if uid in db["banned"]:
        return await callback.answer("🚫 Ты заблокирован.", show_alert=True)
    if not is_registered(uid):
        return await callback.answer("Сначала напиши /start", show_alert=True)
    if db["players"][uid].get("in_match"):
        return await callback.answer("Ты уже в активном матче!", show_alert=True)
    if any(e["uid"] == uid for e in db["queue"]):
        return await callback.answer("Ты уже в очереди!", show_alert=True)

    db["queue"].append({"uid": uid, "joined_at": datetime.now(), "mod": selected_mod})

    await callback.message.edit_text(
        f"🔍 <b>Поиск противника [{selected_mod}]...</b>\n"
        f"Твой ELO: <code>{db['players'][uid]['elo']}</code>\n"
        f"В очереди: <b>{len([e for e in db['queue'] if e['mod'] == selected_mod])}</b>",
        reply_markup=queue_cancel_kb(), parse_mode="HTML"
    )

    opponent = find_opponent(uid, selected_mod)
    if opponent:
        await create_match(uid, opponent)
    else:
        await callback.answer("Ищем соперника...")

@dp.callback_query(F.data == "leave_queue")
async def leave_queue_handler(callback: types.CallbackQuery):
    leave_queue(callback.from_user.id)
    await callback.message.edit_text("❌ Поиск отменён.", reply_markup=main_menu())
    await callback.answer()

# =====================
# МАТЧ И БАНЫ
# =====================

async def create_match(p1: int, p2: int):
    leave_queue(p1)
    leave_queue(p2)
    db["players"][p1]["in_match"] = True
    db["players"][p2]["in_match"] = True

    match_id = f"{p1}_{p2}_{int(datetime.now().timestamp())}"
    selected_maps = random.sample(MAPS, min(5, len(MAPS)))
    first_ban = random.choice([p1, p2])

    db["matches"][match_id] = {
        "p1": p1, "p2": p2,
        "maps": selected_maps,
        "turn": first_ban,
        "history": [],
        "status": "banning",
        "host": p1,
        "created_at": datetime.now(),
        "winner": None,
        "final_map": None,
    }

    for p_id in [p1, p2]:
        await bot.send_photo(
            p_id,
            photo="https://i.yapx.ru/dffXc.png",
            caption=f"⚔️ <b>Матч найден!</b>\n\nПервый банит: <b>{db['players'][first_ban]['name']}</b>",
            reply_markup=ban_keyboard(match_id), parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("ban:"))
async def handle_ban(callback: types.CallbackQuery):
    _, match_id, map_name = callback.data.split(":")
    match = db["matches"].get(match_id)
    if not match or callback.from_user.id != match["turn"]:
        return await callback.answer("Не твой ход или матч не найден!", show_alert=True)

    match["maps"].remove(map_name)
    match["history"].append(f"❌{map_name}")
    match["turn"] = match["p2"] if match["turn"] == match["p1"] else match["p1"]

    if len(match["maps"]) > 1:
        text = f"🏟 <b>Бан карт</b>\nХодит: <b>{db['players'][match['turn']]['name']}</b>"
        for p_id in [match["p1"], match["p2"]]:
            await bot.send_message(p_id, text, reply_markup=ban_keyboard(match_id), parse_mode="HTML")
    else:
        final_map = match["maps"][0]
        match["status"] = "active"
        match["final_map"] = final_map
        for p_id in [match["p1"], match["p2"]]:
            is_host = (p_id == match["host"])
            await bot.send_message(p_id, f"✅ <b>Карта: {final_map}</b>", reply_markup=match_actions(match_id, is_host), parse_mode="HTML")
    await callback.answer()

# =====================
# КОД, СКРИНЫ И ЗАВЕРШЕНИЕ
# =====================

@dp.callback_query(F.data.startswith("set_code:"))
async def ask_code(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[1])
    await state.set_state(MatchState.waiting_for_code)
    await callback.message.answer("🔑 Введи код лобби:")
    await callback.answer()

@dp.message(MatchState.waiting_for_code)
async def relay_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    match = db["matches"].get(data['m_id'])
    guest_id = match["p2"] if message.from_user.id == match["p1"] else match["p1"]
    await bot.send_message(guest_id, f"🔑 <b>Код лобби:</b> <code>{message.text}</code>", parse_mode="HTML")
    await message.answer("✅ Код отправлен!")
    await state.clear()

@dp.callback_query(F.data.startswith("win_report:"))
async def ask_screenshot(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[1])
    await state.set_state(MatchState.waiting_for_screenshot)
    await callback.message.answer("📸 Пришли скриншот победы:")
    await callback.answer()

@dp.message(MatchState.waiting_for_screenshot, F.photo)
async def process_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    match = db["matches"].get(data['m_id'])
    winner_id = message.from_user.id
    loser_id = match["p2"] if winner_id == match["p1"] else match["p1"]

    await bot.send_message(loser_id, "⚠️ Соперник заявил о победе! Подтверди.", reply_markup=confirm_result_kb(data['m_id'], winner_id))
    await bot.send_message(ADMIN_CHAT_ID, f"📸 Скрин от {winner_id} в матче {data['m_id']}", reply_markup=admin_decision_kb(data['m_id'], winner_id, loser_id))
    await message.answer("📤 Отправлено!")
    await state.clear()

async def finalize_match(match_id, winner_id, loser_id):
    match = db["matches"][match_id]
    match["status"] = "finished"
    db["players"][winner_id]["in_match"] = False
    db["players"][loser_id]["in_match"] = False
    
    change = elo_change(db["players"][winner_id]["elo"], db["players"][loser_id]["elo"])
    db["players"][winner_id]["elo"] += change
    db["players"][loser_id]["elo"] -= change
    db["players"][winner_id]["wins"] += 1
    db["players"][loser_id]["losses"] += 1
    
    res = {"map": match["final_map"], "elo_change": change, "opponent": db["players"][loser_id]["name"]}
    db["players"][winner_id]["match_history"].append({**res, "result": "win"})
    db["players"][loser_id]["match_history"].append({**res, "result": "loss", "opponent": db["players"][winner_id]["name"]})

    for p_id, text in [(winner_id, f"🏆 Победа! +{change} ELO"), (loser_id, f"💀 Поражение! -{change} ELO")]:
        await bot.send_message(p_id, text)

@dp.callback_query(F.data.startswith("confirm_result:"))
async def confirm_res(callback: types.CallbackQuery):
    _, m_id, w_id = callback.data.split(":")
    match = db["matches"].get(m_id)
    loser_id = match["p2"] if int(w_id) == match["p1"] else match["p1"]
    await finalize_match(m_id, int(w_id), loser_id)
    await callback.message.edit_text("✅ Подтверждено")

# =====================
# ПРОФИЛЬ, ТОП, ИСТОРИЯ
# =====================

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    p = db["players"].get(callback.from_user.id)
    text = f"👤 <b>{p['name']}</b>\nРанг: {get_rank(p['elo'])}\nELO: {p['elo']}\nW/L: {p['wins']}/{p['losses']}"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "top")
async def top_players(callback: types.CallbackQuery):
    sorted_p = sorted(db["players"].items(), key=lambda x: x[1]['elo'], reverse=True)[:10]
    text = "🏆 <b>ТОП-10</b>\n\n"
    for i, (uid, data) in enumerate(sorted_p):
        text += f"{i+1}. {data['name']} — {data['elo']}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "history")
async def match_history(callback: types.CallbackQuery):
    p = db["players"].get(callback.from_user.id)
    history = p.get("match_history", [])
    if not history: return await callback.message.answer("Пусто")
    text = "📜 <b>История</b>\n"
    for m in history[-5:]:
        text += f"{'🏆' if m['result']=='win' else '💀'} vs {m['opponent']} | {m['map']} | {m['elo_change']}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
