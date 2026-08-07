"""
Handler de cupons de desconto.
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from bot.database import db
from bot.keyboards import Keyboards

logger = logging.getLogger(__name__)

WAITING_COUPON_CODE = 1


async def coupon_command(update: Update, context: CallbackContext):
    """Handle /cupom — usar cupom."""
    await update.message.reply_text(
        "🏷️ *Cupom de Desconto*\n\n"
        "Digite o código do seu cupom:\n\n"
        "Exemplo: `MASTER10`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )
    return WAITING_COUPON_CODE


async def coupon_code_received(update: Update, context: CallbackContext):
    """Processa código do cupom."""
    code = update.message.text.strip().upper()
    user = update.effective_user

    coupon = db.get_coupon(code)
    if not coupon:
        await update.message.reply_text(
            "❌ Cupom inválido. Verifique o código e tente novamente.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return ConversationHandler.END

    if not coupon.active:
        await update.message.reply_text(
            "❌ Este cupom está desativado.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return ConversationHandler.END

    if coupon.expires_at and datetime.utcnow() > coupon.expires_at:
        await update.message.reply_text(
            "❌ Este cupom expirou.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return ConversationHandler.END

    if coupon.max_uses and coupon.current_uses >= coupon.max_uses:
        await update.message.reply_text(
            "❌ Este cupom já atingiu o limite de usos.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return ConversationHandler.END

    # Verificar se já usou
    from bot.database import CouponUsage
    with db.session() as s:
        already = s.query(CouponUsage).filter_by(
            user_id=user.id, coupon_code=code
        ).first()
        if already:
            await update.message.reply_text(
                "❌ Você já usou este cupom.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboards.back(),
            )
            return ConversationHandler.END

    # Aplicar cupom: dar bônus ao usuário
    # Cupom de depósito: percentual do valor configurado
    from bot.config import Config
    bonus_amount = 5.0  # Valor fixo para cupons simples
    if coupon.discount_percent > 0:
        bonus_amount = coupon.discount_percent  # Pode ser valor fixo em R$

    db.update_balance(user.id, bonus_amount)
    db.add_transaction(
        user_id=user.id,
        tx_type='deposit',
        amount=bonus_amount,
        description=f'Cupom {code} - R$ {bonus_amount:.2f}',
    )
    db.use_coupon(code, user.id)

    await update.message.reply_text(
        f"✅ *Cupom aplicado com sucesso!*\n\n"
        f"🏷️ Código: `{code}`\n"
        f"💰 Bônus: *R$ {bonus_amount:.2f}*\n\n"
        f"Seu saldo foi atualizado!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu(),
    )

    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext):
    """Cancela a conversa."""
    await update.message.reply_text(
        "Operação cancelada.",
        reply_markup=Keyboards.back(),
    )
    return ConversationHandler.END


def get_handlers():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('cupom', coupon_command)],
        states={
            WAITING_COUPON_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, coupon_code_received),
            ],
        },
        fallbacks=[CommandHandler('cancelar', cancel)],
    )
    return [conv_handler]