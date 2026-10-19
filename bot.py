import asyncio
import logging
import random
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8757318199:AAH-8hN4NPx7jBRpwZOZIhjGfjJJWrovsAE"
QUESTIONS_PER_LESSON = 10
MAX_HEARTS = 3

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            xp INTEGER DEFAULT 0,
            lessons_completed INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mistakes (
            user_id INTEGER,
            level TEXT,
            question_text TEXT,
            UNIQUE(user_id, question_text)
        )
    """)
    conn.commit()
    conn.close()

def get_user_stats(user_id: int, name: str):
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
    cur.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
    conn.commit()
    cur.execute("SELECT xp, lessons_completed FROM users WHERE user_id = ?", (user_id,))
    xp, lessons = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM mistakes WHERE user_id = ?", (user_id,))
    mistakes_count = cur.fetchone()[0]
    conn.close()
    return xp, lessons, mistakes_count

def add_xp(user_id: int, earned_xp: int):
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET xp = xp + ?, lessons_completed = lessons_completed + 1 WHERE user_id = ?", (earned_xp, user_id))
    conn.commit()
    conn.close()

def save_mistake(user_id: int, level: str, question_text: str):
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO mistakes (user_id, level, question_text) VALUES (?, ?, ?)", (user_id, level, question_text))
    conn.commit()
    conn.close()

def remove_mistake(user_id: int, question_text: str):
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM mistakes WHERE user_id = ? AND question_text = ?", (user_id, question_text))
    conn.commit()
    conn.close()

def get_user_mistakes(user_id: int):
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("SELECT level, question_text FROM mistakes WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_leaderboard():
    conn = sqlite3.connect("duolingo.db")
    cur = conn.cursor()
    cur.execute("SELECT name, xp, lessons_completed FROM users ORDER BY xp DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_rank(xp: int) -> str:
    if xp < 100: return "🐣 Новичок (Beginner)"
    if xp < 300: return "📘 Ученик (Elementary)"
    if xp < 600: return "🔥 Практик (Intermediate)"
    if xp < 1000: return "🎓 Знаток (Advanced)"
    return "👑 Мастер языка (Fluent)"

# --- БАЗА ВОПРОСОВ ---
LESSONS = {
    "basics": [
        {"q": "Как переводится 'Cat'?", "en": "Cat", "options": ["Собака", "Кошка", "Птица", "Мышь"], "c": "Кошка", "exp": "Cat — кошка, Dog — собака."},
        {"q": "Перевод слова 'Always'", "en": "Always", "options": ["Иногда", "Никогда", "Всегда", "Часто"], "c": "Всегда", "exp": "Always = всегда, Never = никогда."},
        {"q": "Как переводится 'Apple'?", "en": "Apple", "options": ["Яблоко", "Апельсин", "Банан", "Груша"], "c": "Яблоко", "exp": "Apple — яблоко."},
        {"q": "Выберите перевод: 'Hello'", "en": "Hello", "options": ["Пока", "Привет", "Спасибо", "Извини"], "c": "Привет", "exp": "Hello — стандартное приветствие."},
        {"q": "Как переводится 'Book'?", "en": "Book", "options": ["Тетрадь", "Книга", "Журнал", "Ручка"], "c": "Книга", "exp": "Book — книга."},
        {"q": "Перевод слова 'Water'", "en": "Water", "options": ["Огонь", "Земля", "Вода", "Воздух"], "c": "Вода", "exp": "Water — вода, Fire — огонь."},
        {"q": "Как переводится 'House'?", "en": "House", "options": ["Машина", "Дерево", "Дом", "Улица"], "c": "Дом", "exp": "House — дом, здание."},
        {"q": "Перевод слова 'Sun'", "en": "Sun", "options": ["Луна", "Звезда", "Солнце", "Небо"], "c": "Солнце", "exp": "Sun — солнце, Moon — луна."},
        {"q": "Как переводится 'Friend'?", "en": "Friend", "options": ["Враг", "Друг", "Брат", "Сосед"], "c": "Друг", "exp": "Best friend — лучший друг."},
        {"q": "Перевод слова 'Time'", "en": "Time", "options": ["Деньги", "Время", "Часы", "День"], "c": "Время", "exp": "What time is it? — Который час?"},
        {"q": "Как переводится 'Car'?", "en": "Car", "options": ["Автобус", "Самолет", "Машина", "Поезд"], "c": "Машина", "exp": "Car — легковой автомобиль."},
        {"q": "Перевод слова 'Money'", "en": "Money", "options": ["Работа", "Деньги", "Кошелек", "Банк"], "c": "Деньги", "exp": "Time is money — время-деньги."},
        {"q": "Как переводится 'Good'?", "en": "Good", "options": ["Плохой", "Хороший", "Быстрый", "Новый"], "c": "Хороший", "exp": "Good — хороший, Bad — плохой."},
        {"q": "Перевод слова 'Night'", "en": "Night", "options": ["Утро", "День", "Вечер", "Ночь"], "c": "Ночь", "exp": "Good night — спокойной ночи."},
        {"q": "Как переводится 'Tree'?", "en": "Tree", "options": ["Цветок", "Трава", "Дерево", "Лес"], "c": "Дерево", "exp": "Tree — дерево, Three — цифра три."}
    ],
    "intermediate": [
        {"q": "Вставьте слово: 'I ___ a doctor.'", "en": "I am a doctor", "options": ["am", "is", "are", "be"], "c": "am", "exp": "С местоимением 'I' всегда используется 'am'."},
        {"q": "Как переводится 'Environment'?", "en": "Environment", "options": ["Окружающая среда", "Правительство", "Развитие", "Общество"], "c": "Окружающая среда", "exp": "Environment — природа, окружающая среда."},
        {"q": "Прошедшее время глагола 'Go'", "en": "Went", "options": ["Goes", "Gone", "Went", "Going"], "c": "Went", "exp": "Неправильный глагол: Go -> Went -> Gone."},
        {"q": "Перевод фразы 'It depends on you'", "en": "It depends on you", "options": ["Это зависит от тебя", "Это для тебя", "Это из-за тебя", "Это твое"], "c": "Это зависит от тебя", "exp": "Depend on — зависеть от кого-то."},
        {"q": "Синоним к слову 'Fast'", "en": "Quick", "options": ["Slow", "Quick", "Heavy", "Hard"], "c": "Quick", "exp": "Fast и Quick означают «быстрый»."},
        {"q": "Вставьте слово: 'She ___ playing tennis now.'", "en": "She is playing tennis now", "options": ["is", "are", "am", "does"], "c": "is", "exp": "В Present Continuous с She используется 'is'."},
        {"q": "Как переводится 'Opportunity'?", "en": "Opportunity", "options": ["Проблема", "Возможность", "Обязанность", "Решение"], "c": "Возможность", "exp": "Opportunity — благоприятная возможность, шанс."},
        {"q": "Вставьте предлог: 'I am interested ___ music.'", "en": "I am interested in music", "options": ["in", "on", "at", "for"], "c": "in", "exp": "Устойчивое выражение: interested IN."},
        {"q": "Прошедшее время глагола 'Buy'", "en": "Bought", "options": ["Buyed", "Bought", "Brought", "Begun"], "c": "Bought", "exp": "Buy (покупать) -> Bought."},
        {"q": "Как переводится 'Experience'?", "en": "Experience", "options": ["Эксперимент", "Опыт", "Экзамен", "Эксперт"], "c": "Опыт", "exp": "Work experience — опыт работы."},
        {"q": "Вставьте слово: 'Have you ___ been to London?'", "en": "Have you ever been to London", "options": ["ever", "never", "yet", "already"], "c": "ever", "exp": "В вопросах о жизненном опыте ставится 'ever'."},
        {"q": "Перевод слова 'Decision'", "en": "Decision", "options": ["Обсуждение", "Решение", "Деление", "Сомнение"], "c": "Решение", "exp": "Make a decision — принять решение."},
        {"q": "Какой предлог нужен: 'Wait ___ me!'", "en": "Wait for me", "options": ["for", "to", "on", "at"], "c": "for", "exp": "Ждать кого-то — всегда Wait FOR."},
        {"q": "Как переводится 'To improve'?", "en": "To improve", "options": ["Ухудшать", "Доказывать", "Улучшать", "Проверять"], "c": "Улучшать", "exp": "Improve — улучшать."},
        {"q": "Вставьте слово: 'There aren't ___ apples left.'", "en": "There are not many apples left", "options": ["much", "many", "some", "a lot"], "c": "many", "exp": "Яблоки исчисляемые, поэтому 'many'."}
    ],
    "advanced": [
        {"q": "Что значит идиома 'Piece of cake'?", "en": "It is a piece of cake", "options": ["Кусок торта", "Проще простого", "Сложная задача", "Приятный сюрприз"], "c": "Проще простого", "exp": "Piece of cake — очень легкое дело."},
        {"q": "Вставьте слово: 'By the time you arrive, I ___ finished.'", "en": "By the time you arrive I will have finished", "options": ["will have", "have", "had", "will"], "c": "will have", "exp": "Future Perfect: will have + V3."},
        {"q": "Синоним к слову 'Ubiquitous'", "en": "Ubiquitous", "options": ["Rare", "Omnipresent", "Hidden", "Expensive"], "c": "Omnipresent", "exp": "Оба слова означают «вездесущий, повсеместный»."},
        {"q": "Что значит 'To play devil's advocate'?", "en": "To play devils advocate", "options": ["Спорить ради проверки аргументов", "Быть злым", "Защищать виновного", "Сдаться"], "c": "Спорить ради проверки аргументов", "exp": "Специально приводить контраргументы в споре."},
        {"q": "Значение слова 'Procrastination'", "en": "Procrastination", "options": ["Ускорение", "Откладывание дел на потом", "Достижение цели", "Усталость"], "c": "Откладывание дел на потом", "exp": "Привычка откладывать важные дела."},
        {"q": "Что значит идиома 'Break a leg'?", "en": "Break a leg", "options": ["Сломай ногу", "Ни пуха ни пера", "Беги быстрее", "Остановись"], "c": "Ни пуха ни пера", "exp": "Пожелание удачи перед выступлением."},
        {"q": "Вставьте слово: 'If I ___ known, I would have told you.'", "en": "If I had known I would have told you", "options": ["had", "have", "would", "did"], "c": "had", "exp": "3-й тип условных предложений: If + had V3."},
        {"q": "Как переводится 'Inevitable'?", "en": "Inevitable", "options": ["Невидимый", "Неизбежный", "Невероятный", "Невозможный"], "c": "Неизбежный", "exp": "Inevitable — неминуемый, неизбежный."},
        {"q": "Что значит 'To hit the nail on the head'?", "en": "Hit the nail on the head", "options": ["Попасть в самую точку", "Пораниться", "Сделать ошибку", "Работать руками"], "c": "Попасть в самую точку", "exp": "Сказать абсолютно точно."},
        {"q": "Перевод слова 'Ambiguous'", "en": "Ambiguous", "options": ["Амбициозный", "Двусмысленный", "Очевидный", "Огромный"], "c": "Двусмысленный", "exp": "Ambiguous — неоднозначный, двусмысленный."},
        {"q": "Что значит идиома 'Under the weather'?", "en": "I feel under the weather", "options": ["Под дождем", "Плохо себя чувствовать", "В хорошем настроении", "На улице"], "c": "Плохо себя чувствовать", "exp": "Feel under the weather — приболеть."},
        {"q": "Вставьте слово: 'Rarely ___ we see such talent.'", "en": "Rarely do we see such talent", "options": ["do", "are", "have", "is"], "c": "do", "exp": "Инверсия после Rarely требует вспомогательного глагола do."},
        {"q": "Как переводится 'Consequence'?", "en": "Consequence", "options": ["Последовательность", "Последствие", "Совесть", "Совпадение"], "c": "Последствие", "exp": "Consequence — последствие."},
        {"q": "Что значит 'Once in a blue moon'?", "en": "Once in a blue moon", "options": ["Каждую ночь", "Очень редко", "В полнолуние", "Никогда"], "c": "Очень редко", "exp": "Аналог выражения «раз в сто лет»."},
        {"q": "Перевод слова 'Resilient'", "en": "Resilient", "options": ["Жизнестойкий", "Хрупкий", "Резиновый", "Тихий"], "c": "Жизнестойкий", "exp": "Способный быстро восстанавливаться."}
    ]
}

class LessonState(StatesGroup):
    in_lesson = State()

def main_menu_kb(mistakes_count: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 Легкий (Микс заданий)", callback_data="lesson_basics")
    builder.button(text="🟡 Средний (Микс заданий)", callback_data="lesson_intermediate")
    builder.button(text="🔴 Сложный (Микс заданий)", callback_data="lesson_advanced")
    builder.button(text="⌨️ Письменный тренажер", callback_data="lesson_typing")
    if mistakes_count > 0:
        builder.button(text=f"🛠 Работа над ошибками ({mistakes_count})", callback_data="lesson_mistakes")
    builder.button(text="👤 Мой профиль", callback_data="profile")
    builder.button(text="🏆 Топ игроков", callback_data="leaderboard")
    builder.adjust(1, 1, 1, 1, 1 if mistakes_count > 0 else 2, 2)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    xp, lessons, mistakes_count = get_user_stats(message.from_user.id, message.from_user.first_name)
    rank = get_rank(xp)
    await message.answer(
        f"Привет, {message.from_user.first_name}! 🦉\n\n"
        f"Звание: {rank}\n"
        f"🌟 Опыт: {xp} XP | 📚 Уроков: {lessons}\n\n"
        f"Выбери режим тренировки (на урок дается {MAX_HEARTS} ❤️):",
        reply_markup=main_menu_kb(mistakes_count)
    )

@dp.callback_query(F.data == "menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    xp, lessons, mistakes_count = get_user_stats(callback.from_user.id, callback.from_user.first_name)
    rank = get_rank(xp)
    await callback.message.answer(
        f"🏠 Главное меню\n\n"
        f"Звание: {rank}\n"
        f"🌟 Опыт: {xp} XP | 📚 Уроков: {lessons}\n\n"
        f"Выбери тренировку:",
        reply_markup=main_menu_kb(mistakes_count)
    )
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    xp, lessons, mistakes_count = get_user_stats(callback.from_user.id, callback.from_user.first_name)
    rank = get_rank(xp)
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="menu")
    await callback.message.answer(
        f"👤 Профиль игрока: {callback.from_user.first_name}\n\n"
        f"🏅 Звание: {rank}\n"
        f"🌟 Всего опыта: {xp} XP\n"
        f"📚 Пройдено уроков: {lessons}\n"
        f"❗️ Вопросов на повторение: {mistakes_count}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    leaders = get_leaderboard()
    text = "🏆 Топ-10 игроков по опыту (XP):\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, (name, xp, lessons) in enumerate(leaders):
        icon = medals[idx] if idx < 3 else f"{idx + 1}."
        text += f"{icon} {name} — {xp} XP ({lessons} ур.)\n"
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="menu")
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("lesson_"))
async def start_lesson(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if mode == "mistakes":
        saved = get_user_mistakes(user_id)
        if not saved:
            await callback.answer("У тебя нет ошибок для повторения!", show_alert=True)
            return
        pool = []
        for lvl, q_text in saved:
            for item in LESSONS.get(lvl, []):
                if item["q"] == q_text:
                    c_item = item.copy()
                    c_item["lvl"] = lvl
                    c_item["q_type"] = "choice"
                    pool.append(c_item)
        selected_questions = random.sample(pool, min(QUESTIONS_PER_LESSON, len(pool)))
    elif mode == "typing":
        all_items = []
        for lvl in ["basics", "intermediate"]:
            for item in LESSONS[lvl]:
                c_item = item.copy()
                c_item["lvl"] = lvl
                c_item["q_type"] = "typing"
                all_items.append(c_item)
        selected_questions = random.sample(all_items, min(QUESTIONS_PER_LESSON, len(all_items)))
    else:
        pool = []
        for item in LESSONS[mode]:
            c_item = item.copy()
            c_item["lvl"] = mode
            pool.append(c_item)
        selected_questions = random.sample(pool, min(QUESTIONS_PER_LESSON, len(pool)))
        for idx, q in enumerate(selected_questions):
            if idx % 2 == 1:
                q["q_type"] = "typing"
            else:
                q["q_type"] = "choice"

    await state.set_state(LessonState.in_lesson)
    await state.update_data(
        user_id=user_id,
        mode=mode,
        question_index=0,
        score=0,
        hearts=MAX_HEARTS,
        current_questions=selected_questions
    )
    await callback.message.answer(f"🎯 Тренировка началась! У тебя {MAX_HEARTS} ❤️.")
    await send_question(callback.message, state)
    await callback.answer()

async def send_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_index = data["question_index"]
    questions = data["current_questions"]
    hearts = data["hearts"]
    score = data["score"]

    if hearts <= 0:
        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 В главное меню", callback_data="menu")
        await message.answer(
            f"💔 У тебя закончились жизни!\n"
            f"Правильных ответов: {score}.\nВсе ошибки сохранены в «Работу над ошибками».",
            reply_markup=builder.as_markup()
        )
        await state.clear()
        return

    if q_index >= len(questions):
        user_id = data.get("user_id")
        earned_xp = score * 15 + (hearts * 5)
        if user_id:
            add_xp(user_id, earned_xp)
        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 В главное меню", callback_data="menu")
        await message.answer(
            f"🎉 Урок успешно пройден!\n\n"
            f"✅ Правильных ответов: {score} из {len(questions)}\n"
            f"❤️ Бонус за жизни: +{hearts * 5} XP\n"
            f"🌟 Всего начислено: +{earned_xp} XP!",
            reply_markup=builder.as_markup()
        )
        await state.clear()
        return

    q_data = questions[q_index]
    q_type = q_data.get("q_type", "choice")
    hearts_display = "❤️" * hearts + "🖤" * (MAX_HEARTS - hearts)

    if q_type == "typing":
        builder = InlineKeyboardBuilder()
        builder.button(text="💡 Показать варианты (сдаться)", callback_data="force_choice")
        builder.adjust(1)

        if len(q_data["en"].split()) == 1 and q_data["c"] != q_data["en"]:
            prompt_text = (
                f"Вопрос {q_index + 1} из {len(questions)}   [{hearts_display}]\n\n"
                f"⌨️ **Напиши по-английски с клавиатуры:**\n"
                f"👉 «{q_data['c']}»"
            )
            await state.update_data(expected_text=q_data["en"])
        else:
            prompt_text = (
                f"Вопрос {q_index + 1} из {len(questions)}   [{hearts_display}]\n\n"
                f"⌨️ **Напиши правильный ответ в чат:**\n"
                f"🇬🇧 {q_data['q']}"
            )
            await state.update_data(expected_text=q_data["c"])

        await message.answer(prompt_text, reply_markup=builder.as_markup())
        return

    builder = InlineKeyboardBuilder()
    indexed_options = list(enumerate(q_data["options"]))
    random.shuffle(indexed_options)

    for idx, option in indexed_options:
        builder.button(text=option, callback_data=f"ans_{idx}")
    builder.adjust(2)

    await message.answer(
        f"Вопрос {q_index + 1} из {len(questions)}   [{hearts_display}]\n\n"
        f"🇬🇧 {q_data['q']}",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "force_choice", LessonState.in_lesson)
async def force_choice_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data["current_questions"]
    q_index = data["question_index"]
    questions[q_index]["q_type"] = "choice"
    await state.update_data(current_questions=questions)
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_question(callback.message, state)
    await callback.answer()

@dp.message(LessonState.in_lesson, F.text)
async def check_text_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_index = data["question_index"]
    questions = data["current_questions"]
    q_data = questions[q_index]

    if q_data.get("q_type") != "typing":
        await message.answer("👆 Нажми на одну из кнопок выше!")
        return

    user_input = message.text.strip().lower().rstrip(".!?")
    expected = data.get("expected_text", q_data["c"]).strip().lower().rstrip(".!?")
    alt_expected = q_data["c"].strip().lower().rstrip(".!?")

    score = data["score"]
    hearts = data["hearts"]
    explanation = q_data.get("exp", "")

    if user_input == expected or user_input == alt_expected:
        score += 1
        await message.answer(f"✅ Блестяще! Верно: **{data.get('expected_text')}**")
    else:
        hearts -= 1
        save_mistake(message.from_user.id, q_data.get("lvl", "basics"), q_data["q"])
        await message.answer(
            f"❌ Ошибка! -1 ❤️\n"
            f"Правильный ответ: **{data.get('expected_text')}**\n"
            f"💡 Подсказка: {explanation}"
        )

    await state.update_data(question_index=q_index + 1, score=score, hearts=hearts)
    await send_question(message, state)

@dp.callback_query(F.data.startswith("ans_"), LessonState.in_lesson)
async def check_button_answer(callback: types.CallbackQuery, state: FSMContext):
    selected_idx = int(callback.data.split("_")[1])
    data = await state.get_data()
    q_index = data["question_index"]
    questions = data["current_questions"]
    score = data["score"]
    hearts = data["hearts"]
    mode = data["mode"]

    q_data = questions[q_index]
    selected_text = q_data["options"][selected_idx]
    correct = q_data["c"]
    explanation = q_data.get("exp", "")

    if selected_text == correct:
        score += 1
        if mode == "mistakes":
            remove_mistake(callback.from_user.id, q_data["q"])
            await callback.message.answer("✅ Верно! Ошибка исправлена и удалена из списка.")
        else:
            await callback.message.answer("✅ Верно!")
    else:
        hearts -= 1
        save_mistake(callback.from_user.id, q_data.get("lvl", "basics"), q_data["q"])
        await callback.message.answer(
            f"❌ Ошибка! -1 ❤️\n"
            f"Правильный ответ: {correct}\n"
            f"💡 Подсказка: {explanation}"
        )

    await state.update_data(
        user_id=callback.from_user.id,
        question_index=q_index + 1,
        score=score,
        hearts=hearts
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_question(callback.message, state)
    await callback.answer()

async def main():
    init_db()
    # Регистрируем кнопку /start в системном меню Telegram
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Главное меню / Запустить бота")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())