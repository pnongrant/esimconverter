import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart

# Вставьте сюда токен вашего бота от @BotFather
BOT_TOKEN = "8964600919:AAGPxX1MB4zX36t9A-_suTPneeYRP75Wo-g"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Перешли мне сообщение из бота с QR-кодами "
        "(или просто скопируй и отправь текст со списком номеров), "
        "и я преобразую его в нужный формат:\n\n"
        "<code>79147388510 *КОД АКТИВАЦИИ ESIM*</code>",
        parse_mode="HTML"
    )


@dp.message(F.text)
async def format_numbers(message: Message):
    text = message.text or message.caption or ""
    
    # Ищем все номера вида: "1. 79147388510" или просто "79147388510"
    # Берём номера из 11 цифр (российские) или похожих длин
    pattern = r'\b(\d{10,15})\b'
    numbers = re.findall(pattern, text)
    
    # Фильтруем — оставляем только те, что похожи на телефонные номера (начинаются с 7)
    # Если у вас могут быть другие — уберите фильтр
    phone_numbers = [n for n in numbers if len(n) == 11 and n.startswith('7')]
    
    if not phone_numbers:
        await message.answer("❌ Не нашёл номеров в сообщении. Проверь формат.")
        return
    
    # Формируем результат
    result_lines = [f"{num} *КОД АКТИВАЦИИ ESIM*" for num in phone_numbers]
    result = "\n".join(result_lines)
    
    # Telegram ограничивает сообщение в 4096 символов — разбиваем при необходимости
    if len(result) <= 4000:
        await message.answer(result)
    else:
        # Разбиваем по строкам
        chunk = ""
        for line in result_lines:
            if len(chunk) + len(line) + 1 > 4000:
                await message.answer(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk:
            await message.answer(chunk)
    
    await message.answer(f"✅ Обработано номеров: {len(phone_numbers)}")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
