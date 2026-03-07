import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from supabase import create_client, Client


BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_ID = int(os.getenv("MANAGER_ID", "0"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com/")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not MANAGER_ID:
    raise ValueError("MANAGER_ID is not set or invalid")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is not set")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY is not set")


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_or_create_user(tg_user):
    """Ищет пользователя по telegram_id, создаёт если нет."""
    tg_id = tg_user.id

    res = (
        sb.from_("users")
        .select("*")
        .eq("telegram_id", tg_id)
        .maybe_single()
        .execute()
    )

    if res.data:
        return res.data

    new_user = (
        sb.from_("users")
        .insert(
            {
                "telegram_id": tg_id,
                "username": tg_user.username,
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
            }
        )
        .select()
        .single()
        .execute()
    )

    return new_user.data


def add_bonus(user_id: str, amount: int, tx_type: str, title: str):
    """Начисляет/списывает бонусы и пишет транзакцию."""
    user_res = (
        sb.from_("users")
        .select("bonus_balance")
        .eq("id", user_id)
        .single()
        .execute()
    )
    user = user_res.data or {}
    new_balance = (user.get("bonus_balance") or 0) + amount

    sb.from_("users").update({"bonus_balance": new_balance}).eq("id", user_id).execute()

    sb.from_("transactions").insert(
        {
            "user_id": user_id,
            "amount": amount,
            "type": tx_type,
            "title": title,
        }
    ).execute()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user = get_or_create_user(tg_user)
    args = (message.text or "").split(maxsplit=1)
    ref_arg = args[1] if len(args) > 1 else ""

    if ref_arg.startswith("ref_"):
        ref_tg_id = ref_arg[4:]

        referrer_res = (
            sb.from_("users")
            .select("id")
            .eq("telegram_id", ref_tg_id)
            .maybe_single()
            .execute()
        )
        referrer = referrer_res.data

        if referrer and referrer["id"] != user["id"]:
            exists_res = (
                sb.from_("referrals")
                .select("id")
                .eq("referrer_id", referrer["id"])
                .eq("referred_id", user["id"])
                .maybe_single()
                .execute()
            )
            exists = exists_res.data

            if not exists:
                sb.from_("referrals").insert(
                    {
                        "referrer_id": referrer["id"],
                        "referred_id": user["id"],
                    }
                ).execute()

                add_bonus(
                    referrer["id"],
                    150,
                    "referral",
                    f"Приглашение друга @{tg_user.username or tg_user.first_name or 'user'}",
                )

                referrer_full_res = (
                    sb.from_("users")
                    .select("telegram_id")
                    .eq("id", referrer["id"])
                    .single()
                    .execute()
                )
                referrer_full = referrer_full_res.data

                if referrer_full and referrer_full.get("telegram_id"):
                    try:
                        await bot.send_message(
                            referrer_full["telegram_id"],
                            "🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                            f"👤 {tg_user.first_name or 'Пользователь'}\n"
                            "💰 +150 ★ начислено на твой счёт!",
                        )
                    except Exception as e:
                        log.warning("Не удалось уведомить реферера: %s", e)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎓 Открыть СтудПрофи",
                    web_app={"url": WEBAPP_URL},
                )
            ]
        ]
    )

    bal = user.get("bonus_balance") or 0
    await message.answer(
        f"👋 Привет, {tg_user.first_name or 'друг'}!\n\n"
        f"💎 Твой баланс: *{bal} ★*\n\n"
        "Здесь ты можешь заказывать учебные работы и зарабатывать бонусы "
        "за каждый заказ и приглашение друзей.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user = get_or_create_user(message.from_user)
    bal = user.get("bonus_balance") or 0
    await message.answer(f"💎 Твой баланс: *{bal} ★*", parse_mode="Markdown")


@dp.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user = get_or_create_user(message.from_user)

    orders = (
        sb.from_("orders")
        .select("*")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
    )

    if not orders:
        await message.answer("📭 У тебя пока нет заказов.\n\nОформи первый в приложении!")
        return

    status_emoji = {
        "pending": "🟡",
        "working": "🔵",
        "done": "✅",
        "cancelled": "❌",
    }
    status_text = {
        "pending": "На рассмотрении",
        "working": "В работе",
        "done": "Готово",
        "cancelled": "Отменён",
    }

    text = "📦 *Твои последние заказы:*\n\n"
    for order in orders:
        emoji = status_emoji.get(order.get("status"), "🟡")
        st = status_text.get(order.get("status"), "Неизвестно")
        text += (
            f"{emoji} *{order.get('type', 'Без типа')}*\n"
            f"_{order.get('topic', 'Без темы')}_\n"
            f"Статус: {st}\n\n"
        )

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("notify_order"))
async def notify_order(message: Message):
    await message.answer("Команда зарезервирована для внутреннего использования.")


