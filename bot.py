import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# --------------- Настройка логирования ---------------
logging.basicConfig(
    level=logging.INFO,
    filename="logs.txt",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --------------- Загрузка переменных окружения ---------------
load_dotenv()  # подгружает .env локально (на облаке переменные берутся из ENV)
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    logging.error("Missing BOT_TOKEN or OPENAI_API_KEY in environment. Exiting.")
    print("ERROR: Missing BOT_TOKEN or OPENAI_API_KEY. Проверьте .env или переменные окружения.")
    sys.exit(1)

# --------------- Импорты после проверки ключей ---------------
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

# --------------- Инициализация клиента Telegram и OpenAI ---------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY)

# --------------- Параметры поведения бота ---------------
SYSTEM_MESSAGE = {"role": "system", "content": "Ты дружелюбный AI-ассистент. Отвечай кратко и по делу."}
MAX_HISTORY = 10  # сколько последних сообщений хранить (user+assistant)

# Хранилище истории в памяти (для простоты). Для продакшена используйте БД.
user_history: dict[int, list] = {}

# --------------- Обработчик /start ---------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! 🤖 Я твой AI-бот. Задавай вопросы!")
    logging.info(f"User {message.from_user.id} started bot. username={message.from_user.username}")

# --------------- Основной обработчик сообщений ---------------
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""
    logging.info(f"Incoming from {user_id}: {text}")

    # Инициализируем историю, если нужно
    if user_id not in user_history:
        # Храним сначала системное сообщение, чтобы всегда подставлять роль бота
        user_history[user_id] = [SYSTEM_MESSAGE]

    # Добавляем нынешнее сообщение пользователя
    user_history[user_id].append({"role": "user", "content": text})

    # Обрезаем историю до последних MAX_HISTORY сообщений (помним, что system всегда в начале)
    # Храним system + последние N сообщений (user/assistant)
    # Отрезаем так, чтобы не превышать размер (учитываем системное сообщение на 0-м месте)
    history_tail = user_history[user_id][1:]  # без system
    history_tail = history_tail[-MAX_HISTORY:]
    messages_for_model = [SYSTEM_MESSAGE] + history_tail

    try:
        # Вызов OpenAI SDK может быть блокирующим — запускаем в отдельном потоке, чтобы не блокировать event loop
        loop = asyncio.get_running_loop()
        completion = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_for_model
            )
        )

        # Берём текст ответа
        reply = completion.choices[0].message.content
        # Сохраняем ответ в истории
        user_history[user_id].append({"role": "assistant", "content": reply})

        # Логируем общение (не логируем ключи и др. секреты)
        logging.info(f"Reply to {user_id}: {reply}")

        # Отвечаем пользователю
        await message.answer(reply)
    except Exception as e:
        logging.exception(f"Error when handling message from {user_id}: {e}")
        await message.answer("Произошла ошибка при обращении к AI 😢")

# --------------- Точка входа ---------------
async def main():
    logging.info("Bot is starting...")
    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Bot stopped.")

if __name__ == "__main__":
    asyncio.run(main())
