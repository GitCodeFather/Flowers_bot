import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

FLOWER_PRICE = 150
WRAP_PRICES = {"film": 100, "craft": 100}
DELIVERY_PRICE = 50
FREE_LIMIT = 15
ADMIN_ID = 5750590787  # ← сюда свой telegram id
FLOWER_IMAGES = {
    "Surrender": "/images/surrender.jpg",
    "Lincoln": "/images/lincoln.jpg",
    "Strong Gold": "/images/stron_gold.jpg",
    "Kamaliya": "/images/kamaliya.jpg"
}

# ======= Универсальная очистка user_data =======
def reset_user_data(context, clear_orders=False):
    """
    Сбрасывает пользовательские данные для нового заказа.

    clear_orders=False -> оставляет историю заказов
    clear_orders=True  -> полностью удаляет историю заказов
    """
    context.user_data["current_bouquet"] = {"flowers": {}, "wrap": None}

    if clear_orders:
        context.user_data["orders"] = []
    else:
        context.user_data.setdefault("orders", context.user_data.get("orders", []))

    context.user_data.pop("state", None)
    context.user_data.pop("delivery", None)
    context.user_data.pop("pickup_date", None)
    context.user_data.pop("pickup_time", None)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("💐 Мой букет", callback_data="bouquet")],
        [InlineKeyboardButton("📦 Мой заказ", callback_data="order")]
    ])


def count_flowers(flowers: dict) -> int:
    return sum(flowers.values())


def calculate_bouquet_price(flowers: dict, wrap: str | None) -> int:
    total_flowers = count_flowers(flowers)
    price = total_flowers * FLOWER_PRICE

    if total_flowers < FREE_LIMIT:
        if wrap:
            price += WRAP_PRICES[wrap]

    return price


# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) УБИРАЕМ любые старые ReplyKeyboard (очень важно)
    await update.message.reply_text("⌨️ Для перезагрузки интерфейса отправте сообщение '/start'", reply_markup=ReplyKeyboardRemove())
    context.user_data.setdefault("current_bouquet", {"flowers": {}, "wrap": None})
    context.user_data.setdefault("orders", [])

    # 2) Показываем главное меню (Inline)
    await update.message.reply_text(
        "💐 Добро пожаловать в Наш цветочный магазин! "
        "Ознакомтесь с нашими ценами и оформите свой заказ.\n\n"
        "Стоимость одного цветка - 150 р.\n"
        "Стоимость упаковки - 100 р.\n"
        "Стоимость доставки - 50 р.\n\n"
        "Внимание! При заказе от 15 цветков упаковка и доставка бесплатно.",
        reply_markup=main_menu_keyboard()
    )


def flower_card_keyboard(flower: str, qty: int):
    row = [
        InlineKeyboardButton("➕ Добавить", callback_data=f"add_{flower}_1"),
        InlineKeyboardButton("➕5 цветков", callback_data=f"add_{flower}_5"),
        InlineKeyboardButton("➕10 цветков", callback_data=f"add_{flower}_10"),
    ]

    if qty > 0:
        row.append(
            InlineKeyboardButton("➖ Убрать", callback_data=f"remove_{flower}")
        )

    keyboard = [
        row,
        [InlineKeyboardButton("💐 Добавить в Мой букет", callback_data="bouquet")],
        [InlineKeyboardButton("⬅️ Каталог", callback_data="catalog")]
    ]

    return InlineKeyboardMarkup(keyboard)


async def show_flower_card(query, context, flower: str, *, edit: bool = False):
    """
    Универсальная функция показа карточки цветка.
    edit=False -> отправляет новое сообщение
    edit=True  -> обновляет текущее сообщение
    """
    bouquet = context.user_data["current_bouquet"]["flowers"]
    qty = bouquet.get(flower, 0)

    caption = f"🌸 {flower}\nВ букете: {qty} шт"

    keyboard = flower_card_keyboard(flower, qty)

    if edit:
        media = InputMediaPhoto(
            media=open(FLOWER_IMAGES[flower], "rb"),
            caption=caption
        )
        await query.message.edit_media(
            media=media,
            reply_markup=keyboard
        )
    else:
        await query.message.reply_photo(
            photo=open(FLOWER_IMAGES[flower], "rb"),
            caption=caption,
            reply_markup=keyboard
        )
        await query.message.delete()

