import asyncio
import logging
import re
import io
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode as qr_decode
from PIL import Image

# === НАСТРОЙКИ ===
BOT_TOKEN = "8964600919:AAGPxX1MB4zX36t9A-_suTPneeYRP75Wo-g"

# Если poppler не в PATH (Windows) — укажи путь к папке bin:
# POPPLER_PATH = r"C:\poppler-24.02.0\Library\bin"
POPPLER_PATH = None  # None = искать в PATH

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def extract_phone_numbers_ordered(text: str) -> list[str]:
    """Извлекает номера из текста в исходном порядке."""
    pattern = r'\b(7\d{10})\b'
    numbers = re.findall(pattern, text)
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    result = []
    for n in numbers:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def parse_lpa(lpa_string: str) -> tuple[str, str] | None:
    """
    Парсит строку вида: LPA:1$ESIM.MTS.RU$OU4B4-93XCT-PECUN-EXPIQ
    Возвращает: ('ESIM.MTS.RU', 'OU4B4-93XCT-PECUN-EXPIQ')
    """
    # Убираем префикс LPA:1$ если есть
    s = lpa_string.strip()
    if s.upper().startswith("LPA:"):
        s = s[4:]
    # Теперь: 1$ESIM.MTS.RU$OU4B4-93XCT-PECUN-EXPIQ
    parts = s.split("$")
    if len(parts) >= 3:
        smdp = parts[1].strip()
        code = parts[2].strip()
        return smdp, code
    # Если формат другой — вернём как есть в коде
    return None


def extract_qr_codes_from_pdf(pdf_bytes: bytes) -> list[str]:
    """
    Конвертирует каждую страницу PDF в картинку и сканирует QR-код.
    Возвращает список строк (по одной на страницу).
    Если на странице QR не распознан — добавляет пустую строку.
    """
    # DPI повыше для лучшего распознавания
    images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH)
    
    qr_results = []
    for i, image in enumerate(images, start=1):
        decoded = qr_decode(image)
        if decoded:
            # Берём первый найденный QR на странице
            data = decoded[0].data.decode("utf-8", errors="ignore")
            qr_results.append(data)
            logging.info(f"Стр. {i}: QR найден → {data}")
        else:
            qr_results.append("")
            logging.warning(f"Стр. {i}: QR не распознан")
    
    return qr_results


async def process_pdf(message: Message, pdf_bytes: bytes, caption_text: str = ""):
    """Основная обработка PDF."""
    await message.answer("📄 Сканирую QR-коды на страницах PDF... Это может занять немного времени.")
    
    try:
        # 1. Извлекаем QR-коды постранично
        qr_list = await asyncio.to_thread(extract_qr_codes_from_pdf, pdf_bytes)
    except Exception as e:
        logging.exception("Ошибка сканирования PDF")
        await message.answer(
            f"❌ Ошибка при сканировании PDF:\n<code>{e}</code>\n\n"
            f"Проверь, что установлены <b>poppler</b> и <b>zbar</b>.",
            parse_mode="HTML"
        )
        return
    
    # 2. Достаём список номеров из подписи к файлу (она содержит "Выдано 10 QR: 1. ...")
    numbers = extract_phone_numbers_ordered(caption_text)
    
    if not numbers:
        await message.answer(
            "⚠️ В подписи к PDF не найден список номеров.\n"
            "Перешли сообщение целиком (с текстом и файлом)."
        )
        return
    
    if len(numbers) != len(qr_list):
        await message.answer(
            f"⚠️ Внимание: номеров в тексте — <b>{len(numbers)}</b>, "
            f"страниц с QR — <b>{len(qr_list)}</b>. "
            f"Связь по порядку может быть неточной.",
            parse_mode="HTML"
        )
    
    # 3. Формируем результат: номер ↔ QR по порядку
    result_lines = []
    unmatched = 0
    for i, number in enumerate(numbers):
        qr_data = qr_list[i] if i < len(qr_list) else ""
        if not qr_data:
            result_lines.append(f"{number} ❌ QR не распознан")
            unmatched += 1
            continue
        
        parsed = parse_lpa(qr_data)
        if parsed:
            smdp, code = parsed
            result_lines.append(f"{number} {smdp} {code}")
        else:
            # Если формат не LPA — выводим как есть
            result_lines.append(f"{number} {qr_data}")
    
    # 4. Отправляем результат (разбивая длинные сообщения)
    chunk = ""
    for line in result_lines:
        if len(chunk) + len(line) + 1 > 4000:
            await message.answer(chunk.strip())
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk.strip())
    
    summary = f"✅ Готово: {len(result_lines)} строк"
    if unmatched:
        summary += f"\n⚠️ Не распознано QR: {unmatched}"
    await message.answer(summary)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Перешли мне сообщение из бота с QR-кодами (с прикреплённым PDF), "
        "и я выдам список вида:\n\n"
        "<code>79147388424 ESIM.MTS.RU OU4B4-93XCT-PECUN-EXPIQ</code>\n\n"
        "📌 Важно: пересылай <b>именно сообщение с файлом и текстом</b> "
        "(чтобы было видно и PDF, и список номеров под ним).",
        parse_mode="HTML"
    )


@dp.message(F.document)
async def pdf_handler(message: Message):
    document = message.document
    
    if not (document.file_name and document.file_name.lower().endswith('.pdf')):
        await message.answer("❌ Жду PDF-файл.")
        return
    
    try:
        file = await bot.get_file(document.file_id)
        file_bytes_io = await bot.download_file(file.file_path)
        pdf_bytes = file_bytes_io.read()
    except Exception as e:
        await message.answer(f"❌ Не удалось скачать файл: <code>{e}</code>", parse_mode="HTML")
        return
    
    caption = message.caption or ""
    await process_pdf(message, pdf_bytes, caption)


@dp.message(F.text)
async def text_handler(message: Message):
    await message.answer(
        "ℹ️ Чтобы я смог достать данные из QR — мне нужен <b>PDF-файл</b>.\n"
        "Перешли сообщение с прикреплённым PDF.",
        parse_mode="HTML"
    )


@dp.message()
async def fallback(message: Message):
    await message.answer("🤔 Перешли сообщение с PDF-файлом из бота с QR-кодами.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
