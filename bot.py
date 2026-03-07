import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client
import os

# ==============================
# ⚙️ НАСТРОЙКИ
# ==============================
BOT_TOKEN    = os.getenv("BOT_TOKEN", "8771034458:AAEXVL8Y5M9BAIIP5jtovgVcO12r2FY_N0U")
MANAGER_ID   = int(os.getenv("MANAGER_ID", "8515276800"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hmtvzflvnzxhoalshwmt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_YqbanryR_Gtvf81MirWRVA_wsIuyAiz")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "https://egorkorotchenko777-boop.github.io/studprofy/")
# ==============================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
sb  = create_client(SUPABASE_URL, SUPABASE_KEY)


# ───────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ───────────────────────────────────────────

def get_or_create_user(tg_user):
    """Ищет пользователя по telegram_id, создаёт если нет."""
    tg_id = tg_user.id
    res = sb.from_("users").select("*").eq("telegram_id", tg_id).maybe_single().execute()
    if res.data:
        return res.data
    new = sb.from_("users").insert({
        "telegram_id": tg_id,
        "username":    tg_user.username,
        "first_name":  tg_user.first_name,
        "last_name":   tg_user.last_name,
    }).select().single().execute()
    return new.data


def add_bonus(user_id: str, amount: int, tx_type: str, title: str):
    """Начисляет/списывает бонусы и пишет транзакцию."""
    user = sb.from_("users").select("bonus_balance").eq("id", user_id).single().execute().data
    new_balance = (user["bonus_balance"] or 0) + amount
    sb.from_("users").update({"bonus_balance": new_balance}).eq("id", user_id).execute()
    sb.from_("transactions").insert({
        "user_id": user_id,
        "amount":  amount,
        "type":    tx_type,
        "title":   title,
    }).execute()


# ───────────────────────────────────────────
# /start — приветствие + реферал
# ───────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg_user = message.from_user
    user    = get_or_create_user(tg_user)
    args    = message.text.split(maxsplit=1)
    ref_arg = args[1] if len(args) > 1 else ""

    # Обработка реферальной ссылки
    if ref_arg.startswith("ref_"):
        ref_tg_id = ref_arg[4:]  # telegram_id пригласившего
        referrer  = sb.from_("users").select("id").eq("telegram_id", ref_tg_id).maybe_single().execute().data

        if referrer and referrer["id"] != user["id"]:
            # Проверяем — не был ли уже реферал записан
            exists = sb.from_("referrals") \
                .select("id") \
                .eq("referrer_user_id", referrer["id"]) \
                .eq("invited_user_id", user["id"]) \
                .maybe_single().execute().data

            if not exists:
                # Записываем реферала
                sb.from_("referrals").insert({
                    "referrer_user_id": referrer["id"],
                    "invited_user_id": user["id"],
                    "signup_bonus_given": True,
                    "order_bonus_given": False,
                }).execute()

                # Начисляем бонус пригласившему
                add_bonus(referrer["id"], 150, "referral", f"Приглашение друга @{tg_user.username or tg_user.first_name}")

                # Уведомляем пригласившего
                referrer_full = sb.from_("users").select("telegram_id").eq("id", referrer["id"]).single().execute().data
                try:
                    await bot.send_message(
                        referrer_full["telegram_id"],
                        f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                        f"👤 {tg_user.first_name}\n"
                        f"💰 +150 ★ начислено на твой счёт!"
                    )
                except Exception:
                    pass

    # Кнопка открыть мини-апп
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎓 Открыть СтудПрофи",
            web_app={"url": WEBAPP_URL}
        )
    ]])

    bal = user.get("bonus_balance") or 0
    await message.answer(
        f"👋 Привет, {tg_user.first_name}!\n\n"
        f"💎 Твой баланс: *{bal} ★*\n\n"
        f"Здесь ты можешь заказывать учебные работы и зарабатывать бонусы за каждый заказ и приглашение друзей.",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ───────────────────────────────────────────
# /balance — баланс
# ───────────────────────────────────────────

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    user = get_or_create_user(message.from_user)
    bal  = user.get("bonus_balance") or 0
    await message.answer(f"💎 Твой баланс: *{bal} ★*", parse_mode="Markdown")


# ───────────────────────────────────────────
# /orders — мои заказы
# ───────────────────────────────────────────

@dp.message(Command("orders"))
async def cmd_orders(message: Message):
    user   = get_or_create_user(message.from_user)
    orders = sb.from_("orders").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(5).execute().data

    if not orders:
        await message.answer("📭 У тебя пока нет заказов.\n\nОформи первый в приложении!")
        return

    status_emoji = {"pending": "🟡", "working": "🔵", "done": "✅", "cancelled": "❌"}
    status_text  = {"pending": "На рассмотрении", "working": "В работе", "done": "Готово", "cancelled": "Отменён"}

    text = "📦 *Твои последние заказы:*\n\n"
    for o in orders:
        emoji = status_emoji.get(o["status"], "🟡")
        st    = status_text.get(o["status"], "Неизвестно")
        text += f"{emoji} *{o['type']}*\n_{o['topic']}_\nСтатус: {st}\n\n"

    await message.answer(text, parse_mode="Markdown")


# ───────────────────────────────────────────
# WEBHOOK от мини-апп — новый заказ
# Мини-апп сохраняет заказ в Supabase,
# бот получает уведомление через Supabase Webhook
# или через прямой вызов /notify_order
# ───────────────────────────────────────────

@dp.message(Command("notify_order"))
async def notify_order(message: Message):
    """Внутренняя команда — вызывается Supabase webhook при новом заказе."""
    pass  # реализовано через polling + проверку новых заказов ниже


async def poll_new_orders():
    """Раз в 10 сек проверяем новые заказы со статусом pending и уведомляем менеджера."""
    notified = set()  # хранит id уже уведомлённых заказов

    while True:
        try:
            orders = sb.from_("orders") \
                .select("*, users(telegram_id, first_name, username)") \
                .eq("status", "pending") \
                .eq("manager_notified", False) \
                .execute().data or []

            for order in orders:
                if order["id"] in notified:
                    continue

                u = order.get("users") or {}
                client_name = u.get("first_name", "Неизвестно")
                client_tg   = u.get("telegram_id", "")
                username    = f"@{u['username']}" if u.get("username") else f"tg://user?id={client_tg}"

                text = (
                    f"📦 *Новый заказ!*\n\n"
                    f"👤 Клиент: {client_name} ({username})\n"
                    f"📝 Тип: {order.get('type','')}\n"
                    f"📌 Тема: {order.get('topic','')}\n"
                    f"🏫 Вуз: {order.get('university','')}\n"
                    f"📄 Страниц: {order.get('pages','—')}\n"
                    f"📅 Дедлайн: {order.get('deadline','—')}\n"
                    f"💬 Доп.: {order.get('requirements','—')}\n"
                )

                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔵 В работу",  callback_data=f"status_working_{order['id']}_{client_tg}"),
                        InlineKeyboardButton(text="✅ Готово",    callback_data=f"status_done_{order['id']}_{client_tg}"),
                    ],
                    [
                        InlineKeyboardButton(text="❌ Отменить",  callback_data=f"status_cancelled_{order['id']}_{client_tg}"),
                    ]
                ])

                await bot.send_message(MANAGER_ID, text, parse_mode="Markdown", reply_markup=kb)

                # Помечаем что уведомили
                sb.from_("orders").update({"manager_notified": True}).eq("id", order["id"]).execute()
                notified.add(order["id"])

        except Exception as e:
            log.error(f"Poll error: {e}")

        await asyncio.sleep(10)


