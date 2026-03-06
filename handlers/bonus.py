from aiogram import Router, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database as db
from config import GIFT_THRESHOLD

router = Router()

@router.callback_query(lambda c: c.data == "my_bonuses")
async def show_bonuses(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала напиши /start")
        return
    referrals = await db.get_referrals_count(callback.from_user.id)
    balance = user["bonus_points"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(
        f"🎁 <b>Твои бонусы</b>\n\n"
        f"💰 Баланс: <b>{balance} бонусов</b>\n"
        f"👥 Приглашено друзей: <b>{referrals}</b>\n"
        f"📦 Всего заказов: <b>{user['total_orders']}</b>\n\n"
        f"До подарка: <b>{max(0, GIFT_THRESHOLD - balance)}</b> бонусов",
        parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "referral_link")
async def show_referral(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    referrals = await db.get_referrals_count(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(
        f"👥 <b>Реферальная ссылка</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"Отправь друзьям и получай бонусы!\n\n"
        f"Приглашено: <b>{referrals} чел.</b>\n"
        f"• +150 ★ когда друг зарегистрируется\n"
        f"• +300 ★ когда друг сделает заказ",
        parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: CallbackQuery):
    from handlers.start import main_menu
    user = await db.get_user(callback.from_user.id)
    balance = user["bonus_points"] if user else 0
    await callback.message.edit_text(
        f"👋 Главное меню\n\n💰 Баланс: <b>{balance} бонусов</b>\n\nВыбери действие 👇",
        parse_mode="HTML", reply_markup=main_menu()
    )
    await callback.answer()
