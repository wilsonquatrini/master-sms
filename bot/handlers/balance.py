"""
Handler de saldo e histórico.
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from bot.database import db
from bot.keyboards import Keyboards

logger = logging.getLogger(__name__)


async def saldo_command(update: Update, context: CallbackContext):
    """Handle /saldo."""
    user = update.effective_user
    db_user = db.get_user(user.id)

    trans = db.get_user_transactions(user.id, limit=5)

    trans_text = ""
    if trans:
        trans_text = "\n\n📋 *Últimas Transações:*\n"
        for t in trans:
            emoji = "💰" if t.type == "deposit" else "📱" if t.type == "purchase" else "👥" if "referral" in t.type else "↩️"
            trans_text += f"{emoji} {t.type.title()}: *R$ {abs(t.amount):.2f}* - {t.created_at.strftime('%d/%m %H:%M')}\n"

    text = (
        f"💰 *Seu Saldo*\n\n"
        f"Saldo disponível: *R$ {db_user.balance:.2f}*\n"
        f"Total gasto: R$ {db_user.total_spent:.2f}\n"
        f"{trans_text}\n"
        f"Use /depositar para adicionar créditos"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.deposit_options() if db_user.balance < 10 else Keyboards.back(),
    )


async def historico_command(update: Update, context: CallbackContext):
    """Handle /historico."""
    user = update.effective_user

    trans = db.get_user_transactions(user.id, limit=15)

    if not trans:
        await update.message.reply_text(
            "📋 *Histórico*\n\nNenhuma transação encontrada.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    text = "📋 *Histórico de Transações*\n\n"
    for t in trans:
        emoji = "💰" if t.type == "deposit" else "📱" if t.type == "purchase" else "👥" if "referral" in t.type else "↩️"
        status = "✅" if t.status == "completed" else "⏳" if t.status == "pending" else "❌"
        text += f"{emoji} {status} *{t.type.title()}*: R$ {abs(t.amount):.2f}\n"
        text += f"   🕐 {t.created_at.strftime('%d/%m/%Y %H:%M')}\n"
        if t.description:
            text += f"   📝 {t.description}\n"
        text += "\n"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )


async def saldo_callback(update: Update, context: CallbackContext):
    """Callback do botão saldo."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = db.get_user(user.id)

    trans = db.get_user_transactions(user.id, limit=5)

    trans_text = ""
    if trans:
        trans_text = "\n\n📋 *Últimas:*\n"
        for t in trans:
            emoji = "💰" if t.type == "deposit" else "📱" if t.type == "purchase" else "↩️"
            trans_text += f"{emoji} {t.type.title()}: R$ {abs(t.amount):.2f}\n"

    text = (
        f"💰 *Saldo*\n\n"
        f"Disponível: *R$ {db_user.balance:.2f}*\n"
        f"{trans_text}"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.deposit_options() if db_user.balance < 10 else Keyboards.back(),
    )


async def historico_callback(update: Update, context: CallbackContext):
    """Callback do botão histórico."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    trans = db.get_user_transactions(user.id, limit=10)

    if not trans:
        await query.edit_message_text(
            "📋 *Histórico*\n\nNenhuma transação.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    text = "📋 *Histórico*\n\n"
    for t in trans:
        emoji = "💰" if t.type == "deposit" else "📱" if t.type == "purchase" else "↩️"
        text += f"{emoji} *{t.type.title()}*: R$ {abs(t.amount):.2f} ({t.created_at.strftime('%d/%m %H:%M')})\n"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )


def get_handlers():
    return [
        CommandHandler('saldo', saldo_command),
        CommandHandler('historico', historico_command),
        CallbackQueryHandler(saldo_callback, pattern='^saldo$'),
        CallbackQueryHandler(historico_callback, pattern='^historico$'),
    ]