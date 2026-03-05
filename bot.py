import asyncio
import os
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest

async def safe_edit(query, text, keyboard=None, parse_mode=None):
    try:
        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode=parse_mode
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

FLOWER_PRICE = 150
WRAP_PRICES = {"film": 100, "craft": 100}
DELIVERY_PRICE = 50
FREE_LIMIT = 15
ADMIN_ID = 5750590787  # ← сюда свой telegram id
FLOWER_IMAGES = {
    "Surrender": "AgACAgIAAxkBAAICJGmlj-5RodQMcOBYfzQQ5umWFqEEAAI5FWsbw8cpSS39kv5wUo5JAQADAgADbQADOgQ",
    # "Lincoln": "AgACAgIAAxkBAAICJmmlkBs30EuPXBg5YNZ3288ShsVeAAJxF2sbgfAxSS52dZiDYVbPAQADAgADbQADOgQ",
    "Strong Gold": "AgACAgIAAxkBAAICKGmlkDNJ1H23SWquaAfC7N3Ot5OMAAJyF2sbgfAxSQljcbCl5BEsAQADAgADeAADOgQ",
    "Kamaliya": "AgACAgIAAxkBAAICKmmlkFT4Aw_rzOxxQT7-tJ0E06_-AAJ0F2sbgfAxSQ5Pde3GbijRAQADAgADbQADOgQ"
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
    if wrap:
        # Если цветов МЕНЬШЕ лимита — платим за упаковку
        if total_flowers < FREE_LIMIT:
            price += WRAP_PRICES[wrap]
        # Если цветов 15 и больше — упаковка прибавляет 0 к цене (бесплатно)
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
        "Внимание! При заказе от 15 цветков упаковка бесплатно.",
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
    Использует file_id вместо локальных файлов.
    """
    # 1. Получаем данные о букете
    bouquet = context.user_data.get("current_bouquet", {}).get("flowers", {})
    qty = bouquet.get(flower, 0)

    caption = f"🌸 {flower}\nВ букете: {qty} шт"
    keyboard = flower_card_keyboard(flower, qty)

    # 2. Берем ID фото из словаря (без open!)
    # ВАЖНО: Ключ в FLOWER_IMAGES должен СОВПАДАТЬ с переменной flower (регистр важен!)
    photo_id = FLOWER_IMAGES.get(flower)

    if not photo_id:
        print(f"❌ ОШИБКА: Ключ '{flower}' не найден в FLOWER_IMAGES")
        await query.answer("Фото не найдено")
        return

    if edit:
        # Для обновления сообщения используем InputMediaPhoto со строкой-ID
        media = InputMediaPhoto(
            media=photo_id, # Просто строка ID
            caption=caption
        )
        await query.message.edit_media(
            media=media,
            reply_markup=keyboard
        )
    else:
        # Для нового сообщения просто передаем ID в photo
        await query.message.reply_photo(
            photo=photo_id, # Просто строка ID
            caption=caption,
            reply_markup=keyboard
        )
        # Удаляем предыдущее сообщение (необязательно, если это вызывает ошибки)
        try:
            await query.message.delete()
        except:
            pass

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
        total_flowers = count_flowers(flowers)

        # Визуально показываем, что упаковка бесплатная
        if total_flowers >= FREE_LIMIT:
            lines.append(f"\n🎁 Упаковка: {wrap_name} (Бесплатно! 🔥)")
        else:
            lines.append(f"\n🎁 Упаковка: {wrap_name} (+{WRAP_PRICES[wrap]} ₽)")
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

    text_content = "\n".join(lines)
    if edit:
        # Если в сообщении есть ФОТО (переход из карточки цветка)
        if query.message.photo:
            try:
                await query.message.delete()
            except:
                pass
            # Шлем НОВОЕ текстовое сообщение (один раз при переходе от фото к тексту)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text_content,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            # Если фото НЕТ (мы уже внутри корзины), просто РЕДАКТИРУЕМ текст на месте
            await safe_edit(query, text_content, keyboard, "Markdown")
    else:
        # Если вызвано без edit (например, командой /bouquet)
        await query.message.reply_text(
            text_content,
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# --- Обработка нажатий кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # обязательно

    # --- Главное меню ---
    if query.data == "menu":
        await safe_edit(query, "⬅️ Главное меню:", keyboard=main_menu_keyboard())

    # --- Каталог ---
    elif query.data == "catalog":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌹 SURRENDER", callback_data="flower_Surrender")],
            # [InlineKeyboardButton("🌷 LINCOLN", callback_data="flower_Lincoln")],
            [InlineKeyboardButton("🌼 STRONG GOLD", callback_data="flower_Strong Gold")],
            [InlineKeyboardButton("🌸 KAMALIYA", callback_data="flower_Kamaliya")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
        ])
        if query.message and getattr(query.message, 'photo', None):
            try:
                await query.message.delete()
            except Exception:
                pass
            # 2. Отправляем новое текстовое меню
            await query.message.reply_text("📋 Наш каталог:", reply_markup=keyboard)
        else:
            # 3. Если это уже текст, просто редактируем
            await safe_edit(query, "📋 Наш каталог:", keyboard=keyboard)


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
        # edit=True заставит show_bouquet вызвать safe_edit внутри себя
        await show_bouquet(query, context, edit=True)

        # Больше не нужно ничего удалять, сообщение просто обновится!


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
            keyboard_buttons = [[InlineKeyboardButton("📋 Каталог", callback_data="catalog")]]
        else:
            text = ["🛒 Ваш заказ:\n"]
            # Считаем общее кол-во цветов во ВСЕХ букетах корзины
            flowers_total = sum(o.get("count", 0) for o in orders)
            is_free_wrap = flowers_total >= FREE_LIMIT
            total_sum = 0

            for i, o in enumerate(orders, 1):
                # Цена цветов в букете
                b_price = o["count"] * FLOWER_PRICE
                # Цена упаковки (0 если цветов суммарно >= 15)
                w_price = 0
                if o["wrap"] and not is_free_wrap:
                    w_price = WRAP_PRICES.get(o["wrap"], 0)

                current_b_sum = b_price + w_price
                total_sum += current_b_sum

                text.append(f"{i}. Букет ({o['count']} шт.):")
                for flower_name, flower_qty in o.get("flowers", {}).items():
                    text.append(f"   • {flower_name}: {flower_qty} шт")
                if o["wrap"]:
                    status = " (Бесплатно!🔥)" if is_free_wrap else f" (+{w_price} ₽)"
                    text.append(f"   🎁 Упаковка: {'Слюда' if o['wrap'] == 'film' else 'Крафт'}{status}")
                text.append(f"   💰 Стоимость: {current_b_sum} ₽\n")

            # Расчет доставки
            total_sum += DELIVERY_PRICE
            text.append(f"🚚 Доставка: {DELIVERY_PRICE} ₽")
            # Итоговая сумма с учетом доставки
            text.append(f"\n💰 Итого к оплате: {total_sum} ₽")

            # Кнопки корзины
            keyboard_buttons = [
                [InlineKeyboardButton("🚚 Доставка", callback_data="delivery")],
                [InlineKeyboardButton("🏠 Самовывоз", callback_data="pickup")],
                [InlineKeyboardButton("🗑️ Очистить корзину", callback_data="clear_order")],  # Новая кнопка
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
            ]

        await safe_edit(query, "\n".join(text),
                        keyboard=InlineKeyboardMarkup(keyboard_buttons))


    # --- Очистка корзины (удаление заказа) ---
    elif query.data == "clear_order":
        context.user_data["orders"] = []  # Полностью очищаем список заказов
        await query.answer("Корзина очищена 🗑️")
        # Возвращаем пользователя в главное меню или заново в "order"
        await safe_edit(query, "🛒 Корзина пуста",
                        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Каталог", callback_data="catalog")]]))


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

        await safe_edit(query,
            f"✅ Букет добавлен в заказ\n💰 Стоимость: {price} ₽",
            keyboard=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Каталог", callback_data="catalog")],
                [InlineKeyboardButton("📦 Мой заказ", callback_data="order")],
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="menu")]
            ])
        )

    # --- Доставка ---
    elif query.data == "delivery":
        context.user_data["delivery"] = {}
        context.user_data["state"] = "delivery_street"
        await safe_edit(query, "Введите улицу:")

    # --- Самовывоз ---
    elif query.data == "pickup":
        context.user_data["state"] = "pickup_date"
        await safe_edit(query, "Введите дату получения:")

    # --- Подтверждение доставки ---
    elif query.data == "confirm_delivery":
        await send_order_to_admin(context, query.from_user)
        reset_user_data(context, clear_orders=True)
        await safe_edit(query,
            "Спасибо за заказ! 💐\n"
            "Ваш заказ отправлен на обработку.\n"
            "Наш администратор подтвердит заказ в личном сообщении.\n\n"
            "Вы можете оформить новый заказ:",
            keyboard=main_menu_keyboard()
        )

    # --- Подтверждение самовывоза ---
    elif query.data == "confirm_pickup":
        await send_order_to_admin(context, query.from_user, pickup=True)
        reset_user_data(context, clear_orders=True)
        await safe_edit(query,
            "Спасибо за заказ! 💐\n"
            "Ваш заказ отправлен на обработку.\n\n"
            "Заказ Вы сможете забрать по адресу:\n"
            "ул. Космонавтов, дом 8, подъезд 1, квартира 7.\n\n"
            "Вы можете оформить новый заказ:",
            keyboard=main_menu_keyboard()
        )

    elif query.data == "noop":
        await query.answer("❗ Сначала добавьте цветы в букет", show_alert=True)


# ================ Обработка текста ========================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    state = context.user_data.get("state")

    # если бот сейчас ничего не ждёт — игнорируем текст
    if not state:
        return

    text = update.message.text

    # --- ДОСТАВКА ---
    if state.startswith("delivery_"):
        field = state.replace("delivery_", "")
        context.user_data.setdefault("delivery", {})[field] = text

        DELIVERY_FIELDS = ["street", "house", "entrance","date", "time", "name", "phone"]
        FIELD_NAMES = {
            "street": "улицу",
            "house": "дом",
            "entrance": "подъезд",
            "date": "дату доставки",
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
    """Отправка полного и корректного заказа админу."""
    orders = context.user_data.get("orders", [])
    if not orders:
        return

    # 1. Считаем общее кол-во цветов во ВСЕХ букетах для скидки на упаковку
    flowers_total = sum(o.get("count", 0) for o in orders)
    # Скидка на упаковку, если суммарно во всех букетах >= FREE_LIMIT
    is_free_wrap = flowers_total >= FREE_LIMIT

    total_sum = 0
    text = [
        "📦 НОВЫЙ ЗАКАЗ 🆕",
        f"👤 Клиент: {user.full_name} (@{user.username})\n",
        "--- Состав заказа ---"
    ]

    # 2. Перечисляем букеты (логика как в корзине)
    for i, o in enumerate(orders, 1):
        # Цена самих цветов в конкретном букете
        b_price = o["count"] * FLOWER_PRICE

        # Расчет упаковки для этого букета
        w_price = 0
        wrap_info = ""
        if o["wrap"]:
            # Если цветов суммарно много — упаковка 0, иначе по прайсу
            w_price = 0 if is_free_wrap else WRAP_PRICES.get(o["wrap"], 0)
            status = " (Бесплатно)" if is_free_wrap else f" (+{w_price} ₽)"
            wrap_name = "Слюда" if o["wrap"] == "film" else "Крафт"
            wrap_info = f"   🎁 Упаковка: {wrap_name}{status}"

        # Сумма за этот конкретный букет
        current_b_sum = b_price + w_price
        total_sum += current_b_sum

        text.append(f"{i}. Букет ({o['count']} шт.):")
        # Перечисляем конкретные цветы в этом букете
        for name, qty in o.get("flowers", {}).items():
            text.append(f"   • {name}: {qty} шт")

        if wrap_info:
            text.append(wrap_info)
        text.append(f"   💰 Стоимость букета: {current_b_sum} ₽\n")

    # 3. Расчет доставки (только если НЕ самовывоз)
    if not pickup:
        total_sum += DELIVERY_PRICE
        text.append(f"🚚 Доставка: {DELIVERY_PRICE} ₽")

    text.append(f"<b>\n💰 ИТОГО К ОПЛАТЕ: {total_sum} ₽</b>")

    # 4. Данные о доставке или самовывозе
    text.append("\n--- Детали получения ---")
    if pickup:
        text.append("🏠 Самовывоз")
        text.append(f"📅 Дата: {context.user_data.get('pickup_date', '-')}")
        text.append(f"⏰ Время: {context.user_data.get('pickup_time', '-')}")
    else:
        d = context.user_data.get("delivery", {})
        text.append("🚚 Доставка")
        text.append(f"📍 Адрес: {d.get('street', '-')}, д.{d.get('house', '-')}, под.{d.get('entrance', '-')}")
        text.append(f"👤 Получатель: {d.get('name', '-')} ({d.get('phone', '-')})")
        text.append(f"📅 Дата/Время: {d.get('date', '-')} в {d.get('time', '-')}")

    # Отправка админу (используем HTML для жирного шрифта в ИТОГО)
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text="\n".join(text),
        parse_mode="HTML"
    )


# --- ЗАПУСК БОТА ---
def main():
    if not TOKEN or not WEBHOOK_URL:
        raise RuntimeError("❌ BOT_TOKEN или WEBHOOK_URL не заданы")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🚀 БОТ ЗАПУЩЕН (WEBHOOK)")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    asyncio.run(main())

