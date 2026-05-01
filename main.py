import asyncio
import logging
import random
import string
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- НАСТРОЙКИ ---
API_TOKEN = '8680030204:AAEg8lmgQo9hKanAMC8UsFqSSnpoXWL9mUs'
ADMIN_CHAT_ID = -5288317466
MAPS = ["Харьков", "Авдеевка", "Часов Яр", "а/р Антонова", "Бахмут"]
MAIN_PHOTO = "https://i.yapx.ru/dffXD.jpg"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Временная база данных
db = {"players": {}, "queue": [], "matches": {}}

class MatchState(StatesGroup):
    waiting_for_lobby_code = State()     # Код для входа в игру (от хоста)
    waiting_for_enemy_token = State()    # Секретный код соперника для победы
    waiting_for_report_screen = State()   # Скриншот при жалобе

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(elo: int) -> str:
    if elo < 900:   return "🟤 Бронза"
    if elo < 1100:  return "⚪ Серебро"
    if elo < 1300:  return "🟡 Золото"
    if elo < 1500:  return "💎 Платина"
    if elo < 1800:  return "👑 Мастер"
    return "🔥 Легенда"

def get_progress_bar(elo: int):
    progress = (elo % 200) // 20
    return "🔹" * progress + "🔸" * (10 - progress)

def generate_token():
    return ''.join(random.choices(string.digits, k=4))

# --- КЛАВИАТУРЫ ---
def mod_selection_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 FLEXXY mods", callback_data="set_mod:FLEXXY mods")
    builder.button(text="🛠 D.I.W mods", callback_data="set_mod:D.I.W mods")
    builder.adjust(1)
    return builder.as_markup()

def lobby_menu(mod_name: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Найти игру", callback_data=f"search:{mod_name}")
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="🏆 ТОП-10", callback_data="top")
    builder.button(text="⬅️ Назад", callback_data="back_to_mods")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def match_actions(match_id: str, is_host: bool):
    builder = InlineKeyboardBuilder()
    if is_host:
        builder.button(text="🔑 Дать код ЛОББИ", callback_data=f"action:l_code:{match_id}")
    
    builder.button(text="📤 Отправить СВОЙ код", callback_data=f"action:send_tok:{match_id}")
    builder.button(text="🏆 Я Победил", callback_data=f"action:win_check:{match_id}")
    builder.button(text="🚩 Репорт", callback_data=f"action:report:{match_id}")
    builder.adjust(1)
    return builder.as_markup()

