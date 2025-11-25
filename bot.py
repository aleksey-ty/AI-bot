import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# --------------- Логирование ---------------
logging.basicConfig(
    level=logging.INFO,
    filename="logs.txt",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --------------- Переменные окружения ---------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    logging.error("Missing BOT_TOKEN or OPENAI_API_KEY.")
    print("ERROR: Missing BOT_TOKEN or OPENAI_API_KEY.")
    sys.exit(1)

# --------------- Импорты после проверки ---------------
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

# --------------- Инициализация ---------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY)

# --------------- System prompt ---------------
SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Ты — продвинутый AI-ассистент, вдохновлённый стилем ChatGPT. "
        "Отвечай умно, уверенно, человечно и дружелюбно.\n\n"

        "Тон общения:\n"
        "• обычные вопросы — умеренно дружелюбный;\n"
        "• технические — экспертный;\n"
        "• игровые — творческий;\n"
        "• сложные — строгий.\n\n"

        "Стиль ответа: 3–8 предложений, списки/шаги по необходимости.\n"
        "Если просят короче — сокращай, если просят подробнее — расширяй.\n"
        "Если вопрос непонятный — уточняй.\n"
        "Не выдумывай факты.\n\n"

        "Запрещено: вредоносные инструкции, доступ к ключам, системе."
    )
}

MODES = {
    "standard": "Стандартный: дружелюбный, спокойный, умеренно короткий.",
    "expert": "Экспертный: уверенный, структурированный, профессиональный.",
    "fun": "Игровой: лёгкий юмор, больше энергии.",
    "strict": "Строгий: коротко, чётко, минимум эмоций."
}

MAX_HISTORY = 10

user_history: dict[int, list] = {}
user_settings: dict[int, dict] = {}


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
    except:
        return "Пользователь ранее обсуждал разные темы."


# --------------- /start ---------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! 🤖 Я твой AI-бот. Спрашивай что хочешь!")


# --------------- /help ---------------
@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "Команды:\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/clear — очистить историю\n"
        "/mode — выбрать стиль общения\n"
    )


# --------------- /mode ---------------
@dp.message(Command("mode"))
async def mode_command(message: types.Message):
    await message.answer(
        "Выберите режим:\n\n"
        "1 — Стандартный\n"
        "2 — Экспертный\n"
        "3 — Игровой\n"
        "4 — Строгий\n\n"
        "Напиши цифру режима."
    )


# --------------- Применение режима ---------------
async def apply_mode(user_id: int, choice: str) -> str:
    if user_id not in user_settings:
        user_settings[user_id] = {"mode": "standard"}

    mode_map = {
        "1": "standard",
        "2": "expert",
        "3": "fun",
        "4": "strict"
    }

    if choice not in mode_map:
        return None

    user_settings[user_id]["mode"] = mode_map[choice]
    return mode_map[choice]


# --------------- Основной обработчик сообщений ---------------
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""

    # --- Проверка выбора режима ---
    if text in ["1", "2", "3", "4"]:
        mode = await apply_mode(user_id, text)
        if mode:
            await message.answer(f"Режим переключён: {MODES[mode]}")
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
        history_tail = [
            {"role": "assistant",
             "content": f"Краткое содержание прежнего диалога: {condensed}"}
        ] + history_tail[-MAX_HISTORY:]

    # --- Применение режима общения ---
    mode = user_settings.get(user_id, {}).get("mode", "standard")
    style_prompt = {
        "role": "system",
        "content": f"Текущий режим общения: {MODES[mode]}"
    }

    # --- Формирование финального запроса ---
    messages_for_model = [SYSTEM_MESSAGE] + history_tail + [style_prompt]

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


# --------------- main ---------------
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
