"""
Handler de /start e boas-vindas.
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from bot.database import db
from bot.keyboards import Keyboards
from bot.services.referral import referral_service

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: CallbackContext):
    """Handle /start — cria usuário e mostra boas-vindas."""
    user = update.effective_user
    args = context.args

    # Criar/obter usuário
    db_user = db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    # Verificar se veio com código de referral
    if args and args[0]:
        referral_code = args[0].strip().upper()
        result = referral_service.process_referral(user.id, referral_code)
        if result['success']:
            await update.message.reply_text(
                f"🎉 {result['message']}",
                parse_mode=ParseMode.MARKDOWN,
            )

    # Nível de fidelidade
    # Simples: baseado no total gasto
    level_info = ""
    if db_user.total_spent >= 1000:
        level_info = "💎 *Platinum*"
    elif db_user.total_spent >= 500:
        level_info = "🥇 *Gold*"
    elif db_user.total_spent >= 100:
        level_info = "🥈 *Silver*"
    else:
        level_info = "🥉 *Bronze*"

    welcome = (
        f"🎉 *Bem-vindo ao Master SMS!*\n\n"
        f"Olá {user.first_name}! 👋\n\n"
        f"Aqui você pode comprar números temporários para receber "
        f"SMS de verificação dos principais serviços:\n"
        f"📱 WhatsApp, Telegram, Instagram, TikTok, Google e muito mais!\n\n"
        f"💰 *Seu Saldo:* R$ {db_user.balance:.2f}\n"
        f"🏆 *Nível:* {level_info}\n\n"
        f"📌 *Como funciona:*\n"
        f"1️⃣ Faça um depósito via PIX\n"
        f"2️⃣ Escolha o país desejado 🌍\n"
        f"3️⃣ Selecione o serviço\n"
        f"4️⃣ Receba o número e aguarde o SMS\n"
        f"5️⃣ Pronto! Verificação concluída ✅\n\n"
        f"Use os botões abaixo para navegar 👇"
    )

    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu(),
    )


async def menu_callback(update: Update, context: CallbackContext):
    """Callback do menu principal (botão Voltar)."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = db.get_user(user.id)

    welcome = (
        f"🏠 *Menu Principal*\n\n"
        f"💰 Saldo: R$ {db_user.balance:.2f}\n"
        f"👤 ID: {user.id}\n\n"
        f"Escolha uma opção:"
    )

    await query.edit_message_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu(),
    )


async def noop_callback(update: Update, context: CallbackContext):
    """Callback vazio para botões de navegação."""
    await update.callback_query.answer()


async def help_command(update: Update, context: CallbackContext):
    """Handle /ajuda."""
    user = update.effective_user
    help_text = (
        "❓ *Ajuda - Master SMS*\n\n"
        "📌 *Comandos:*\n"
        "/start - Menu principal\n"
        "/saldo - Ver saldo\n"
        "/depositar - Recarregar via PIX\n"
        "/comprar - Comprar número SMS\n"
        "/paises - Ver países disponíveis\n"
        "/indicar - Sistema de indicação\n"
        "/historico - Histórico de compras\n"
        "/cupom - Usar cupom de desconto\n"
        "/ajuda - Esta mensagem\n\n"
        "💡 *Dicas:*\n"
        "• Indique amigos e ganhe comissão em 3 níveis!\n"
        "• Quanto mais compra, maior seu nível de fidelidade\n"
        "• Tempo médio de recebimento do SMS: 30s-2min\n"
    )
    if Config.SUPPORT_USERNAME:
        help_text += f"\n📞 *Suporte:* @{Config.SUPPORT_USERNAME}"

    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back(),
    )


from bot.config import Config


def get_handlers():
    return [
        CommandHandler('start', start_command),
        CommandHandler('ajuda', help_command),
        CallbackQueryHandler(menu_callback, pattern='^menu$'),
        CallbackQueryHandler(noop_callback, pattern='^noop$'),
    ]