import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup, 
                           KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройки
BOT_TOKEN = "8261117132:AAHVXMKSabbaAbB_UOfPAtp956M6fBd4QbQ"  # ← замени на свой, если нужно

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния FSM для регистрации
class Registration(StatesGroup):
    gender = State()
    name = State()
    age_group = State()
    photo = State()
    search_gender = State()
    search_age_group = State()

# Состояние для изменения возрастной группы поиска
class ChangeSearchAge(StatesGroup):
    waiting_for_age = State()

# Работа с базой данных
def init_db():
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            gender TEXT NOT NULL,
            name TEXT NOT NULL,
            age_group TEXT NOT NULL,
            photo_file_id TEXT,
            search_gender TEXT NOT NULL,
            search_age_group TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def user_exists(user_id):
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def save_user(user_id, gender, name, age_group, photo, search_gender, search_age_group):
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, gender, name, age_group, photo_file_id, search_gender, search_age_group)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, gender, name, age_group, photo, search_gender, search_age_group))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            'user_id': row[0],
            'gender': row[1],
            'name': row[2],
            'age_group': row[3],
            'photo_file_id': row[4],
            'search_gender': row[5],
            'search_age_group': row[6]
        }
    return None

def update_search_age_group(user_id, new_age_group):
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET search_age_group = ? WHERE user_id = ?', (new_age_group, user_id))
    conn.commit()
    conn.close()

def get_profiles(user_id, with_photo=True):
    """Возвращает список анкет других пользователей, подходящих под критерии поиска."""
    user = get_user(user_id)
    if not user:
        return []
    conn = sqlite3.connect('kamaz_dating.db')
    cur = conn.cursor()
    query = '''
        SELECT user_id, name, age_group, photo_file_id, gender 
        FROM users 
        WHERE user_id != ?
    '''
    params = [user_id]
    # Фильтр по полу поиска
    if user['search_gender'] != 'any':
        query += ' AND gender = ?'
        params.append(user['search_gender'])
    # Фильтр по возрастной группе поиска
    if user['search_age_group'] != 'any':
        query += ' AND age_group = ?'
        params.append(user['search_age_group'])
    # Фильтр по наличию фото
    if with_photo:
        query += ' AND photo_file_id IS NOT NULL'
    else:
        query += ' AND photo_file_id IS NULL'
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [{'user_id': r[0], 'name': r[1], 'age_group': r[2], 'photo': r[3], 'gender': r[4]} for r in rows]

# Клавиатуры
def main_menu_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Анкеты")],
            [KeyboardButton(text="🔍 Изменить возрастную группу")]
        ],
        resize_keyboard=True
    )
    return kb

def gender_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="gender_male"),
         InlineKeyboardButton(text="Женский", callback_data="gender_female")]
    ])
    return kb

def age_group_keyboard(include_any=False):
    builder = InlineKeyboardBuilder()
    groups = ["18-25", "26-35", "36-50", "50+"]
    if include_any:
        groups.append("Любой")
    for g in groups:
        builder.button(text=g, callback_data=f"age_{g}")
    builder.adjust(2)
    return builder.as_markup()

def search_gender_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="search_male"),
         InlineKeyboardButton(text="Женский", callback_data="search_female")],
        [InlineKeyboardButton(text="Любой", callback_data="search_any")]
    ])
    return kb

def photo_skip_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="photo_skip")]
    ])
    return kb

def profile_navigation_keyboard(profile_index, total_profiles, back_to_menu=True):
    builder = InlineKeyboardBuilder()
    if total_profiles > 1:
        if profile_index > 0:
            builder.button(text="◀️", callback_data="nav_prev")
        if profile_index < total_profiles - 1:
            builder.button(text="▶️", callback_data="nav_next")
    if back_to_menu:
        builder.button(text="🏠 В меню", callback_data="nav_menu")
    builder.adjust(2)
    return builder.as_markup()

def photo_filter_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 С фото", callback_data="filter_photo"),
         InlineKeyboardButton(text="🚫 Без фото", callback_data="filter_no_photo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="filter_back")]
    ])
    return kb

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_exists(user_id):
        await message.answer("Вы уже зарегистрированы.", reply_markup=main_menu_keyboard())
    else:
        await state.set_state(Registration.gender)
        await message.answer("👋 Добро пожаловать! Давай зарегистрируемся.\nВыбери свой пол:", reply_markup=gender_keyboard())

# Регистрация: пол
@dp.callback_query(StateFilter(Registration.gender), F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split("_")[1]
    await state.update_data(gender=gender)
    await state.set_state(Registration.name)
    await callback.message.edit_text("Отлично! Теперь введи своё имя (можно никнейм):")
    await callback.answer()

# Регистрация: имя
@dp.message(StateFilter(Registration.name), F.text)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Имя должно быть от 2 до 50 символов. Попробуй ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(Registration.age_group)
    await message.answer("Выбери свою возрастную группу:", reply_markup=age_group_keyboard())

# Регистрация: возрастная группа
@dp.callback_query(StateFilter(Registration.age_group), F.data.startswith("age_"))
async def process_age_group(callback: CallbackQuery, state: FSMContext):
    age_group = callback.data.split("_", 1)[1]
    await state.update_data(age_group=age_group)
    await state.set_state(Registration.photo)
    await callback.message.edit_text(
        "Можешь прикрепить фото (необязательно). Просто отправь изображение или нажми «Пропустить».",
        reply_markup=photo_skip_keyboard()
    )
    await callback.answer()

# Регистрация: фото (пропуск)
@dp.callback_query(StateFilter(Registration.photo), F.data == "photo_skip")
async def process_photo_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(Registration.search_gender)
    await callback.message.edit_text("Кого ты ищешь?", reply_markup=search_gender_keyboard())
    await callback.answer()

# Регистрация: фото (получение)
@dp.message(StateFilter(Registration.photo), F.photo)
async def process_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo=file_id)
    await state.set_state(Registration.search_gender)
    await message.answer("Кого ты ищешь?", reply_markup=search_gender_keyboard())