async def show_bouquet(query, context, *, edit: bool = True):
    bouquet = context.user_data.get("current_bouquet", {"flowers": {}, "wrap": None})
    flowers = bouquet["flowers"]
    wrap = bouquet["wrap"]

    lines = ["💐 Ваш букет:\n"]

    if not flowers:
        lines.append("Пока пусто")
    else:
        for name, qty in flowers.items():
            lines.append(f"{name}: {qty} шт")

    # --- упаковка ---
    if wrap:
        wrap_name = "Слюда" if wrap == "film" else "Крафт"
        wrap_price = WRAP_PRICES.get(wrap, 0)
        lines.append(f"\n🎁 Упаковка: {wrap_name}")
    else:
        lines.append("\n🎁 Упаковка: не выбрана")

    total_price = calculate_bouquet_price(flowers, wrap)
    lines.append(f"\n💰 Стоимость букета: {total_price} ₽")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить цветы", callback_data="catalog")],
        [InlineKeyboardButton("🎁 Упаковка слюда", callback_data="wrap_film")],
        [InlineKeyboardButton("🎁 Упаковка крафт", callback_data="wrap_craft")],
        [
            InlineKeyboardButton(
                "📦 Добавить в заказ",
                callback_data="save_bouquet"
                if flowers else "noop"   # 👈 отключаем кнопку
            )
        ],
        [InlineKeyboardButton("🗑️ Удалить букет", callback_data="clear_bouquet")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
    ])

    if edit:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# --- Обработка нажатий кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # обязательно

    # --- Главное меню ---
    if query.data == "menu":
        await query.edit_message_text("⬅️ Главное меню:", reply_markup=main_menu_keyboard())

    # --- Каталог ---
    elif query.data == "catalog":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌹 SURRENDER", callback_data="flower_Surrender")],
            [InlineKeyboardButton("🌷 LINCOLN", callback_data="flower_Lincoln")],
            [InlineKeyboardButton("🌼 STRONG GOLD", callback_data="flower_Strong Gold")],
            [InlineKeyboardButton("🌸 KAMALIYA", callback_data="flower_Kamaliya")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
        ])
        await query.message.reply_text("📋 Наш каталог:", reply_markup=keyboard)
        await query.message.delete()

    elif query.data.startswith("flower_"):
        flower = query.data.replace("flower_", "")
        await show_flower_card(query, context, flower)


    # --- Обработка добавления цветка в букет ---
    elif query.data.startswith("add_"):
        _, flower, amount = query.data.split("_")
        amount = int(amount)

        bouquet = context.user_data["current_bouquet"]["flowers"]
        bouquet[flower] = bouquet.get(flower, 0) + amount

        await show_flower_card(query, context, flower, edit=True)


    # --- Обработка удаления цветка из букета ---
    elif query.data.startswith("remove_"):
        flower = query.data.replace("remove_", "")
        bouquet = context.user_data["current_bouquet"]["flowers"]

        if flower in bouquet:
            bouquet[flower] -= 1
            if bouquet[flower] <= 0:
                del bouquet[flower]

        await show_flower_card(query, context, flower, edit=True)


    # --- Мой букет ---
    elif query.data == "bouquet":
        await show_bouquet(query, context, edit=False)
        await query.message.delete()

    # --- Обработчик очистки букета ---
    elif query.data == "clear_bouquet":
        context.user_data["current_bouquet"] = {"flowers": {}, "wrap": None}

        try: # Если вызываешь show_bouquet
            await show_bouquet(query, context, edit=True)
        except Exception as e:
            # Игнорируем ошибку, если сообщение не изменилось
            if "Message is not modified" not in str(e):
                raise

    # --- Мой заказ ---
    elif query.data == "order":
        orders = context.user_data.get("orders", [])

        if not orders:
            text = ["🛒 Заказ пуст"]
        else:
            text = ["🛒 Ваш заказ:\n"]
            total = 0
            flowers_total = 0

            for i, o in enumerate(orders, 1):
                text.append(f"{i}. Букет:")
                for name, qty in o["flowers"].items():
                    text.append(f"   • {name}: {qty} шт")
                if o["wrap"]:
                    text.append(f"   🎁 Упаковка: {'Слюда' if o['wrap'] == 'film' else 'Крафт'}")
                text.append(f"   💰 Стоимость: {o['price']} ₽\n")
                total += o["price"]
                flowers_total += o["count"]

            if flowers_total < FREE_LIMIT:
                total += DELIVERY_PRICE
                text.append(f"\n🚚 Доставка: {DELIVERY_PRICE} ₽")

            text.append(f"\n💰 Итого: {total} ₽")

        await query.edit_message_text(
            "\n".join(text),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚚 Доставка", callback_data="delivery")],
                [InlineKeyboardButton("🏠 Самовывоз", callback_data="pickup")],
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
            ])
        )


    # --- Упаковка ---
    elif query.data.startswith("wrap_"):
        wrap = query.data.replace("wrap_", "")
        context.user_data["current_bouquet"]["wrap"] = wrap

        await show_bouquet(query, context)

    # --- Сохранить букет ---
    elif query.data == "save_bouquet":
        bouquet = context.user_data["current_bouquet"]
        total_flowers = sum(bouquet["flowers"].values())
        price = calculate_bouquet_price(bouquet["flowers"], bouquet["wrap"])

        context.user_data.setdefault("orders", []).append({
            "flowers": bouquet["flowers"].copy(),
            "wrap": bouquet["wrap"],
            "price": price,
            "count": total_flowers
        })

        context.user_data["current_bouquet"] = {"flowers": {}, "wrap": None}

        await query.edit_message_text(
            f"✅ Букет добавлен в заказ\n💰 Стоимость: {price} ₽",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
                [InlineKeyboardButton("📦 Мой заказ", callback_data="order")],
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
            ])
        )

    # --- Доставка ---
    elif query.data == "delivery":
        context.user_data["delivery"] = {}
        context.user_data["state"] = "delivery_street"
        await query.edit_message_text("Введите улицу:")

    # --- Самовывоз ---
    elif query.data == "pickup":
        context.user_data["state"] = "pickup_date"
        await query.edit_message_text("Введите дату получения:")

    # --- Подтверждение доставки ---
    elif query.data == "confirm_delivery":
        await send_order_to_admin(context, query.from_user)
        reset_user_data(context, clear_orders=True)
        await query.edit_message_text(
            "Спасибо за заказ! 💐\n"
            "Ваш заказ отправлен на обработку.\n"
            "Наш администратор подтвердит заказ в личном сообщении.\n\n"
            "Вы можете оформить новый заказ:",
            reply_markup=main_menu_keyboard()
        )

    # --- Подтверждение самовывоза ---
    elif query.data == "confirm_pickup":
        await send_order_to_admin(context, query.from_user, pickup=True)
        reset_user_data(context, clear_orders=True)
        await query.edit_message_text(
            "Спасибо за заказ! 💐\n"
            "Ваш заказ отправлен на обработку.\n\n"
            "Заказ Вы сможете забрать по адресу:\n"
            "ул. Космонавтов, дом 8, подъезд 1, квартира 7.\n\n"
            "Вы можете оформить новый заказ:",
            reply_markup=main_menu_keyboard()
        )

    elif query.data == "noop":
        await query.answer("❗ Сначала добавьте цветы в букет", show_alert=True)


