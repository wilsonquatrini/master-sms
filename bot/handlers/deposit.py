"""
Handler de depósito PIX.
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from bot.database import db
from bot.keyboards import Keyboards
from bot.config import Config
from bot.services.pix import pix

logger = logging.getLogger(__name__)

# Estados da conversa
WAITING_CUSTOM_AMOUNT = 1


async def depositar_command(update: Update, context: CallbackContext):
    """Handle /depositar."""
    user = update.effective_user
    db_user = db.get_user(user.id)

    text = (
        "💳 *Depósito via PIX*\n\n"
        "Escolha o valor que deseja depositar:"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.deposit_options(),
    )


async def depositar_callback(update: Update, context: CallbackContext):
    """Callback dos botões de depósito."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    data = query.data

    if data == 'depositar':
        text = (
            "💳 *Depósito via PIX*\n\n"
            "Escolha o valor:"
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.deposit_options(),
        )
        return

    if data == 'dep_custom':
        await query.edit_message_text(
            "💳 *Depósito Personalizado*\n\n"
            f"Digite o valor desejado (entre R$ {Config.MIN_DEPOSIT:.0f} e R$ {Config.MAX_DEPOSIT:.0f}):\n\n"
            "Exemplo: `30` ou `45.50`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to("depositar"),
        )
        return WAITING_CUSTOM_AMOUNT

    # Valores fixos
    amounts = {
        'dep_10': 10,
        'dep_25': 25,
        'dep_50': 50,
        'dep_100': 100,
    }
    amount = amounts.get(data)
    if amount:
        await _process_deposit(query, user, amount)


async def custom_amount_received(update: Update, context: CallbackContext):
    """Recebe valor personalizado do usuário."""
    try:
        amount = float(update.message.text.replace(',', '.').strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Digite apenas números.\n"
            f"Exemplo: `30` ou `45.50`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_CUSTOM_AMOUNT

    if amount < Config.MIN_DEPOSIT or amount > Config.MAX_DEPOSIT:
        await update.message.reply_text(
            f"❌ Valor deve estar entre R$ {Config.MIN_DEPOSIT:.0f} e R$ {Config.MAX_DEPOSIT:.0f}.\n"
            "Tente novamente:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_CUSTOM_AMOUNT

    await _process_deposit_message(update, update.effective_user, amount)
    return ConversationHandler.END


async def _process_deposit(query, user, amount: float):
    """Processa depósito de valor fixo (via callback)."""
    db_user = db.get_user(user.id)
    unique_id = db_user.referral_code if db_user else f"USR{user.id}"

    # Tenta Mercado Pago, depois Pluggy, depois manual
    result = pix.create_pix(amount, user.id, unique_id)

    if not result:
        # Falhou tudo
        await query.edit_message_text(
            "❌ *Erro ao gerar PIX*\n\n"
            "Não foi possível gerar o pagamento. Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    if result['provider'] == 'manual':
        # PIX manual (chave estática)
        await query.edit_message_text(
            result['instructions'],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    # PIX automático (Mercado Pago ou Pluggy)
    if result.get('qr_code_base64'):
        # Tem QR Code em base64 — podemos tentar mostrar como imagem
        # Por enquanto, mostramos o copia-e-cola
        text = (
            f"💳 *PIX Gerado ({result['provider'].title()})*\n\n"
            f"Valor: *R$ {amount:.2f}*\n\n"
        )
        if result.get('copy_paste'):
            text += (
                f"📋 *Código Copia e Cola:*\n"
                f"`{result['copy_paste']}`\n\n"
            )
        text += (
            f"🔄 Pagamento identificado automaticamente!\n"
            f"O saldo será creditado em até 1 minuto."
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
    elif result.get('copy_paste'):
        text = (
            f"💳 *PIX Gerado ({result['provider'].title()})*\n\n"
            f"Valor: *R$ {amount:.2f}*\n\n"
            f"📋 *Código Copia e Cola:*\n"
            f"`{result['copy_paste']}`\n\n"
            f"🔄 Pagamento identificado automaticamente!\n"
            f"O saldo será creditado em até 1 minuto."
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
    else:
        await query.edit_message_text(
            result['instructions'],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )


async def _process_deposit_message(msg, user, amount: float):
    """Processa depósito de valor personalizado."""
    db_user = db.get_user(user.id)
    unique_id = db_user.referral_code if db_user else f"USR{user.id}"

    # Tenta Mercado Pago, depois Pluggy, depois manual
    result = pix.create_pix(amount, user.id, unique_id)

    if not result:
        await msg.reply_text(
            "❌ *Erro ao gerar PIX*\n\n"
            "Não foi possível gerar o pagamento. Tente novamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if result['provider'] == 'manual':
        await msg.reply_text(
            result['instructions'],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    if result.get('copy_paste'):
        text = (
            f"💳 *PIX Gerado ({result['provider'].title()})*\n\n"
            f"Valor: *R$ {amount:.2f}*\n\n"
            f"📋 *Código Copia e Cola:*\n"
            f"`{result['copy_paste']}`\n\n"
            f"🔄 Pagamento identificado automaticamente!\n"
            f"O saldo será creditado em até 1 minuto."
        )
        await msg.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
    else:
        await msg.reply_text(
            result['instructions'],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )


def get_handlers():
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('depositar', depositar_command),
            CallbackQueryHandler(depositar_callback, pattern='^dep_'),
        ],
        states={
            WAITING_CUSTOM_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_received),
            ],
        },
        fallbacks=[CallbackQueryHandler(depositar_callback, pattern='^depositar$')],
    )

    return [
        conv_handler,
        CallbackQueryHandler(depositar_callback, pattern='^depositar$'),
        CallbackQueryHandler(depositar_callback, pattern='^dep_custom$'),
    ]