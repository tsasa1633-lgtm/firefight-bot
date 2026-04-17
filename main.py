import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Настройки ---
API_TOKEN = 'ТВОЙ_ТОКЕН_БОТА'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Состояния ---
class MatchState(StatesGroup):
    main_menu = State()     # Главное меню
    searching = State()    # Поиск матча
    map_veto = State()     # Этап бана карт
    in_game = State()      # Идет матч (кнопки Победа/Поражение)

# --- Список карт ---
ALL_MAPS = ["БАХМУТ", "АР.АНТОНОВ", "АВДЕЕВКА"]

# --- Клавиатуры ---
def get_main_menu():
    kb = [
        [InlineKeyboardButton(text="🔍 НАЙТИ МАТЧ", callback_data="find_match")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_veto_keyboard(available_maps):
    kb = [[InlineKeyboardButton(text=f"🚫 БАН: {m}", callback_data=f"ban_{m}")] for m in available_maps]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_game_results():
    kb = [
        [InlineKeyboardButton(text="🏆 Я ПОБЕДИЛ", callback_data="win")],
        [InlineKeyboardButton(text="🏳️ Я ПРОИГРАЛ (Сдаться)", callback_data="lose")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- Хэндлеры ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.set_state(MatchState.main_menu)
    await message.answer(
        "Твой LVL: 3 | ELO: 1025\n\nНажимай поиск, когда будешь готов.",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "find_match")
async def start_searching(callback: types.Callback_query, state: FSMContext):
    await state.set_state(MatchState.searching)
    await callback.message.edit_text("🔍 Поиск игроков...")
    
    # Имитация нахождения матча через 2 секунды
    await asyncio.sleep(2)
    
    # Переходим к вето
    await state.set_state(MatchState.map_veto)
    await state.update_data(remaining_maps=ALL_MAPS.copy())
    
    await callback.message.edit_text(
        "✅ Игроки найдены!\nЭтап МАП-ВЕТО. Выберите карту для БАНА:",
        reply_markup=get_veto_keyboard(ALL_MAPS)
    )

@dp.callback_query(F.data.startswith("ban_"))
async def handle_veto(callback: types.Callback_query, state: FSMContext):
    data = await state.get_data()
    maps = data.get("remaining_maps")
    banned_map = callback.data.replace("ban_", "")
    
    if banned_map in maps:
        maps.remove(banned_map)
    
    await state.update_data(remaining_maps=maps)

    # Если осталась только 1 карта — начинаем матч
    if len(maps) == 1:
        final_map = maps[0]
        await state.set_state(MatchState.in_game)
        await callback.message.edit_text(
            f"🎮 МАТЧ НАЧАТ!\n📍 Локация: **{final_map}**\n\nУдачи в бою! После завершения нажми результат:",
            parse_mode="Markdown",
            reply_markup=get_game_results()
        )
    else:
        # Если карт еще много, продолжаем банить
        await callback.message.edit_text(
            f"Карта {banned_map} забанена. Выбери следующую:",
            reply_markup=get_veto_keyboard(maps)
        )

@dp.callback_query(F.data.in_({"win", "lose"}))
async def match_result(callback: types.Callback_query, state: FSMContext):
    res = "Победа! +25 ELO" if callback.data == "win" else "Поражение. -20 ELO"
    await callback.message.edit_text(f"Результат записан: {res}")
    
    # Возвращаем в главное меню через 3 секунды
    await asyncio.sleep(3)
    await start_cmd(callback.message, state)

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