# ================ Обработка текста ========================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    # если бот сейчас ничего не ждёт — игнорируем текст
    if not state:
        return

    text = update.message.text

    # --- ДОСТАВКА ---
    if state.startswith("delivery_"):
        field = state.replace("delivery_", "")
        context.user_data.setdefault("delivery", {})[field] = text

        DELIVERY_FIELDS = ["street", "house", "entrance","data", "time", "name", "phone"]
        FIELD_NAMES = {
            "street": "улицу",
            "house": "дом",
            "entrance": "подъезд",
            "data": "дату доставки",
            "time": "время доставки",
            "name": "имя получателя",
            "phone": "номер телефона получателя",
        }

        next_index = DELIVERY_FIELDS.index(field) + 1

        # есть ещё поля
        if next_index < len(DELIVERY_FIELDS):
            next_field = DELIVERY_FIELDS[next_index]
            context.user_data["state"] = f"delivery_{next_field}"
            await update.message.reply_text(
                f"Введите {FIELD_NAMES[next_field]}:"
            )
        else:
            # всё введено
            context.user_data["state"] = None
            await update.message.reply_text(
                "✅ Все данные доставки получены",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚚 Оформить доставку", callback_data="confirm_delivery")]
                ])
            )

    # --- САМОВЫВОЗ ---
    elif state == "pickup_date":
        context.user_data["pickup_date"] = text
        context.user_data["state"] = "pickup_time"
        await update.message.reply_text("Введите время получения:")

    elif state == "pickup_time":
        context.user_data["pickup_time"] = text
        context.user_data["state"] = None
        await update.message.reply_text(
            "Подтвердите заказ:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Оформить заказ", callback_data="confirm_pickup")]
            ])
        )