def play_again_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 В ГЛАВНОЕ МЕНЮ", callback_data="back_to_mods")
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    if uid not in db["players"]:
        db["players"][uid] = {"elo": 1000, "name": message.from_user.full_name, "wins": 0, "losses": 0, "in_match": False}
    
    await message.answer_photo(
        photo=MAIN_PHOTO, 
        caption="<b>⚔️ FIREFIGHT Matchmaking</b>\n\nВыберите мод для игры:", 
        reply_markup=mod_selection_kb(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_mods")
async def back_to_mods(callback: types.CallbackQuery):
    try:
        await callback.message.edit_caption(
            caption="<b>⚔️ FIREFIGHT Matchmaking</b>\n\nВыберите мод для игры:",
            reply_markup=mod_selection_kb(),
            parse_mode="HTML"
        )
    except:
        await callback.message.answer_photo(photo=MAIN_PHOTO, caption="⚔️ <b>ВЫБЕРИТЕ МОД:</b>", reply_markup=mod_selection_kb(), parse_mode="HTML")
        await callback.message.delete()

@dp.callback_query(F.data.startswith("set_mod:"))
async def open_lobby(callback: types.CallbackQuery):
    mod = callback.data.split(":")[1]
    p = db["players"].get(callback.from_user.id)
    text = (
        f"🛰 <b>РЕЖИМ: {mod}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Игрок: <b>{p['name']}</b>\n"
        f"🏅 Ранг: {get_rank(p['elo'])}\n"
        f"📊 ELO: <code>{p['elo']}</code>"
    )
    await callback.message.edit_caption(caption=text, reply_markup=lobby_menu(mod), parse_mode="HTML")

@dp.callback_query(F.data.startswith("search:"))
async def search(callback: types.CallbackQuery):
    mod, uid = callback.data.split(":")[1], callback.from_user.id
    if db["players"][uid].get("in_match"):
        return await callback.answer("❌ Вы уже в игре!", show_alert=True)

    opponent = next((e for e in db["queue"] if e["mod"] == mod and e["uid"] != uid), None)
    if opponent:
        db["queue"].remove(opponent)
        await create_match(uid, opponent["uid"], mod)
    else:
        if not any(e["uid"] == uid for e in db["queue"]): 
            db["queue"].append({"uid": uid, "mod": mod})
        await callback.message.edit_caption(
            caption=f"🔍 <b>ПОИСК ИГРЫ [{mod}]</b>\n\nОжидайте противника...", 
            reply_markup=InlineKeyboardBuilder().button(text="❌ Отмена", callback_data="back_to_mods").as_markup(), 
            parse_mode="HTML"
        )

async def create_match(p1, p2, mod):
    m_id = f"m_{p1}_{p2}_{int(datetime.now().timestamp())}"
    t1, t2 = generate_token(), generate_token()
    
    db["players"][p1]["in_match"] = db["players"][p2]["in_match"] = True
    db["matches"][m_id] = {
        "p1": p1, "p2": p2, 
        "p1_token": t1, "p2_token": t2, 
        "mod": mod, "map": random.choice(MAPS)
    }

    for p_id in [p1, p2]:
        role = "<b>ХОСТ</b>" if p_id == p1 else "<b>ГОСТЬ</b>"
        my_token = t1 if p_id == p1 else t2
        text = (
            f"⚔️ <b>МАТЧ НАЙДЕН!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 Локация: <code>{db['matches'][m_id]['map']}</code>\n"
            f"🎭 Роль: {role}\n"
            f"🎫 Твой код для соперника: <code>{my_token}</code>\n\n"
            f"<i>Если проиграете — отдайте этот код. Если выиграли — введите код соперника.</i>"
        )
        await bot.send_message(p_id, text, reply_markup=match_actions(m_id, p_id==p1), parse_mode="HTML")

# --- ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК МАТЧА ---

@dp.callback_query(F.data.startswith("action:"))
async def handle_match_actions(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    action = data_parts[1]
    m_id = data_parts[2]
    
    match = db["matches"].get(m_id)
    if not match:
        return await callback.answer("❌ Матч уже завершен или не найден.")

    if action == "l_code":
        await state.update_data(m_id=m_id)
        await state.set_state(MatchState.waiting_for_lobby_code)
        await callback.message.answer("⌨️ Введите код лобби (пароль), который увидит соперник:")

    elif action == "send_tok":
        # Отправляем свой токен сопернику
        is_p1 = callback.from_user.id == match["p1"]
        my_token = match["p1_token"] if is_p1 else match["p2_token"]
        target = match["p2"] if is_p1 else match["p1"]
        
        await bot.send_message(target, f"📩 Соперник прислал код подтверждения победы: <code>{my_token}</code>")
        await callback.answer("✅ Код отправлен сопернику!", show_alert=True)

    elif action == "win_check":
        await state.update_data(m_id=m_id)
        await state.set_state(MatchState.waiting_for_enemy_token)
        await callback.message.answer("🏆 Введите код, который вам скинул соперник после вашего выигрыша:")

    elif action == "report":
        await state.update_data(m_id=m_id)
        await state.set_state(MatchState.waiting_for_report_screen)
        await callback.message.answer("🚩 Отправьте скриншот победы. Мы проверим жалобу вручную.")

# --- ЛОГИКА ВВОДА ТЕКСТА ---

@dp.message(MatchState.waiting_for_enemy_token)
async def process_win_token(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m_id = data.get('m_id')
    match = db["matches"].get(m_id)
    if not match: return await state.clear()

    is_p1 = message.from_user.id == match["p1"]
    enemy_token = match["p2_token"] if is_p1 else match["p1_token"]
    
    if message.text.strip() == enemy_token:
        win_id = match["p1"] if is_p1 else match["p2"]
        los_id = match["p2"] if is_p1 else match["p1"]
        await finish_match(m_id, win_id, los_id)
        await state.clear()
    else:
        await message.answer("❌ Неверный код! Попробуйте еще раз или напишите жалобу (Репорт).")

@dp.message(MatchState.waiting_for_lobby_code)
async def process_lobby_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    match = db["matches"].get(data.get('m_id'))
    if match:
        target = match["p2"] if message.from_user.id == match["p1"] else match["p1"]
        await bot.send_message(target, f"🔑 <b>КОД ЛОББИ ОТ ХОСТА:</b>\n<code>{message.text}</code>", parse_mode="HTML")
        await message.answer("✅ Код доставлен сопернику.")
    await state.clear()

@dp.message(MatchState.waiting_for_report_screen, F.photo)
async def process_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m_id = data.get('m_id')
    match = db["matches"].get(m_id)
    
    admin_text = (
        f"🚨 <b>ЖАЛОБА</b>\nИгрок: {message.from_user.full_name}\nID: `{message.from_user.id}`\n"
        f"Матч: `{m_id}`\nПротив: `{match['p1'] if message.from_user.id != match['p1'] else match['p2']}`"
    )
    
    await bot.send_photo(
        ADMIN_CHAT_ID, 
        photo=message.photo[-1].file_id, 
        caption=admin_text,
        reply_markup=InlineKeyboardBuilder()
        .button(text="✅ Вин P1", callback_data=f"adm_res:{m_id}:{match['p1']}:{match['p2']}")
        .button(text="✅ Вин P2", callback_data=f"adm_res:{m_id}:{match['p2']}:{match['p1']}")
        .adjust(2).as_markup()
    )
    await message.answer("🆗 Жалоба принята. Ожидайте решения администрации.")
    await state.clear()

async def finish_match(m_id, win_id, los_id):
    for u, e in [(win_id, 25), (los_id, -25)]:
        if u in db["players"]:
            db["players"][u]["elo"] += e
            db["players"][u]["in_match"] = False
            if e > 0: db["players"][u]["wins"] += 1
            else: db["players"][u]["losses"] += 1
            
            res = "🏆 <b>ПОБЕДА!</b> +25 ELO" if e > 0 else "💀 <b>ПОРАЖЕНИЕ.</b> -25 ELO"
            await bot.send_message(u, res, reply_markup=play_again_kb(), parse_mode="HTML")
    
    if m_id in db["matches"]: 
        del db["matches"][m_id]

# --- ОСТАЛЬНЫЕ ФУНКЦИИ ---

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    p = db["players"].get(callback.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ: {p['name']}</b>\n🏅 Ранг: {get_rank(p['elo'])}\n📈 ELO: <code>{p['elo']}</code>\n"
            f"✅ Побед: {p['wins']} | ❌ Слив: {p['losses']}")
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "top")
async def show_top(callback: types.CallbackQuery):
    sorted_p = sorted(db["players"].values(), key=lambda x: x['elo'], reverse=True)[:10]
    text = "🏆 <b>TOP 10 ИГРОКОВ</b>\n"
    for i, p in enumerate(sorted_p, 1):
        text += f"{i}. {p['name']} — <code>{p['elo']}</code>\n"
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_res:"))
async def admin_decision(callback: types.CallbackQuery):
    _, m_id, win_id, los_id = callback.data.split(":")
    await finish_match(m_id, int(win_id), int(los_id))
    await callback.message.edit_caption(caption="✅ Результат изменен админом.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
