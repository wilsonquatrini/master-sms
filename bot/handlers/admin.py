"""
Handler de admin — gestão completa do bot.
"""

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from bot.database import db
from bot.keyboards import Keyboards
from bot.config import Config
from bot.services.providers import provider_manager
from bot.services.pricing import pricing
from bot.async_utils import run_blocking

logger = logging.getLogger(__name__)

# Estados da conversa
WAITING_BROADCAST_TEXT = 1

# Cache temporário para fluxos
_admin_ctx = {}


def is_admin(user_id: int) -> bool:
    """Verifica se usuário é admin. ADMIN_IDS sempre concede admin."""
    # Sempre concede admin se o ID estiver na lista de administradores (env)
    if user_id in Config.ADMIN_IDS:
        return True
    user = db.get_user(user_id)
    return user.is_admin if user else False


async def admin_command(update: Update, context: CallbackContext):
    """Handle /admin — menu admin."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            "❌ Acesso negado. Você não é administrador.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    stats = await run_blocking(db.get_stats)

    text = (
        "👨‍💼 *Painel do Administrador*\n\n"
        f"👥 Usuários: *{stats['total_users']}*\n"
        f"💰 Saldo total (positivo): *R$ {stats['total_balance']:.2f}*\n"
        f"📱 Vendas hoje: *{stats['today_sales']}*\n"
        f"💵 Receita hoje: *R$ {stats['today_revenue']:.2f}*\n"
        f"📊 Total vendas: *{stats['total_sales']}*\n"
        f"💎 Receita total: *R$ {stats['total_revenue']:.2f}*\n\n"
        f"Selecione uma opção:"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


async def admin_stats_callback(update: Update, context: CallbackContext):
    """Mostra estatísticas detalhadas."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    # Chamadas bloqueantes (DB/API) rodam em thread p/ não travar o bot
    stats = await asyncio.to_thread(db.get_stats)
    try:
        balances = await asyncio.to_thread(provider_manager.get_balance)
    except Exception as e:
        logger.error(f"get_balance error: {e}", exc_info=True)
        balances = {}
    total_provider_balance = sum(b for b in balances.values() if b is not None)

    text = (
        "📊 *Estatísticas*\n\n"
        f"👥 *Usuários*\n"
        f"• Total: {stats['total_users']}\n"
        f"• Saldo positivo: R$ {stats['total_balance']:.2f}\n\n"
        f"📱 *Vendas*\n"
        f"• Hoje: {stats['today_sales']} (R$ {stats['today_revenue']:.2f})\n"
        f"• Total: {stats['total_sales']} (R$ {stats['total_revenue']:.2f})\n\n"
        f"🏦 *Fornecedores (saldo USD)*\n"
    )
    for provider_name, bal in balances.items():
        bal_str = f"${bal:.2f}" if bal is not None else "❌ erro"
        text += f"• {provider_name}: *{bal_str}*\n"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


def _build_admin_prices_text() -> str:
    """Síncrono: monta texto de preços (roda em thread — chama API)."""
    rules = db.get_all_price_rules()

    text = (
        "💰 *Gestão de Preços*\n\n"
        f"Markup global: *{Config.MARKUP_GLOBAL:.0f}%*\n\n"
        f"📋 *Markups específicos:*\n"
    )

    if rules:
        for r in rules:
            name = pricing.get_service_name(r.service)
            text += f"• {name}: *{r.markup_percent:.0f}%*\n"
    else:
        text += "• Nenhuma regra específica (usando global)\n"

    text += (
        f"\n📱 *Exemplo de preços:*\n"
        f"• WhatsApp: R$ {pricing.calculate_price('wa'):.2f}\n"
        f"• Telegram: R$ {pricing.calculate_price('tg'):.2f}\n"
        f"• Instagram: R$ {pricing.calculate_price('ig'):.2f}\n"
        f"• Google: R$ {pricing.calculate_price('go'):.2f}\n\n"
        f"Use /preco <servico> <markup%> para definir\n"
        f"Ex: `/preco wa 150` (WhatsApp com 150% de markup)"
    )
    return text


