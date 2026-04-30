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
MAPS = ["Харьков", "Авдеевка", "Часов Яр", "а/р Антонова", "Бахмут", "Village", "Forest"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Временная БД (обнуляется при перезапуске)
db = {"players": {}, "queue": [], "matches": {}}

class MatchState(StatesGroup):
    waiting_for_code = State()
    waiting_for_screenshot = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(elo: int) -> str:
    if elo < 900:   return "🟤 Бронза"
    if elo < 1100:  return "⚪ Серебро"
    if elo < 1300:  return "🟡 Золото"
    if elo < 1500:  return "💎 Платина"
    if elo < 1800:  return "👑 Мастер"
    return "🔥 Легенда"

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
        builder.button(text="📝 Отправить код", callback_data=f"action:code:{match_id}")
    builder.button(text="🏆 Я победил (скрин)", callback_data=f"action:win:{match_id}")
    builder.button(text="🚩 Репорт", callback_data=f"action:report:{match_id}")
    builder.adjust(1)
    return builder.as_markup()

def admin_decision_kb(match_id: str, p1_id: int, p2_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Победил {p1_id}", callback_data=f"adm_res:{match_id}:{p1_id}:{p2_id}")
    builder.button(text=f"✅ Победил {p2_id}", callback_data=f"adm_res:{match_id}:{p2_id}:{p1_id}")
    builder.button(text="❌ Отклонить", callback_data=f"adm_cancel:{match_id}")
    builder.adjust(1)
    return builder.as_markup()

def play_again_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 Играть еще", callback_data="back_to_mods")
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    if uid not in db["players"]:
        db["players"][uid] = {"elo": 1000, "name": message.from_user.full_name, "wins": 0, "losses": 0, "in_match": False}
    
    await message.answer_photo(
        photo="https://i.yapx.ru/dffXD.jpg", 
        caption="⚔️ <b>ВЫБЕРИТЕ МОД:</b>", 
        reply_markup=mod_selection_kb(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_mods")
async def back_to_mods(callback: types.CallbackQuery):
    try:
        await callback.message.edit_caption(caption="⚔️ <b>ВЫБЕРИТЕ МОД:</b>", reply_markup=mod_selection_kb(), parse_mode="HTML")
    except:
        await callback.message.answer_photo(photo="https://i.yapx.ru/dffXD.jpg", caption="⚔️ <b>ВЫБЕРИТЕ МОД:</b>", reply_markup=mod_selection_kb(), parse_mode="HTML")
        await callback.message.delete()

@dp.callback_query(F.data.startswith("set_mod:"))
async def open_lobby(callback: types.CallbackQuery):
    mod = callback.data.split(":")[1]
    await callback.message.edit_caption(caption=f"🛰 <b>Лобби: {mod}</b>", reply_markup=lobby_menu(mod), parse_mode="HTML")

@dp.callback_query(F.data.startswith("search:"))
async def search(callback: types.CallbackQuery):
    mod, uid = callback.data.split(":")[1], callback.from_user.id
    if db["players"][uid]["in_match"]:
        return await callback.answer("Сначала закончи матч!", show_alert=True)
        
    opponent = next((e for e in db["queue"] if e["mod"] == mod and e["uid"] != uid), None)
    if opponent:
        db["queue"].remove(opponent)
        await create_match(uid, opponent["uid"], mod)
    else:
        if not any(e["uid"] == uid for e in db["queue"]): db["queue"].append({"uid": uid, "mod": mod})
        cancel_kb = InlineKeyboardBuilder()
        cancel_kb.button(text="❌ Отмена поиска", callback_data="back_to_mods")
        await callback.message.edit_caption(caption=f"🔍 <b>Поиск [{mod}]...</b>", reply_markup=cancel_kb.as_markup(), parse_mode="HTML")

async def create_match(p1, p2, mod):
    m_id = f"m_{p1}_{p2}_{int(datetime.now().timestamp())}"
    db["players"][p1]["in_match"] = db["players"][p2]["in_match"] = True
    f_map = random.choice(MAPS)
    db["matches"][m_id] = {"p1": p1, "p2": p2}
    for p_id in [p1, p2]:
        await bot.send_message(p_id, f"⚔️ <b>Матч найден!</b>\nКарта: <code>{f_map}</code>", reply_markup=match_actions(m_id, p_id==p1), parse_mode="HTML")

# --- ПРОФИЛЬ И ТОП ---
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    p = db["players"].get(callback.from_user.id)
    text = f"👤 <b>{p['name']}</b>\nРанг: {get_rank(p['elo'])}\nELO: {p['elo']}\nW/L: {p['wins']}/{p['losses']}"
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "top")
async def show_top(callback: types.CallbackQuery):
    sorted_p = sorted(db["players"].values(), key=lambda x: x['elo'], reverse=True)[:10]
    text = "🏆 <b>ТОП-10 ИГРОКОВ:</b>\n\n"
    for i, p in enumerate(sorted_p, 1):
        text += f"{i}. {p['name']} — {p['elo']}\n"
    await callback.message.answer(text, reply_markup=play_again_kb(), parse_mode="HTML")
    await callback.answer()

# --- ЛОГИКА АДМИНА И СКРИНШОТОВ ---
@dp.callback_query(F.data.startswith("action:win:"))
async def win_req(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[2])
    await state.set_state(MatchState.waiting_for_screenshot)
    await callback.message.answer("📸 Отправь скриншот победы:")

@dp.message(MatchState.waiting_for_screenshot, F.photo)
async def admin_check(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m_id = data.get('m_id')
    match = db["matches"].get(m_id)
    if not match: return

    user = message.from_user
    username = f"@{user.username}" if user.username else "нет юзернейма"
    await message.answer("⏳ Скриншот отправлен админу. Ожидай решения.")
    
    admin_caption = (
        f"🧐 <b>ПРОВЕРКА ПОБЕДЫ</b>\n\n"
        f"👤 <b>Отправитель:</b> {user.full_name} ({username})\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"⚔️ <b>Матч:</b> <code>{m_id}</code>\n"
        f"👥 <b>Игроки:</b> <code>{match['p1']}</code> vs <code>{match['p2']}</code>"
    )

    await bot.send_photo(ADMIN_CHAT_ID, photo=message.photo[-1].file_id, caption=admin_caption,
                         reply_markup=admin_decision_kb(m_id, match['p1'], match['p2']), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_res:"))
async def admin_confirm(callback: types.CallbackQuery):
    _, m_id, win_id, los_id = callback.data.split(":")
    win_id, los_id = int(win_id), int(los_id)
    
    for u, e in [(win_id, 25), (los_id, -25)]:
        db["players"][u]["elo"] += e
        db["players"][u]["in_match"] = False
        res_text = "🏆 <b>ПОБЕДА! +25 ELO</b>" if e > 0 else "💀 <b>ПОРАЖЕНИЕ. -25 ELO</b>"
        if e > 0: db["players"][u]["wins"] += 1
        else: db["players"][u]["losses"] += 1
        await bot.send_message(u, res_text, reply_markup=play_again_kb(), parse_mode="HTML")

    await callback.message.edit_caption(caption=f"✅ Матч {m_id} закрыт админом.")
    if m_id in db["matches"]: del db["matches"][m_id]

# --- КОД И РЕПОРТ ---
@dp.callback_query(F.data.startswith("action:code:"))
async def c_req(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(m_id=callback.data.split(":")[2])
    await state.set_state(MatchState.waiting_for_code)
    await callback.message.answer("🔑 Введи код лобби:")

@dp.message(MatchState.waiting_for_code)
async def c_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    m = db["matches"].get(data['m_id'])
    if m:
        target = m["p2"] if message.from_user.id == m["p1"] else m["p1"]
        await bot.send_message(target, f"🔑 Код от соперника: <code>{message.text}</code>", parse_mode="HTML")
        await message.answer("✅ Код отправлен!")
    await state.clear()

@dp.callback_query(F.data.startswith("action:report:"))
async def send_report(callback: types.CallbackQuery):
    m_id = callback.data.split(":")[2]
    await bot.send_message(ADMIN_CHAT_ID, f"🚩 <b>ЖАЛОБА</b>\nОт: {callback.from_user.id}\nМатч: {m_id}")
    await callback.answer("Жалоба отправлена", show_alert=True)

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
    