async def poll_new_orders():
    """Раз в 10 сек проверяем новые заказы и уведомляем менеджера."""
    notified = set()

    while True:
        try:
            orders = (
                sb.from_("orders")
                .select("*, users(telegram_id, first_name, username)")
                .eq("status", "pending")
                .eq("manager_notified", False)
                .execute()
                .data
                or []
            )

            for order in orders:
                order_id = order.get("id")
                if not order_id or order_id in notified:
                    continue

                user_info = order.get("users") or {}
                client_name = user_info.get("first_name", "Неизвестно")
                client_tg = user_info.get("telegram_id", "")
                username = (
                    f"@{user_info['username']}"
                    if user_info.get("username")
                    else f"tg://user?id={client_tg}"
                )

                text = (
                    "📦 *Новый заказ!*\n\n"
                    f"👤 Клиент: {client_name} ({username})\n"
                    f"📝 Тип: {order.get('type', '')}\n"
                    f"📌 Тема: {order.get('topic', '')}\n"
                    f"🏫 Вуз: {order.get('university', '')}\n"
                    f"📄 Страниц: {order.get('pages', '—')}\n"
                    f"📅 Дедлайн: {order.get('deadline', '—')}\n"
                    f"💬 Доп.: {order.get('extra', '—')}\n"
                )

                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔵 В работу",
                                callback_data=f"status|working|{order_id}|{client_tg}",
                            ),
                            InlineKeyboardButton(
                                text="✅ Готово",
                                callback_data=f"status|done|{order_id}|{client_tg}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text="❌ Отменить",
                                callback_data=f"status|cancelled|{order_id}|{client_tg}",
                            ),
                        ],
                    ]
                )

                await bot.send_message(
                    MANAGER_ID,
                    text,
                    parse_mode="Markdown",
                    reply_markup=kb,
                )

                sb.from_("orders").update({"manager_notified": True}).eq("id", order_id).execute()
                notified.add(order_id)

        except Exception as e:
            log.exception("Ошибка в poll_new_orders: %s", e)

        await asyncio.sleep(10)


@dp.callback_query(F.data.startswith("status|"))
async def handle_status_change(call: CallbackQuery):
    if call.from_user.id != MANAGER_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return

    parts = (call.data or "").split("|")
    if len(parts) != 4:
        await call.answer("Некорректные данные", show_alert=True)
        return

    _, new_status, order_id, client_tg_raw = parts

    try:
        client_tg = int(client_tg_raw) if client_tg_raw else None
    except ValueError:
        client_tg = None

    status_labels = {
        "working": "🔵 В работе",
        "done": "✅ Готово",
        "cancelled": "❌ Отменён",
    }

    client_messages = {
        "working": (
            "🔵 Твой заказ взят в работу!\n\n"
            "Менеджер уже занимается им. Ждём результата 💪"
        ),
        "done": (
            "✅ Твой заказ готов!\n\n"
            "🎉 На твой счёт начислено +100 ★ бонусов!\n\n"
            "Спасибо, что выбрал СтудПрофи!"
        ),
        "cancelled": (
            "❌ К сожалению, твой заказ был отменён.\n\n"
            "Если есть вопросы — напиши менеджеру."
        ),
    }

    sb.from_("orders").update({"status": new_status}).eq("id", order_id).execute()

    if client_tg:
        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🎓 Открыть приложение",
                            web_app={"url": WEBAPP_URL},
                        )
                    ]
                ]
            )
            await bot.send_message(
                client_tg,
                client_messages.get(new_status, "Статус заказа обновлён."),
                reply_markup=kb,
            )
        except Exception as e:
            log.warning("Не удалось уведомить клиента %s: %s", client_tg, e)

    label = status_labels.get(new_status, new_status)

    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.answer(f"✅ Статус изменён на: *{label}*", parse_mode="Markdown")

    await call.answer()


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user is None or message.from_user.id != MANAGER_ID:
        await message.answer("❌ Нет доступа")
        return

    users_count = len(sb.from_("users").select("id").execute().data or [])
    orders_total = len(sb.from_("orders").select("id").execute().data or [])
    orders_new = len(sb.from_("orders").select("id").eq("status", "pending").execute().data or [])
    orders_work = len(sb.from_("orders").select("id").eq("status", "working").execute().data or [])

    await message.answer(
        "👨‍💼 *Панель менеджера*\n\n"
        f"👥 Пользователей: *{users_count}*\n"
        f"📦 Всего заказов: *{orders_total}*\n"
        f"🟡 Новых: *{orders_new}*\n"
        f"🔵 В работе: *{orders_work}*\n\n"
        "Новые заказы приходят автоматически с кнопками управления.",
        parse_mode="Markdown",
    )


@dp.message(Command("pending"))
async def cmd_pending(message: Message):
    if message.from_user is None or message.from_user.id != MANAGER_ID:
        await message.answer("❌ Нет доступа")
        return

    orders = (
        sb.from_("orders")
        .select("*, users(telegram_id, first_name, username)")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )

    if not orders:
        await message.answer("✅ Новых заказов нет!")
        return

    for order in orders:
        user_info = order.get("users") or {}
        client_name = user_info.get("first_name", "Неизвестно")
        client_tg = user_info.get("telegram_id", "")
        username = f"@{user_info['username']}" if user_info.get("username") else str(client_tg)

        text = (
            "📦 *Заказ*\n\n"
            f"👤 {client_name} ({username})\n"
            f"📝 {order.get('type', '')}\n"
            f"📌 {order.get('topic', '')}\n"
            f"🏫 {order.get('university', '')}\n"
            f"📅 {order.get('deadline', '—')}\n"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔵 В работу",
                        callback_data=f"status|working|{order.get('id')}|{client_tg}",
                    ),
                    InlineKeyboardButton(
                        text="✅ Готово",
                        callback_data=f"status|done|{order.get('id')}|{client_tg}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отменить",
                        callback_data=f"status|cancelled|{order.get('id')}|{client_tg}",
                    ),
                ],
            ]
        )

        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def main():
    asyncio.create_task(poll_new_orders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
