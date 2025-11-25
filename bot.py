import os
import sys
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from openai import OpenAI

# ----------------- Настройка логирования -----------------
logging.basicConfig(
    level=logging.INFO,
    filename="logs.txt",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ----------------- Переменные окружения -----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    logging.error("Missing BOT_TOKEN or OPENAI_API_KEY.")
    print("ERROR: Missing BOT_TOKEN or OPENAI_API_KEY.")
    sys.exit(1)

# ----------------- Инициализация -----------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------- Системное сообщение -----------------
SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Ты — продвинутый AI-ассистент, вдохновлённый стилем ChatGPT. "
        "Отвечай умно, уверенно, человечно и дружелюбно. "
        "Тон общения — адаптивный, стиль ответа — средняя длина, используй списки и шаги при необходимости. "
        "Не выдумывай факты, уточняй, если что-то непонятно. "
        "Запрещено — инструкции по взлому, ключи, конфиденциальные данные."
    )
}

# ----------------- Стили общения -----------------
MODES = {
    "standard": "Дружелюбный и ясный: отвечает понятно и мягко, подходит для повседневного общения.",
    "expert": "Экспертный: уверенный, структурированный, даёт логичные и точные объяснения.",
    "fun": "Игровой: лёгкий и творческий, иногда с юмором, без перегиба.",
    "strict": "Строгий: прямой, точный, минимальные эмоции, кратко и по делу."
}

MAX_HISTORY = 10
RATE_LIMIT_SECONDS = 1.0

user_history: dict[int, list] = {}
user_profile: dict[int, dict] = {}  # {"name": str, "mode": str}
user_last_message: dict[int, datetime] = {}

# ----------------- Inline клавиатура для выбора режима -----------------
def mode_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("1️⃣ Дружелюбный", callback_data="mode_standard"),
        InlineKeyboardButton("2️⃣ Экспертный", callback_data="mode_expert"),
        InlineKeyboardButton("3️⃣ Игровой", callback_data="mode_fun"),
        InlineKeyboardButton("4️⃣ Строгий", callback_data="mode_strict")
    )
    return keyboard

# ----------------- Сжатие истории -----------------
async def summarize_history(history: list) -> str:
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Сжать диалог в 1–2 предложения."},
                    {"role": "user", "content": str(history)}
                ]
            )
        )
        return result.choices[0].message.content
    except Exception as e:
        logging.exception(f"Ошибка сжатия истории: {e}")
        return "Пользователь ранее обсуждал разные темы."

# ----------------- Стартовое сообщение -----------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        "Привет! 🤖 Я твой AI-бот. Используй команды:\n"
        "/help — помощь\n"
        "/clear — очистить историю\n"
        "/mode — выбрать стиль общения"
    )
    if user_id not in user_profile:
        user_profile[user_id] = {"name": None, "mode": "standard"}

# ----------------- Команда /help -----------------
@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "Команды бота:\n"
        "/start — запустить бота\n"
        "/help — показать это сообщение\n"
        "/clear — очистить историю\n"
        "/mode — выбрать стиль общения\n\n"
        "После задания имени бот будет помнить ваш контекст и стиль общения."
    )

# ----------------- Команда /clear -----------------
@dp.message(Command("clear"))
async def clear_command(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
    await message.answer("✅ История очищена.")

# ----------------- Команда /mode -----------------
@dp.message(Command("mode"))
async def mode_command(message: types.Message):
    await message.answer("Выберите режим общения:", reply_markup=mode_keyboard())

# ----------------- Обработка нажатий кнопок -----------------
@dp.callback_query()
async def handle_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data.startswith("mode_"):
        selected_mode = data.split("_")[1]
        user_profile[user_id]["mode"] = selected_mode
        await callback_query.message.answer(f"Режим переключён: {MODES[selected_mode]}")

    await callback_query.answer()

# ----------------- Основной обработчик сообщений -----------------
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""

    # --- Анти-спам ---
    now = datetime.now()
    last_time = user_last_message.get(user_id)
    if last_time and (now - last_time).total_seconds() < RATE_LIMIT_SECONDS:
        await message.answer("⏳ Подожди секунду перед следующим сообщением.")
        return
    user_last_message[user_id] = now

    # --- Сбор имени пользователя ---
    if user_profile.get(user_id, {}).get("name") is None:
        user_profile[user_id]["name"] = text
        await message.answer(f"Приятно познакомиться, {text}! Теперь можешь задавать вопросы.")
        return

    # --- Инициализация истории ---
    if user_id not in user_history:
        user_history[user_id] = [SYSTEM_MESSAGE]

    user_history[user_id].append({"role": "user", "content": text})
    history_tail = user_history[user_id][1:]

    # --- Сжатие истории ---
    if len(history_tail) > MAX_HISTORY:
        old_part = history_tail[:-MAX_HISTORY]
        condensed = await summarize_history(old_part)
        history_tail = [{"role": "assistant",
                         "content": f"Краткое содержание прежнего диалога: {condensed}"}] + history_tail[-MAX_HISTORY:]

    # --- Режим общения и имя пользователя ---
    mode = user_profile.get(user_id, {}).get("mode", "standard")
    style_prompt = {"role": "system", "content": f"Текущий режим общения: {MODES[mode]}"}
    name_prompt = {"role": "system", "content": f"Имя пользователя: {user_profile[user_id]['name']}"}

    messages_for_model = [SYSTEM_MESSAGE] + [name_prompt, style_prompt] + history_tail
    messages_for_model.append({"role": "system", "content": "Если нужно — используй списки или шаги."})

    # --- Вызов OpenAI ---
    try:
        loop = asyncio.get_running_loop()
        completion = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_for_model
            )
        )
        reply = completion.choices[0].message.content
    except Exception as e:
        logging.exception(f"Ошибка OpenAI: {e}")
        reply = "⚠️ Я сейчас недоступен, попробуй позже."

    user_history[user_id].append({"role": "assistant", "content": reply})
    await message.answer(reply)

# ----------------- Глобальная обработка ошибок -----------------
@dp.errors()
async def global_error_handler(update, exception):
    user_id = getattr(update.message.from_user, "id", None)
    logging.exception(f"Global error for user {user_id}: {exception}")
    try:
        if update.message:
            await update.message.answer("⚠️ Произошла внутренняя ошибка. Я продолжаю работать!")
    except:
        pass
    return True

# ----------------- Точка входа -----------------
async def main():
    logging.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

