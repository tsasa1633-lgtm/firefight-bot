import os
import asyncio
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

# Список карт для Firefight
ALL_MAPS = ["🏙 City", "🌲 Forest", "🏜 Desert", "🏭 Factory", "❄️ Snow"]

# БД в памяти
queues = {"flexxy": [], "editor": []}
matches = {}      
elo_ratings = {}  
user_last_msg = {} 
veto_sessions = {} # {match_id: {"maps": [], "turn": p1, "p1": p1, "p2": p2}}

# --- СИСТЕМА FACEIT ---
def get_elo(uid):
    return elo_ratings.get(uid, 1000)

def get_lvl(elo):
    if elo < 800: return "1️⃣"
    if elo < 1100: return "3️⃣"
    if elo < 1400: return "5️⃣"
    if elo < 2000: return "9️⃣"
    return "🔟"

async def ui_update(uid, text, kb, photo=PHOTO_MAIN):
    if uid in user_last_msg:
        try: await bot.delete_message(uid, user_last_msg[uid])
        except: pass
    msg = await bot.send_photo(uid, photo=photo, caption=text, reply_markup=kb, parse_mode="Markdown")
    user_last_msg[uid] = msg.message_id

# --- КЛАВИАТУРЫ ---
def kb_game(mode, uid):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 НАЙТИ МАТЧ", callback_data=f"find_{mode}"))
    builder.row(InlineKeyboardButton(text="🏆 Я ПОБЕДИЛ", callback_data="report_win"))
    builder.row(InlineKeyboardButton(text="🏳️ Я ПРОИГРАЛ", callback_data="report_loss"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="show_mods"))
    builder.adjust(1)
    return builder.as_markup()

def kb_veto(match_id, available_maps):
    builder = InlineKeyboardBuilder()
    for m in available_maps:
        builder.row(InlineKeyboardButton(text=f"❌ Бан {m}", callback_data=f"ban_{match_id}_{m}"))
    builder.adjust(1)
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await ui_update(message.from_user.id, "⚔️ **FACEIT SYSTEM**\n\nВыбери режим:", 
                    InlineKeyboardBuilder().row(InlineKeyboardButton(text="🕹 ИГРАТЬ", callback_data="show_mods")).as_markup())

@dp.callback_query(F.data == "show_mods")
async def mods_menu(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔥 FLEXXY ХАБ", callback_data="setmode_flexxy"))
    kb.row(InlineKeyboardButton(text="🛠 EDITOR ХАБ", callback_data="setmode_editor"))
    await ui_update(call.from_user.id, "🕹 **ВЫБЕРИ ХАБ:**", kb.as_markup())

@dp.callback_query(F.data.startswith("setmode_"))
async def select_hub(call: types.CallbackQuery):
    mode = call.data.split("_")[1]
    await ui_update(call.from_user.id, f"✅ **ХАБ: {mode.upper()}**\n\nИщи матч!", kb_game(mode, call.from_user.id), PHOTO_CHOICE)

@dp.callback_query(F.data.startswith("find_"))
async def find_match(call: types.CallbackQuery):
    uid, mode = call.from_user.id, call.data.split("_")[1]
    if uid in matches or any(uid in q for q in queues.values()):
        return await call.answer("Уже в системе!")
    
    queues[mode].append(uid)
    await call.answer("🔍 Поиск...")

    if len(queues[mode]) >= 2:
        p1, p2 = queues[mode].pop(0), queues[mode].pop(0)
        match_id = f"{p1}_{p2}"
        matches[p1] = p2; matches[p2] = p1
        
        veto_sessions[match_id] = {"maps": ALL_MAPS.copy(), "turn": p1, "p1": p1, "p2": p2}
        
        await bot.send_message(p1, "🎮 **Матч найден!**\nТвоя очередь банить карту.", reply_markup=kb_veto(match_id, ALL_MAPS))
        await bot.send_message(p2, "🎮 **Матч найден!**\nОжидай, пока противник банит карты.")

# ЛОГИКА БАНА
@dp.callback_query(F.data.startswith("ban_"))
async def handle_ban(call: types.CallbackQuery):
    _, match_id, map_name = call.data.split("_")
    uid = call.from_user.id
    session = veto_sessions.get(match_id)

    if not session or uid != session["turn"]:
        return await call.answer("Сейчас не твой ход!", show_alert=True)

    session["maps"].remove(map_name)
    next_player = session["p2"] if uid == session["p1"] else session["p1"]
    session["turn"] = next_player

    if len(session["maps"]) > 1:
        # Продолжаем бан
        await bot.send_message(next_player, f"🚫 Карта `{map_name}` забанена.\nТвой черед банить!", 
                               reply_markup=kb_veto(match_id, session["maps"]))
        await call.message.edit_text(f"✅ Ты забанил {map_name}. Ожидай ход противника.")
    else:
        # Осталась одна карта
        final_map = session["maps"][0]
        p1, p2 = session["p1"], session["p2"]
        msg = f"🏁 **ВЕТО ЗАВЕРШЕНО!**\n\n🗺 Карта матча: **{final_map}**\n\nХост ({get_lvl(get_elo(p1))}): Создавай лобби!"
        await bot.send_message(p1, msg)
        await bot.send_message(p2, msg.replace("Хост", "Гость"))
        del veto_sessions[match_id]

# ФИНАЛ МАТЧА (как прежде)
async def apply_result(win_id, loss_id):
    points = 25
    elo_ratings[win_id] = get_elo(win_id) + points
    elo_ratings[loss_id] = max(0, get_elo(loss_id) - points)
    matches.pop(win_id, None); matches.pop(loss_id, None)
    await bot.send_message(win_id, f"🏆 **WIN!** New ELO: `{get_elo(win_id)}`")
    await bot.send_message(loss_id, f"💀 **LOSS!** New ELO: `{get_elo(loss_id)}`")

@dp.callback_query(F.data == "report_win")
async def report_win(call: types.CallbackQuery):
    if call.from_user.id not in matches: return
    opp = matches[call.from_user.id]
    kb = InlineKeyboardBuilder().row(InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"conf_{call.from_user.id}")).as_markup()
    await bot.send_message(opp, "⚠️ Противник нажал WIN. Подтверждаешь?", reply_markup=kb)

@dp.callback_query(F.data.startswith("conf_"))
async def confirm_res(call: types.CallbackQuery):
    w_id = int(call.data.split("_")[1])
    if call.from_user.id in matches:
        await apply_result(w_id, call.from_user.id)
        await call.message.delete()

@dp.callback_query(F.data == "report_loss")
async def report_loss(call: types.CallbackQuery):
    if call.from_user.id in matches: await apply_result(matches[call.from_user.id], call.from_user.id)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