# ==== Формирует сообщение о заказе и отправлять его админу ====
async def send_order_to_admin(context, user, pickup=False):
    """Отправка заказа админу Telegram."""

    orders = context.user_data.get("orders", [])

    if not orders:
        return  # Заказ пуст — ничего не отправляем

    total_flowers = 0
    total_price = 0
    text = [
        "📦 НОВЫЙ ЗАКАЗ",
        f"👤 Клиент: {user.full_name} (@{user.username})\n"
    ]

    # Перечисляем все букеты
    for i, o in enumerate(orders, 1):
        text.append(f"{i}. Букет:")
        for name, qty in o["flowers"].items():
            text.append(f"   • {name}: {qty} шт")
        if o["wrap"]:
            text.append(f"   🎁 Упаковка: {'Слюда' if o['wrap'] == 'film' else 'Крафт'}")
        text.append(f"   💰 Стоимость: {o['price']} ₽\n")
        total_flowers += o["count"]
        total_price += o["price"]

    # Доставка
    if not pickup and total_flowers < 15:
        total_price += 50  # доставка
        text.append(f"\n🚚 Доставка: 50 ₽")

    text.append(f"\n💰 ИТОГО: {total_price} ₽")

    # Доставка или самовывоз
    if pickup:
        text.append("\n🏠 Самовывоз")
        text.append(f"Дата: {context.user_data.get('pickup_date', '-')}")
        text.append(f"Время: {context.user_data.get('pickup_time', '-')}")
    else:
        d = context.user_data.get("delivery", {})
        text.append("\n🚚 Доставка")
        text.append(f"Улица: {d.get('street', '-')}")
        text.append(f"Дом: {d.get('house', '-')}")
        text.append(f"Подъезд: {d.get('entrance', '-')}")
        text.append(f"Имя получателя: {d.get('name', '-')}")
        text.append(f"Телефон получателя: {d.get('phone', '-')}")

    # Отправка админу
    await context.bot.send_message(chat_id=ADMIN_ID, text="\n".join(text))


# --- ЗАПУСК БОТА ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    await app.initialize()
    await app.start()

    # --- aiohttp сервер ---
    web_app = web.Application()
    web_app.router.add_post(f"/{TOKEN}", app.bot._webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    # --- регистрируем webhook ---
    await app.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")

    print("🚀 БОТ ЗАПУЩЕН (WEBHOOK)")

    # 🔥 держим процесс живым
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

