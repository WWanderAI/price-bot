import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Регион на Wildberries влияет на наличие и цену (параметр dest)
REGIONS = {
    "msk": ("Москва", "-1257786"),
    "spb": ("Санкт-Петербург", "-1216601"),
}

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v9/search"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def search_wb(query: str, dest: str, limit: int = 5):
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": dest,
        "query": query,
        "resultset": "catalog",
        "sort": "priceup",
        "spp": 30,
        "page": 1,
    }
    r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    products = data.get("products") or data.get("data", {}).get("products", [])

    items = []
    for p in products:
        price = None
        try:
            price = p["sizes"][0]["price"]["product"] / 100
        except Exception:
            if p.get("salePriceU"):
                price = p["salePriceU"] / 100
        if not price:
            continue
        items.append({
            "name": p.get("name", "Товар"),
            "brand": p.get("brand", ""),
            "price": price,
            "rating": p.get("reviewRating") or p.get("rating") or 0,
            "id": p["id"],
        })

    items.sort(key=lambda x: x["price"])
    return items[:limit]


def region_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(name, callback_data=f"region:{key}")
        for key, (name, _) in REGIONS.items()
    ]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("region", "msk")
    await update.message.reply_text(
        "Привет! Напиши название товара, и я найду самые дешёвые варианты.\n"
        "Регион можно сменить командой /region",
    )


async def region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери регион:", reply_markup=region_keyboard())


async def on_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.split(":")[1]
    context.user_data["region"] = key
    await q.edit_message_text(f"Регион: {REGIONS[key][0]}. Теперь пиши название товара.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    key = context.user_data.get("region", "msk")
    name, dest = REGIONS[key]
    await update.message.reply_text(f"Ищу «{query}» ({name})...")

    try:
        items = search_wb(query, dest)
    except Exception as e:
        logging.exception("search failed")
        await update.message.reply_text("Не получилось получить цены. Попробуй чуть позже.")
        return

    if not items:
        await update.message.reply_text("Ничего не нашёл. Попробуй другое название.")
        return

    lines = []
    for i, it in enumerate(items, 1):
        url = f"https://www.wildberries.ru/catalog/{it['id']}/detail.aspx"
        title = f"{it['brand']} {it['name']}".strip()[:60]
        lines.append(f"{i}. {title}\n💰 {it['price']:.0f} ₽  ⭐ {it['rating']}\n{url}")
    await update.message.reply_text(
        "Самые дешёвые на Wildberries:\n\n" + "\n\n".join(lines),
        disable_web_page_preview=True,
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("region", region))
    app.add_handler(CallbackQueryHandler(on_region, pattern="^region:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
