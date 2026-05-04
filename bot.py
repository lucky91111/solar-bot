import os
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from timezonefinder import TimezoneFinder

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Нет TELEGRAM_BOT_TOKEN")

if not OPENWEATHER_API_KEY:
    raise RuntimeError("Нет OPENWEATHER_API_KEY")


tf = TimezoneFinder()


def find_city(city_name: str):
    url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {
        "q": city_name,
        "limit": 1,
        "appid": OPENWEATHER_API_KEY,
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    if not data:
        return None

    city = data[0]

    return {
        "name": city.get("name", city_name),
        "country": city.get("country", ""),
        "lat": city["lat"],
        "lon": city["lon"],
    }


def get_times(lat: float, lon: float):
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        raise RuntimeError("Не удалось определить часовой пояс")

    utc_now = datetime.now(timezone.utc)
    local_now = utc_now.astimezone(ZoneInfo(tz_name))

    # стандартный меридиан (без DST)
    offset = local_now.utcoffset().total_seconds() / 3600
    standard_meridian = offset * 15

    solar_offset_minutes = (lon - standard_meridian) * 4
    solar_now = local_now + timedelta(minutes=solar_offset_minutes)

    return tz_name, local_now, solar_now


def get_period(solar_time: datetime):
    periods = [
        ("Час Крысы 🐭", 23),
        ("Час Быка 🐮", 1),
        ("Час Тигра 🐯", 3),
        ("Час Кролика 🐰", 5),
        ("Час Дракона 🐲", 7),
        ("Час Змеи 🐍", 9),
        ("Час Лошади 🐎", 11),
        ("Час Козы 🐐", 13),
        ("Час Обезьяны 🐒", 15),
        ("Час Петуха 🐔", 17),
        ("Час Собаки 🐶", 19),
        ("Час Свиньи 🐷", 21),
    ]

    hour = solar_time.hour

    if hour >= 23 or hour < 1:
        start = solar_time.replace(hour=23, minute=0, second=0, microsecond=0)
        if hour < 1:
            start -= timedelta(days=1)
        end = start + timedelta(hours=2)
        return "Час Крысы 🐭", start, end

    for name, h in periods[1:]:
        if h <= hour < h + 2:
            start = solar_time.replace(hour=h, minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=2)
            return name, start, end

    return periods[0][0], solar_time, solar_time + timedelta(hours=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Киев", "Лондон"],
        ["Нью-Йорк", "Варшава"],
        ["Париж", "Берлин"],
        ["Прага", "Вена"],
        ["Вильнюс", "Дубай"],
        ["Ввести свой город"],
    ]

    await update.message.reply_text(
        "☀️ Вас приветствует Бот «Солнечное время»\n\n"
        "Я ещё довольно таки Малыш, но быстро учусь.\n"
        "Сейчас я умею подбирать солнечное время для разных городов.\n\n"
        "🌿 Готов помочь.\n\n"
        "Выбери город кнопкой или напиши свой.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, is_persistent=True
        ),
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "Ввести свой город":
        await update.message.reply_text("Напиши город 🌍")
        return

    try:
        city = find_city(text)
    except Exception:
        await update.message.reply_text("Ошибка связи с сервисом городов 😔")
        return

    if not city:
        await update.message.reply_text("Не нашла город 🙈 Попробуй иначе")
        return

    try:
        tz, local_now, solar_now = get_times(city["lat"], city["lon"])
    except Exception:
        await update.message.reply_text("Ошибка расчёта времени 😔")
        return

    period_name, p_start, p_end = get_period(solar_now)

    # 🔁 перевод в локальное
    offset = local_now - solar_now
    local_start = p_start + offset
    local_end = p_end + offset

    # DST
    is_dst = bool(local_now.dst())

    if is_dst:
        dst_text = "ℹ️ Сейчас действует летнее время, поэтому локальное время сдвинуто."
    else:
        dst_text = "ℹ️ Сейчас действует стандартное время (без перевода часов)."

    await update.message.reply_text(
        f"📍 {city['name']}, {city['country']}\n"
        f"📅 Дата: {local_now.strftime('%d.%m.%Y')}\n\n"

        f"🕐 Местное время:\n{local_now.strftime('%H:%M')}\n\n"

        f"☀️ Солнечное время:\n{solar_now.strftime('%H:%M')}\n\n"

        f"🐔 Солнечный час:\n{period_name}\n\n"

        f"⏳ Период (солнечное время):\n"
        f"с {p_start.strftime('%H:%M')} до {p_end.strftime('%H:%M')}\n\n"

        f"🔁 В вашем локальном времени:\n"
        f"с {local_start.strftime('%H:%M')} до {local_end.strftime('%H:%M')}\n\n"

        f"{dst_text}\n\n"

        f"🌿 Используй это время для себя и своего Счастья"
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()


if __name__ == "__main__":
    main()
