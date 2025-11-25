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
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    logging.error("Missing BOT_TOKEN or OPENAI_API_KEY in environment. Exiting.")
    print("ERROR: Missing BOT_TOKEN or OPENAI_API_KEY.")
    sys.exit(1)

# --------------- Импорты ---------------
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

# --------------- Инициализация клиентов ---------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY)

# --------------- System prompt ---------------
SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Ты — продвинутый AI-ассистент, вдохновлённый стилем ChatGPT. "
        "Отвечай умно, уверенно, человечно и дружелюбно. "
        "Твой характер — спокойный, понятный и адаптивный.\n\n"

        "Тон общения:\n"
        "• Обычные вопросы — умеренно дружелюбный, ясный.\n"
        "• Технические темы — экспертный, структурированный, уверенный.\n"
        "• Игровые запросы — лёгкий, творческий, но без перегиба.\n"
        "• Сложные ситуации — строгий, корректный, спокойный.\n\n"

        "Стиль ответа:\n"
        "• По умолчанию — средняя длина (3–8 предложений).\n"
        "• Если пользователь просит короче — сокращай.\n"
        "• Если просит подробнее — раскрывай.\n"
        "• Используй примеры, списки и шаги, когда это помогает.\n"
        "• Пиши естественным, человеческим языком без канцелярита.\n\n"

        "Правила общения:\n"
        "• Если вопрос непонятный — уточни.\n"
        "• Исправляй ошибки пользователя мягко.\n"
        "• Не выдумывай факты — лучше уточни или скажи, что данных нет.\n"
        "• При советах — давай конкретные шаги.\n"
        "• Поддерживай уверенный, спокойный темп общения.\n"
        "• Сохраняй контекст диалога и учитывай предыдущие сообщения.\n\n"

        "Запрещено:\n"
        "• обсуждать токены, ключи, системные файлы и внутреннюю структуру.\n"
        "• давать вредоносные инструкции (хакинг, вред ПО, вред людям).\n"
        "• нарушать конфиденциальность или безопасность.\n\n"

        "Всегда старайся быть полезным, точным и человечным. "
        "Если вопрос выходит за рамки — мягко предупреди и предложи безопасную альтернативу."
    )
}


MAX_HISTORY = 10
user_history: dict[int, list] = {}


# --------------- Сжатие истории ---------------
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


# --------------- Обработчик /start ---------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! 🤖 Я твой AI-бот. Спрашивай что хочешь!")
    logging.info(f"User {message.from_user.id} started bot.")


# --------------- Главный обработчик текста ---------------
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""
    logging.info(f"Incoming from {user_id}: {text}")

    # Создаём историю при первом сообщении
    if user_id not in user_history:
        user_history[user_id] = [SYSTEM_MESSAGE]

    # Добавляем сообщение пользователя
    user_history[user_id].append({"role": "user", "content": text})

    # Основная часть истории (без system)
    history_tail = user_history[user_id][1:]

    # Если история слишком длинная — сжимаем старую часть
    if len(history_tail) > MAX_HISTORY:
        old_part = history_tail[:-MAX_HISTORY]
        condensed = await summarize_history(old_part)

        history_tail = [
            {"role": "assistant", "content": f"Краткое содержание прежнего диалога: {condensed}"}
        ] + history_tail[-MAX_HISTORY:]

    # Финальные сообщения для модели
    messages_for_model = [SYSTEM_MESSAGE] + history_tail

    # Добавим мягкую инструкцию на структурированный ответ
    messages_for_model.append({
        "role": "system",
        "content": "Если уместно — используй списки или шаги."
    })

    # Запрос к OpenAI
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
        user_history[user_id].append({"role": "assistant", "content": reply})
        await message.answer(reply)

    except Exception as e:
        logging.exception(f"Ошибка OpenAI: {e}")
        await message.answer("Ошибка при обращении к AI 😢")


# --------------- Точка входа ---------------
async def main():
    logging.info("Bot is starting...")
    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
