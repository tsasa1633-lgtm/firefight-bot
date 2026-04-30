import asyncio
import logging
import random
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

db = {"players": {}, "queue": [], "matches": {}}

class MatchState(StatesGroup):
    waiting_for_code = State()           # Отправка кода лобби (хост)
    waiting_for_screenshot = State()     # Старый способ через скрин
    waiting_for_opponent_code = State()  # Новый — ввод кода соперника
    waiting_for_report = State()         # Репорт + скрин


# --- СТИЛИЗАЦИЯ ---
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

def match_actions(match_id: str):
    """Общая клавиатура для обоих игроков"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Отправить свой код сопернику", callback_data=f"action:send_mycode:{match_id}")
    builder.button(text="✅ Я победил (ввести код)", callback_data=f"action:win_code:{match_id}")
    builder.button(text="🚩 Репорт на соперника", callback_data=f"action:report:{match_id}")
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
        caption="<b>⚔️ FIREFIGHT Matchmaking</b>\n\nДобро пожаловать в систему поиска игр. Выберите режим, чтобы начать путь к Легенде.",
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
    p = db["players"][callback.from_user.id]

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
    mod = callback.data.split(":")[1]
    uid = callback.from_user.id

    if db["players"][uid]["in_match"]:
        return await callback.answer("❌ Вы находитесь в активном матче!", show_alert=True)

    opponent = next((e for e in db["queue"] if e["mod"] == mod and e["uid"] != uid), None)
    if opponent:
        db["queue"].remove(opponent)
        await create_match(uid, opponent["uid"], mod)
    else:
        if not any(e["uid"] == uid for e in db["queue"]):
            db["queue"].append({"uid": uid, "mod": mod})
        cancel_kb = InlineKeyboardBuilder()
        cancel_kb.button(text="❌ Отмена", callback_data="back_to_mods")
        await callback.message.edit_caption(
            caption=f"🔍 <b>ПОИСК ИГРЫ [{mod}]</b>\n\nСистема подбирает достойного соперника. Пожалуйста, ожидайте...",
            reply_markup=cancel_kb.as_markup(),
            parse_mode="HTML"
        )


async def create_match(p1: int, p2: int, mod: str):
    m_id = f"m_{p1}{p2}{int(datetime.now().timestamp())}"
    
    # Генерируем уникальные коды для каждого
    code1 = str(random.randint(1000, 9999))
    code2 = str(random.randint(1000, 9999))

    db["players"][p1]["in_match"] = db["players"][p2]["in_match"] = True
    f_map = random.choice(MAPS)

    db["matches"][m_id] = {
        "p1": p1,
        "p2": p2,
        "mod": mod,
        "map": f_map,
        "code_p1": code1,
        "code_p2": code2
    }

    for p_id in [p1, p2]:
        is_host = p_id == p1
        role = "<b>ХОСТ</b> (Создай лобби)" if is_host else "<b>ГОСТЬ</b> (Жди код)"
        my_code = code1 if p_id == p1 else code2

        text = (
            f"⚔️ <b>МАТЧ НАЙДЕН!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 Локация: <code>{f_map}</code>\n"
            f"🛠 Мод: <code>{mod}</code>\n"
            f"🎭 Твоя роль: {role}\n"
            f"🔑 <b>Твой код:</b> <code>{my_code}</code>\n\n"
            f"<i>После игры отправь сопернику свой код.\n"
            f"Победитель должен ввести код проигравшего.</i>"
        )

        await bot.send_message(
            p_id, 
            text, 
            reply_markup=match_actions(m_id), 
            parse_mode="HTML"
        )


# --- ПРОФИЛЬ И ТОП ---
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    p = db["players"].get(callback.from_user.id)
    text = (
        f"👤 <b>ЛИЧНОЕ ДЕЛО: {p['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏅 Ранг: {get_rank(p['elo'])}\n"
        f"📈 ELO: <code>{p['elo']}</code>\n"
        f"⏹ Прогресс: <code>{get_progress_bar(p['elo'])}</code>\n\n"
        f"✅ Побед: <b>{p['wins']}</b>\n"
        f"❌ Поражений: <b>{p['losses']}</b>"
    )
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "top")
async def show_top(callback: types.CallbackQuery):
    sorted_p = sorted(db["players"].values(), key=lambda x: x['elo'], reverse=True)[:10]
    text = "🏆 <b>ЭЛИТА FIREFIGHT (TOP 10)</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i, p in enumerate(sorted_p, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        text += f"{medal} <b>{p['name']}</b> — <code>{p['elo']}</code>\n"
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")
    await callback.answer()


# === ОТПРАВКА СВОЕГО КОДА СОПЕРНИКУ ===
@dp.callback_query(F.data.startswith("action:send_mycode:"))
async def send_my_code(callback: types.CallbackQuery, state: FSMContext):
    m_id = callback.data.split(":")[2]
    match = db["matches"].get(m_id)
    if not match:
        return await callback.answer("❌ Матч не найден", show_alert=True)

    user_id = callback.from_user.id
    my_code = match["code_p1"] if user_id == match["p1"] else match["code_p2"]

    await state.update_data(m_id=m_id, my_code=my_code)
    await state.set_state(MatchState.waiting_for_code)

    await callback.message.answer(
        f"🔑 <b>ТВОЙ КОД ДЛЯ ОТПРАВКИ:</b> <code>{my_code}</code>\n\n"
        f"Скопируй его и отправь сопернику в личные сообщения.\n\n"
        f"После отправки нажми кнопку ниже:",
        reply_markup=InlineKeyboardBuilder().button(
            text="✅ Я отправил код сопернику", 
            callback_data=f"code_sent:{m_id}"
        ).as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("code_sent:"))
async def confirm_code_sent(callback: types.CallbackQuery):
    await callback.answer("✅ Код отправлен. Ожидаем код от соперника.", show_alert=True)


# === ПОБЕДА ЧЕРЕЗ КОД СОПЕРНИКА ===
@dp.callback_query(F.data.startswith("action:win_code:"))
async def win_with_code(callback: types.CallbackQuery, state: FSMContext):
    m_id = callback.data.split(":")[2]
    await state.update_data(m_id=m_id)
    await state.set_state(MatchState.waiting_for_opponent_code)
    await callback.message.answer(
        "🔑 <b>ВВЕДИ КОД СОПЕРНИКА</b>\n\nПришли 4-значный код, который тебе скинул противник.",
        parse_mode="HTML"
    )


@dp.message(MatchState.waiting_for_opponent_code)
async def process_opponent_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m_id = data.get('m_id')
    match = db["matches"].get(m_id)
    if not match:
        await message.answer("❌ Матч не найден.")
        await state.clear()
        return

    code = message.text.strip()
    user_id = message.from_user.id

    if user_id == match["p1"]:
        opponent_id = match["p2"]
        correct_code = match["code_p2"]
    else:
        opponent_id = match["p1"]
        correct_code = match["code_p1"]

    if code == correct_code:
        await process_win(message, state, m_id, user_id, opponent_id)
    else:
        await message.answer("❌ Неверный код. Попробуй ещё раз или используй репорт.")


async def process_win(message: types.Message, state: FSMContext, m_id: str, winner_id: int, loser_id: int):
    for u, e in [(winner_id, 25), (loser_id, -25)]:
        db["players"][u]["elo"] += e
        db["players"][u]["in_match"] = False
        res = "🏆 <b>ПОБЕДА!</b> +25 ELO" if e > 0 else "💀 <b>ПОРАЖЕНИЕ</b> -25 ELO"
        if e > 0:
            db["players"][u]["wins"] += 1
        else:
            db["players"][u]["losses"] += 1
        await bot.send_message(u, res, reply_markup=play_again_kb(), parse_mode="HTML")

    if m_id in db["matches"]:
        del db["matches"][m_id]

    await message.answer("✅ Победа засчитана автоматически!", reply_markup=play_again_kb())
    await state.clear()


# === РЕПОРТ НА СОПЕРНИКА ===
@dp.callback_query(F.data.startswith("action:report:"))
async def report_start(callback: types.CallbackQuery, state: FSMContext):
    m_id = callback.data.split(":")[2]
    await state.update_data(m_id=m_id)
    await state.set_state(MatchState.waiting_for_report)
    await callback.message.answer(
        "🚩 <b>РЕПОРТ НА СОПЕРНИКА</b>\n\nНапиши короткое описание проблемы и сразу отправь скриншот своей победы.",
        parse_mode="HTML"
    )


@dp.message(MatchState.waiting_for_report, F.photo)
async def report_with_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m_id = data.get('m_id')
    match = db["matches"].get(m_id)
    if not match:
        await state.clear()
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "N/A"

    admin_caption = (
        f"🚨 <b>РЕПОРТ НА СОПЕРНИКА</b>\n"
        f"👤 От: {user.full_name} ({username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"⚔️ Матч: <code>{m_id}</code>\n"
        f"👥 {match['p1']} vs {match['p2']}\n\n"
        f"Описание: {message.caption or 'Без описания'}"
    )

    await bot.send_photo(
        ADMIN_CHAT_ID,
        photo=message.photo[-1].file_id,
        caption=admin_caption,
        reply_markup=InlineKeyboardBuilder()
            .button(text=f"✅ Вин {match['p1']}", callback_data=f"adm_res:{m_id}:{match['p1']}:{match['p2']}")
            .button(text=f"✅ Вин {match['p2']}", callback_data=f"adm_res:{m_id}:{match['p2']}:{match['p1']}")
            .button(text="❌ Отклонить", callback_data=f"adm_cancel:{m_id}")
            .adjust(2, 1).as_markup(),
        parse_mode="HTML"
    )

    await message.answer("✅ Репорт отправлен администрации.")
    await state.clear()


# === СТАРЫЕ ОБРАБОТЧИКИ (оставлены для совместимости) ===
@dp.callback_query(F.data.startswith("action:code:"))
async def c_req(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[2])
    await state.set_state(MatchState.waiting_for_code)
    await callback.message.answer("🔑 <b>ВВЕДИТЕ КОД ЛОББИ</b>\nНапишите код для соперника.", parse_mode="HTML")


@dp.message(MatchState.waiting_for_code)
async def c_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m = db["matches"].get(data.get('m_id'))
    if m:
        target = m["p2"] if message.from_user.id == m["p1"] else m["p1"]
        await bot.send_message(target, f"🔑 <b>КОД ЛОББИ:</b>\n<code>{message.text}</code>", parse_mode="HTML")
        await message.answer("✅ Код отправлен сопернику.")
    await state.clear()


@dp.callback_query(F.data.startswith("action:win:"))
async def win_req(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[2])
    await state.set_state(MatchState.waiting_for_screenshot)
    await callback.message.answer("📸 Отправь скриншот результата.", parse_mode="HTML")


@dp.message(MatchState.waiting_for_screenshot, F.photo)
async def admin_check(message: types.Message, state: FSMContext):
    # ... (оставил как было, можешь удалить позже)
    await message.answer("Этот способ пока оставлен для совместимости.")
    await state.clear()


@dp.callback_query(F.data.startswith("adm_res:"))
async def admin_confirm(callback: types.CallbackQuery):
    _, m_id, win_id, los_id = callback.data.split(":")
    win_id, los_id = int(win_id), int(los_id)

    for u, e in [(win_id, 25), (los_id, -25)]:
        db["players"][u]["elo"] += e
        db["players"][u]["in_match"] = False
        res = "🏆 <b>ПОБЕДА!</b> +25 ELO" if e > 0 else "💀 <b>ПОРАЖЕНИЕ</b> -25 ELO"
        if e > 0:
            db["players"][u]["wins"] += 1
        else:
            db["players"][u]["losses"] += 1
        await bot.send_message(u, res, reply_markup=play_again_kb(), parse_mode="HTML")

    await callback.message.edit_caption(caption="✅ Результат зафиксирован.")
    if m_id in db["matches"]:
        del db["matches"][m_id]


# === ЗАПУСК ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