# ───────────────────────────────────────────
# КНОПКИ МЕНЕДЖЕРА — смена статуса
# ───────────────────────────────────────────

@dp.callback_query(F.data.startswith("status_"))
async def handle_status_change(call: CallbackQuery):
    # Проверяем что нажал именно менеджер
    if call.from_user.id != MANAGER_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return

    parts     = call.data.split("_", 3)  # status_working_<order_id>_<client_tg_id>
    new_status = parts[1]
    order_id   = parts[2]
    client_tg  = int(parts[3]) if len(parts) > 3 else None

    status_labels = {
        "working":   "🔵 В работе",
        "done":      "✅ Готово",
        "cancelled": "❌ Отменён"
    }
    client_messages = {
        "working":   "🔵 Твой заказ взят в работу!\n\nМенеджер уже занимается им. Ждём результата 💪",
        "done":      "✅ Твой заказ готов!\n\n🎉 На твой счёт начислено +100 ★ бонусов!\n\nСпасибо что выбрал СтудПрофи!",
        "cancelled": "❌ К сожалению, твой заказ был отменён.\n\nЕсли есть вопросы — напиши менеджеру."
    }

    # Обновляем статус в базе
    sb.from_("orders").update({"status": new_status}).eq("id", order_id).execute()

    # Если done — бонусы начисляет триггер в Supabase автоматически

    # Уведомляем клиента
    if client_tg:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎓 Открыть приложение", web_app={"url": WEBAPP_URL})
            ]])
            await bot.send_message(client_tg, client_messages[new_status], reply_markup=kb)
        except Exception as e:
            log.error(f"Cannot notify client {client_tg}: {e}")

    # Обновляем сообщение у менеджера
    label = status_labels.get(new_status, new_status)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"✅ Статус изменён на: *{label}*", parse_mode="Markdown")
    await call.answer()