async def admin_prices_callback(update: Update, context: CallbackContext):
    """Mostra gestão de preços."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    text = await run_blocking(_build_admin_prices_text)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back_to("admin"),
    )


async def set_price_command(update: Update, context: CallbackContext):
    """Define markup específico para serviço. Uso: /preco wa 150"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Uso: `/preco <servico> <markup%>`\n"
            "Ex: `/preco wa 150`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    service = args[0].lower()
    try:
        markup = float(args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Markup inválido. Use número: `/preco wa 150`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    db.set_price_rule(service, markup)
    name = pricing.get_service_name(service)
    new_price = await run_blocking(pricing.calculate_price, service)

    await update.message.reply_text(
        f"✅ *Preço atualizado!*\n\n"
        f"📱 {name}: markup *{markup:.0f}%*\n"
        f"💵 Novo preço: *R$ {new_price:.2f}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


async def admin_users_callback(update: Update, context: CallbackContext):
    """Lista usuários (página 1)."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    users = db.get_all_users()[:10]

    text = "👥 *Usuários (últimos 10)*\n\n"
    for u in users:
        admin_flag = "👑" if u.is_admin else ""
        ban_flag = "⛔" if u.is_banned else ""
        text += (
            f"{admin_flag}{ban_flag} `{u.telegram_id}` - {u.first_name or '?'}\n"
            f"   💰 R$ {u.balance:.2f} | 📱 {u.total_spent:.2f} gasto\n"
        )

    text += (
        f"\n\nTotal: {db.get_user_count()} usuários\n"
        f"\nComandos:\n"
        f"• `/user <id>` - detalhes\n"
        f"• `/saldo <id> <valor>` - ajustar saldo\n"
        f"• `/ban <id>` - banir\n"
        f"• `/unban <id>` - desbanir"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back_to("admin"),
    )


async def user_info_command(update: Update, context: CallbackContext):
    """Mostra detalhes de um usuário. Uso: /user <id>"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Uso: `/user <telegram_id>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.", parse_mode=ParseMode.MARKDOWN)
        return

    target = db.get_user(target_id)
    if not target:
        await update.message.reply_text(
            f"❌ Usuário `{target_id}` não encontrado.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    purchases = db.get_user_purchases(target_id, 5)

    text = (
        f"👤 *Usuário*\n\n"
        f"ID: `{target.telegram_id}`\n"
        f"Nome: {target.first_name or '?'}\n"
        f"Username: @{target.username or '?'}\n"
        f"💰 Saldo: *R$ {target.balance:.2f}*\n"
        f"📱 Total gasto: R$ {target.total_spent:.2f}\n"
        f"👥 Indicou: {db.get_referral_count(target_id)['1']} diretos\n"
        f"👑 Admin: {'Sim' if target.is_admin else 'Não'}\n"
        f"⛔ Banido: {'Sim' if target.is_banned else 'Não'}\n"
        f"🕐 Criado: {target.created_at.strftime('%d/%m/%Y')}\n\n"
        f"📱 *Últimas compras:*\n"
    )

    if purchases:
        for p in purchases:
            text += f"• {p.service_name} - R$ {p.price:.2f} ({p.status})\n"
    else:
        text += "• Nenhuma compra\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def adjust_balance_command(update: Update, context: CallbackContext):
    """Ajusta saldo de usuário. Uso: /saldo <id> <valor>"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Uso: `/saldo <id> <valor>`\n"
            "Ex: `/saldo 123456 50` (adiciona 50)\n"
            "Ex: `/saldo 123456 -50` (remove 50)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        target_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Argumentos inválidos.", parse_mode=ParseMode.MARKDOWN)
        return

    target = db.get_user(target_id)
    if not target:
        await update.message.reply_text(
            f"❌ Usuário `{target_id}` não encontrado.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    new_balance = db.update_balance(target_id, amount)
    db.add_transaction(
        user_id=target_id,
        tx_type='deposit' if amount > 0 else 'refund',
        amount=amount,
        description=f'Ajuste manual pelo admin',
    )

    await update.message.reply_text(
        f"✅ *Saldo ajustado!*\n\n"
        f"👤 Usuário: `{target_id}`\n"
        f"💰 Alteração: *R$ {amount:.2f}*\n"
        f"💵 Novo saldo: *R$ {new_balance:.2f}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


async def ban_command(update: Update, context: CallbackContext):
    """Bane usuário. Uso: /ban <id>"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Uso: `/ban <id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.", parse_mode=ParseMode.MARKDOWN)
        return

    if target_id in Config.ADMIN_IDS:
        await update.message.reply_text("❌ Não é possível banir um admin.", parse_mode=ParseMode.MARKDOWN)
        return

    db.ban_user(target_id, True)
    await update.message.reply_text(
        f"⛔ Usuário `{target_id}` banido com sucesso!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def unban_command(update: Update, context: CallbackContext):
    """Desbane usuário. Uso: /unban <id>"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Uso: `/unban <id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.", parse_mode=ParseMode.MARKDOWN)
        return

    db.ban_user(target_id, False)
    await update.message.reply_text(
        f"✅ Usuário `{target_id}` desbanido!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def admin_broadcast_callback(update: Update, context: CallbackContext):
    """Inicia broadcast."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    await query.edit_message_text(
        "📢 *Broadcast*\n\n"
        "Digite a mensagem que será enviada para todos os usuários:\n\n"
        "Exemplo:\n"
        "🔥 *PROMOÇÃO!* Cupom MASTER10\n"
        "adiciona R$ 10 de bônus!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back_to("admin"),
    )
    _admin_ctx[user.id] = 'broadcast'
    return WAITING_BROADCAST_TEXT


async def broadcast_text_received(update: Update, context: CallbackContext):
    """Recebe texto do broadcast e envia."""
    user = update.effective_user
    if _admin_ctx.get(user.id) != 'broadcast':
        return ConversationHandler.END

    message_text = update.message.text
    users = db.get_all_users()

    sent = 0
    failed = 0

    status_msg = await update.message.reply_text(
        f"📤 Enviando para {len(users)} usuários...",
        parse_mode=ParseMode.MARKDOWN,
    )

    for u in users:
        if u.is_banned:
            continue
        try:
            await context.bot.send_message(
                chat_id=u.telegram_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ *Broadcast concluído!*\n\n"
        f"📤 Enviadas: *{sent}*\n"
        f"❌ Falhas: *{failed}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )

    _admin_ctx.pop(user.id, None)
    return ConversationHandler.END


async def admin_coupons_callback(update: Update, context: CallbackContext):
    """Menu de cupons."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    coupons = db.get_active_coupons()

    text = "🏷️ *Cupons Ativos*\n\n"
    if coupons:
        for c in coupons:
            text += f"• `{c.code}` - {c.discount_percent:.0f}% (usos: {c.current_uses}"
            if c.max_uses:
                text += f"/{c.max_uses}"
            text += ")\n"
    else:
        text += "• Nenhum cupom ativo\n"

    text += (
        f"\nComando para criar:\n"
        f"`/cupom_novo <codigo> <valor>`\n"
        f"Ex: `/cupom_novo MASTER10 10`\n"
        f"(dá R$ 10 de bônus)"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.back_to("admin"),
    )


async def create_coupon_command(update: Update, context: CallbackContext):
    """Cria cupom. Uso: /cupom_novo <codigo> <valor>"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Uso: `/cupom_novo <codigo> <valor>`\n"
            "Ex: `/cupom_novo MASTER10 10`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    code = args[0].upper()
    try:
        value = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Valor inválido.", parse_mode=ParseMode.MARKDOWN)
        return

    existing = db.get_coupon(code)
    if existing:
        await update.message.reply_text(
            f"❌ Cupom `{code}` já existe.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    db.create_coupon(
        code=code,
        discount_percent=value,
        max_uses=None,
        min_purchase=0,
        created_by=user.id,
    )

    await update.message.reply_text(
        f"✅ *Cupom criado!*\n\n"
        f"🏷️ Código: `{code}`\n"
        f"💰 Valor: *R$ {value:.2f}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


async def admin_back_callback(update: Update, context: CallbackContext):
    """Volta ao menu admin."""
    query = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("Acesso negado")
        return
    await query.answer()

    stats = await run_blocking(db.get_stats)
    text = (
        "👨‍💼 *Painel do Administrador*\n\n"
        f"👥 Usuários: *{stats['total_users']}*\n"
        f"📱 Vendas hoje: *{stats['today_sales']}*\n"
        f"💵 Receita hoje: *R$ {stats['today_revenue']:.2f}*\n\n"
        f"Selecione uma opção:"
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.admin_menu(),
    )


async def noop(update: Update, context: CallbackContext):
    pass


def get_handlers():
    conv_broadcast = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_broadcast_callback, pattern='^admin_broadcast$'),
        ],
        states={
            WAITING_BROADCAST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text_received),
            ],
        },
        fallbacks=[CommandHandler('cancelar', noop)],
    )

    return [
        CommandHandler('admin', admin_command),
        CommandHandler('preco', set_price_command),
        CommandHandler('user', user_info_command),
        CommandHandler('saldo', adjust_balance_command),
        CommandHandler('ban', ban_command),
        CommandHandler('unban', unban_command),
        CommandHandler('cupom_novo', create_coupon_command),
        CallbackQueryHandler(admin_stats_callback, pattern='^admin_stats$'),
        CallbackQueryHandler(admin_prices_callback, pattern='^admin_prices$'),
        CallbackQueryHandler(admin_users_callback, pattern='^admin_users$'),
        CallbackQueryHandler(admin_coupons_callback, pattern='^admin_coupons$'),
        CallbackQueryHandler(admin_back_callback, pattern='^admin$'),
        conv_broadcast,
    ]