# Регистрация: пол для поиска
@dp.callback_query(StateFilter(Registration.search_gender), F.data.startswith("search_"))
async def process_search_gender(callback: CallbackQuery, state: FSMContext):
    search_gender = callback.data.split("_")[1]  # male, female, any
    await state.update_data(search_gender=search_gender)
    await state.set_state(Registration.search_age_group)
    await callback.message.edit_text(
        "Какую возрастную группу ты ищешь? (можно выбрать «Любой»)",
        reply_markup=age_group_keyboard(include_any=True)
    )
    await callback.answer()

# Регистрация: возрастная группа для поиска и финиш
@dp.callback_query(StateFilter(Registration.search_age_group), F.data.startswith("age_"))
async def process_search_age_group(callback: CallbackQuery, state: FSMContext):
    search_age_group = callback.data.split("_", 1)[1]
    if search_age_group == "Любой":
        search_age_group = "any"
    data = await state.get_data()
    user_id = callback.from_user.id
    save_user(
        user_id=user_id,
        gender=data['gender'],
        name=data['name'],
        age_group=data['age_group'],
        photo=data.get('photo'),
        search_gender=data['search_gender'],
        search_age_group=search_age_group
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Регистрация завершена!\n"
        f"Имя: {data['name']}\n"
        f"Твой возраст: {data['age_group']}\n"
        f"Ищешь: {data['search_gender']}, возраст {search_age_group}",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

# Главное меню: обработка кнопок
@dp.message(F.text == "📋 Анкеты")
async def show_photo_filter(message: Message):
    await message.answer("Выбери, с фото или без фото показывать анкеты:", reply_markup=photo_filter_keyboard())

@dp.message(F.text == "🔍 Изменить возрастную группу")
async def change_search_age_start(message: Message, state: FSMContext):
    await state.set_state(ChangeSearchAge.waiting_for_age)
    await message.answer(
        "Выбери новую возрастную группу для поиска:",
        reply_markup=age_group_keyboard(include_any=True)
    )

# Изменение возрастной группы поиска
@dp.callback_query(StateFilter(ChangeSearchAge.waiting_for_age), F.data.startswith("age_"))
async def process_change_age(callback: CallbackQuery, state: FSMContext):
    new_age = callback.data.split("_", 1)[1]
    if new_age == "Любой":
        new_age = "any"
    user_id = callback.from_user.id
    update_search_age_group(user_id, new_age)
    await state.clear()
    await callback.message.edit_text(f"✅ Возрастная группа для поиска изменена на {new_age}.", reply_markup=main_menu_keyboard())
    await callback.answer()

# Обработка выбора фильтра (с фото / без фото)
@dp.callback_query(F.data.startswith("filter_"))
async def process_photo_filter(callback: CallbackQuery, state: FSMContext):
    filter_type = callback.data.split("_")[1]
    if filter_type == "back":
        await callback.message.delete()
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
        await callback.answer()
        return

    with_photo = (filter_type == "photo")
    user_id = callback.from_user.id
    profiles = get_profiles(user_id, with_photo=with_photo)

    if not profiles:
        await callback.message.edit_text(
            "😕 Анкет по твоему запросу не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="filter_back")]
            ])
        )
        await callback.answer()
        return

    # Сохраняем список анкет и текущий индекс в FSM (или в памяти). Используем state для хранения временных данных.
    await state.update_data(profiles=profiles, current_index=0, filter_type=filter_type)
    await show_profile(callback.message, 0, profiles, edit=True)
    await callback.answer()

async def show_profile(message: Message, index: int, profiles: list, edit=False):
    profile = profiles[index]
    text = (
        f"📝 Анкета {index+1} из {len(profiles)}\n"
        f"👤 Имя: {profile['name']}\n"
        f"🎂 Возраст: {profile['age_group']}\n"
        f"🚻 Пол: {'Мужской' if profile['gender'] == 'male' else 'Женский'}"
    )
    keyboard = profile_navigation_keyboard(index, len(profiles))

    if profile['photo']:
        if edit:
            await message.edit_media(
                types.InputMediaPhoto(media=profile['photo'], caption=text),
                reply_markup=keyboard
            )
        else:
            await message.answer_photo(photo=profile['photo'], caption=text, reply_markup=keyboard)
    else:
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

# Навигация по анкетам
@dp.callback_query(F.data.startswith("nav_"))
async def profile_navigation(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()
    profiles = data.get('profiles')
    current = data.get('current_index', 0)
    if not profiles:
        await callback.answer("Список анкет устарел. Начни заново.", show_alert=True)
        return

    if action == "menu":
        await state.update_data(profiles=None, current_index=None)
        await callback.message.delete()
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
        await callback.answer()
        return

    if action == "prev":
        new_index = current - 1
    elif action == "next":
        new_index = current + 1
    else:
        await callback.answer()
        return

    if new_index < 0 or new_index >= len(profiles):
        await callback.answer("Нет анкет в эту сторону.")
        return

    await state.update_data(current_index=new_index)
    await show_profile(callback.message, new_index, profiles, edit=True)
    await callback.answer()

# Запуск бота
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
  if __name__ == "__main__":
    print("🚀 Бот запускается...")
    init_db()
    asyncio.run(main())
