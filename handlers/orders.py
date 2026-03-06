from aiogram import Router, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from config import ADMIN_IDS, BONUS_FOR_OWN_ORDER

router = Router()

class OrderState(StatesGroup):
    waiting_description = State()

@router.callback_query(lambda c: c.data == "new_order")
async def new_order_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.waiting_description)
    await callback.message.edit_text(
        "📦 <b>Новый заказ</b>\n\n"
        "Напиши одним сообщением:\n"
        "— Тип работы\n— Тема\n— Дедлайн\n— Учебное заведение и группа",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(OrderState.waiting_description)
async def process_order(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    order_id = await db.create_order(user_id, message.text)
    await message.answer(
        f"✅ <b>Заказ #{order_id} принят!</b>\n\n"
        f"Скоро свяжемся с тобой.\n"
        f"+{BONUS_FOR_OWN_ORDER} бонусов после подтверждения!",
        parse_mode="HTML"
    )
    user = await db.get_user(user_id)
    username = f"@{user['username']}" if user['username'] else f"ID:{user_id}"
    for admin_id in ADMIN_IDS:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_order_{order_id}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_order_{order_id}")],
            ])
            await bot.send_message(admin_id,
                f"📦 <b>Заказ #{order_id}</b>\n\n"
                f"👤 {user['full_name']} ({username})\n\n"
                f"📝 {message.text}",
                parse_mode="HTML", reply_markup=keyboard
            )
        except:
            pass
    await state.clear()
