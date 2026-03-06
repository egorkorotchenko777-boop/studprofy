from aiogram import Router, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import database as db
from config import ADMIN_IDS, BONUS_FOR_OWN_ORDER, BONUS_FOR_REFERRAL_ORDER

router = Router()

def is_admin(user_id):
    return user_id in ADMIN_IDS

@router.callback_query(lambda c: c.data.startswith("confirm_order_"))
async def confirm_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    order_id = int(callback.data.split("_")[-1])
    order = await db.get_order_user(order_id)
    if not order:
        await callback.answer("Заказ не найден")
        return
    user_id = await db.confirm_order(order_id)
    await db.add_bonus(user_id, BONUS_FOR_OWN_ORDER, f"Заказ #{order_id}")
    referrer_id = order["referrer_id"]
    if referrer_id:
        await db.add_bonus(referrer_id, BONUS_FOR_REFERRAL_ORDER, f"Заказ реферала #{order_id}")
        try:
            await bot.send_message(referrer_id,
                f"🎉 Твой друг оформил заказ!\n+{BONUS_FOR_REFERRAL_ORDER} бонусов! 💰")
        except:
            pass
    try:
        await bot.send_message(user_id,
            f"✅ <b>Заказ #{order_id} подтверждён!</b>\n+{BONUS_FOR_OWN_ORDER} бонусов 🎁",
            parse_mode="HTML")
    except:
        pass
    await callback.message.edit_text(callback.message.text + "\n\n✅ ПОДТВЕРЖДЁН", parse_mode="HTML")
    await callback.answer("✅ Подтверждено!")

@router.callback_query(lambda c: c.data.startswith("cancel_order_"))
async def cancel_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    order_id = int(callback.data.split("_")[-1])
    user_id = await db.confirm_order(order_id)
    try:
        await bot.send_message(user_id, f"❌ Заказ #{order_id} отменён.\nПо вопросам: @StudProfy")
    except:
        pass
    await callback.message.edit_text(callback.message.text + "\n\n❌ ОТМЕНЁН", parse_mode="HTML")
    await callback.answer("Отменён")

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📦 Новые заказы", callback_data="admin_orders")],
    ])
    await message.answer("🔧 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    users = await db.get_all_users()
    total_bonuses = sum(u["bonus_points"] for u in users)
    total_orders = sum(u["total_orders"] for u in users)
    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"💰 Бонусов в обороте: <b>{total_bonuses}</b>\n"
        f"📦 Всего заказов: <b>{total_orders}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    users = await db.get_all_users()
    text = "👥 <b>Топ по бонусам:</b>\n\n"
    for i, u in enumerate(users[:10], 1):
        un = f"@{u['username']}" if u['username'] else f"ID:{u['user_id']}"
        text += f"{i}. {u['full_name']} ({un}) — {u['bonus_points']} ★\n"
    await callback.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    orders = await db.get_all_orders("pending")
    if not orders:
        await callback.answer("Нет новых заказов", show_alert=True)
        return
    text = f"📦 <b>Новые заказы ({len(orders)}):</b>\n\n"
    for o in orders[:5]:
        un = f"@{o['username']}" if o['username'] else f"ID:{o['user_id']}"
        text += f"#{o['id']} — {o['full_name']} ({un})\n{str(o['description'])[:60]}...\n\n"
    await callback.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📦 Новые заказы", callback_data="admin_orders")],
    ])
    await callback.message.edit_text("🔧 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()