# ───────────────────────────────────────────
# /admin — панель менеджера
# ───────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != MANAGER_ID:
        await message.answer("❌ Нет доступа")
        return

    # Считаем статистику
    users_count  = len(sb.from_("users").select("id").execute().data or [])
    orders_total = len(sb.from_("orders").select("id").execute().data or [])
    orders_new   = len(sb.from_("orders").select("id").eq("status","pending").execute().data or [])
    orders_work  = len(sb.from_("orders").select("id").eq("status","working").execute().data or [])

    await message.answer(
        f"👨‍💼 *Панель менеджера*\n\n"
        f"👥 Пользователей: *{users_count}*\n"
        f"📦 Всего заказов: *{orders_total}*\n"
        f"🟡 Новых: *{orders_new}*\n"
        f"🔵 В работе: *{orders_work}*\n\n"
        f"Новые заказы приходят автоматически с кнопками управления.",
        parse_mode="Markdown"
    )


# ───────────────────────────────────────────
# /pending — показать новые заказы вручную
# ───────────────────────────────────────────

@dp.message(Command("pending"))
async def cmd_pending(message: Message):
    if message.from_user.id != MANAGER_ID:
        await message.answer("❌ Нет доступа")
        return

    orders = sb.from_("orders") \
        .select("*, users(telegram_id, first_name, username)") \
        .eq("status", "pending") \
        .order("created_at", desc=True) \
        .limit(10).execute().data or []

    if not orders:
        await message.answer("✅ Новых заказов нет!")
        return

    for order in orders:
        u = order.get("users") or {}
        client_name = u.get("first_name", "Неизвестно")
        client_tg   = u.get("telegram_id", "")
        username    = f"@{u['username']}" if u.get("username") else str(client_tg)

        text = (
            f"📦 *Заказ*\n\n"
            f"👤 {client_name} ({username})\n"
            f"📝 {order.get('type','')}\n"
            f"📌 {order.get('topic','')}\n"
            f"🏫 {order.get('university','')}\n"
            f"📅 {order.get('deadline','—')}\n"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔵 В работу", callback_data=f"status_working_{order['id']}_{client_tg}"),
                InlineKeyboardButton(text="✅ Готово",   callback_data=f"status_done_{order['id']}_{client_tg}"),
            ],
            [
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"status_cancelled_{order['id']}_{client_tg}"),
            ]
        ])
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ───────────────────────────────────────────
# ЗАПУСК
# ───────────────────────────────────────────

async def health(request):
    return web.Response(text="OK")


async def main():
    # Запускаем health-check сервер для Render
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    log.info("Health check server started")

    # Запускаем polling новых заказов параллельно
    asyncio.create_task(poll_new_orders())
    await dp.start_polling(bot, allowed_updates=['message', 'callback_query'])


if __name__ == "__main__":
    asyncio.run(main())
