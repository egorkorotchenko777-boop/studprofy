from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
import database as db
from config import CHANNEL_ID, BONUS_FOR_SUBSCRIBE, BONUS_FOR_REFERRAL

router = Router()

MINI_APP_URL = "https://egorkorotchenko777-boop.github.io/studprofy"

async def check_subscription(bot, user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Открыть приложение бонусов", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="referral_link")],
        [InlineKeyboardButton(text="🎁 Мои бонусы", callback_data="my_bonuses")],
        [InlineKeyboardButton(text="📦 Оформить заказ", callback_data="new_order")],
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name

    referrer_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            ref = args[1].replace("ref_", "")
            referrer_id = int(ref)
            if referrer_id == user_id:
                referrer_id = None
        except:
            referrer_id = None

    existing = await db.get_user(user_id)
    is_new = existing is None

    await db.create_user(user_id, username, full_name, referrer_id)

    if is_new and referrer_id:
        referrer = await db.get_user(referrer_id)
        if referrer:
            await db.add_bonus(referrer_id, BONUS_FOR_REFERRAL, "Приглашение друга")
            try:
                await bot.send_message(referrer_id,
                    f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n+{BONUS_FOR_REFERRAL} бонусов 🎁")
            except:
                pass

    is_subscribed = await check_subscription(bot, user_id)
    if is_subscribed and is_new:
        await db.add_bonus(user_id, BONUS_FOR_SUBSCRIBE, "Подписка на канал")
        bonus_text = f"\n✅ Подписан на канал — +{BONUS_FOR_SUBSCRIBE} бонусов!"
    elif not is_subscribed:
        bonus_text = f"\n⚠️ Подпишись на @StudProfy и получи +{BONUS_FOR_SUBSCRIBE} бонусов!"
    else:
        bonus_text = ""

    user = await db.get_user(user_id)
    balance = user["bonus_points"] if user else 0

    await message.answer(
        f"👋 Привет, {full_name}!\n\n"
        f"Добро пожаловать в систему лояльности СтудПрофи 🎓{bonus_text}\n\n"
        f"💰 Твой баланс: <b>{balance} бонусов</b>\n\n"
        f"Нажми кнопку ниже чтобы открыть приложение 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
