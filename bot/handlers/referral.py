"""
Handler de indicação (referral 3 níveis).
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from bot.database import db
from bot.keyboards import Keyboards
from bot.config import Config
from bot.services.referral import referral_service

logger = logging.getLogger(__name__)


async def referral_command(update: Update, context: CallbackContext):
    """Handle /indicar — mostra sistema de referral."""
    user = update.effective_user

    code = referral_service.get_or_create_code(user.id)
    stats = referral_service.get_stats(user.id)

    bot_username = context.bot.username

    text = (
        "👥 *Sistema de Indicação*\n\n"
        f"💰 *Ganhe dinheiro indicando amigos!*\n\n"
        f"🔗 *Seu link de indicação:*\n"
        f"`https://t.me/{bot_username}?start={code}`\n\n"
        f"📊 *Suas Estatísticas:*\n"
        f"• Total de indicados: *{stats['total_referrals']}*\n"
        f"  - Nível 1 (direto): {stats['counts'][1]}\n"
        f"  - Nível 2: {stats['counts'][2]}\n"
        f"  - Nível 3: {stats['counts'][3]}\n"
        f"• Ganhos com indicações: *R$ {stats['earnings']:.2f}*\n\n"
        f"📋 *Comissões:*\n"
        f"• Nível 1 (indicação direta): *{Config.REFERRAL_LEVEL_1:.0f}%* das compras\n"
        f"• Nível 2 (indicado do indicado): *{Config.REFERRAL_LEVEL_2:.0f}%*\n"
        f"• Nível 3: *{Config.REFERRAL_LEVEL_3:.0f}%*\n"
        f"• Bônus de cadastro: *R$ {Config.REFERRAL_SIGNUP_BONUS:.2f}*\n\n"
        f"💡 *Como funciona:*\n"
        f"1️⃣ Compartilhe seu link\n"
        f"2️⃣ A pessoa se cadastra e ganha R$ {Config.REFERRAL_SIGNUP_BONUS:.2f}\n"
        f"3️⃣ Você ganha bônus + comissão das compras dela\n"
        f"4️⃣ Ainda ganha comissão das compras dos indicados por ela!\n\n"
        f"🚀 *Quanto mais você indica, mais ganha!*"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )


async def referral_callback(update: Update, context: CallbackContext):
    """Callback do botão de indicação."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    code = referral_service.get_or_create_code(user.id)
    stats = referral_service.get_stats(user.id)
    bot_username = context.bot.username

    text = (
        "👥 *Indique e Ganhe!*\n\n"
        f"🔗 `https://t.me/{bot_username}?start={code}`\n\n"
        f"📊 Indicados: *{stats['total_referrals']}*\n"
        f"💰 Ganhos: *R$ {stats['earnings']:.2f}*\n\n"
        f"📋 Nível 1: *{Config.REFERRAL_LEVEL_1:.0f}%*\n"
        f"📋 Nível 2: *{Config.REFERRAL_LEVEL_2:.0f}%*\n"
        f"📋 Nível 3: *{Config.REFERRAL_LEVEL_3:.0f}%*"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )


def get_handlers():
    return [
        CommandHandler('indicar', referral_command),
        CallbackQueryHandler(referral_callback, pattern='^referral$'),
    ]