"""
Handler de compra de SMS.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from bot.database import db
from bot.keyboards import Keyboards
from bot.config import Config
from bot.services.providers import provider_manager
from bot.services.providers.base import ProviderError, InsufficientBalanceError
from bot.services.pricing import pricing
from bot.services.referral import referral_service
from bot.async_utils import run_blocking

logger = logging.getLogger(__name__)

# Cache de serviços para paginação
_services_cache = {}
_SERVICE_PAGE = {}  # user_id -> page


async def comprar_command(update: Update, context: CallbackContext):
    """Handle /comprar — mostra serviços disponíveis."""
    user = update.effective_user
    _SERVICE_PAGE[user.id] = 0

    services = await run_blocking(pricing.get_all_services)
    _services_cache[user.id] = services

    text = (
        "📱 *Comprar Número SMS*\n\n"
        "Escolha o serviço desejado:\n\n"
        "💡 *Preços com markup aplicado*\n"
        "📌 Ao comprar, você receberá um número\n"
        "   e aguardará o SMS de verificação.\n\n"
        "👇 Selecione abaixo:"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.purchase_services(services, 0),
    )


async def comprar_callback(update: Update, context: CallbackContext):
    """Callback do botão comprar."""
    query = update.callback_query
    user = update.effective_user
    data = query.data

    if data == 'comprar':
        services = await run_blocking(pricing.get_all_services)
        _services_cache[user.id] = services
        _SERVICE_PAGE[user.id] = 0

        text = "📱 *Comprar Número SMS*\n\nSelecione o serviço:"
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.purchase_services(services, 0),
        )
        return

    # Paginação
    if data.startswith('page_'):
        page = int(data.split('_')[1])
        _SERVICE_PAGE[user.id] = page
        services = _services_cache.get(user.id)
        if services is None:
            services = await run_blocking(pricing.get_all_services)
            _services_cache[user.id] = services
        await query.edit_message_reply_markup(
            reply_markup=Keyboards.purchase_services(services, page),
        )
        await query.answer(f"Página {page + 1}")
        return

    # Compra de serviço
    if data.startswith('buy_'):
        service_code = data[4:]
        country_code = context.user_data.get('selected_country', Config.DEFAULT_COUNTRY)
        await _process_purchase(query, user, service_code, country_code)


async def _process_purchase(query, user, service_code: str, country_code: str = None):
    """Processa a compra de um SMS."""
    db_user = db.get_user(user.id)

    # Usar país da sessão se não especificado
    if not country_code:
        # Tenta pegar da sessão do usuário (context não disponível aqui)
        country_code = Config.DEFAULT_COUNTRY

    # Verificar se não está banido
    if db_user and db_user.is_banned:
        await query.edit_message_text(
            "❌ Sua conta foi suspensa. Contate o suporte.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    # Calcular preço (rede/DB -> thread para não travar)
    price = await run_blocking(pricing.calculate_price, service_code, country_code)
    service_name = pricing.get_service_name(service_code)
    country_name = pricing.get_country_name(country_code)

    # Verificar saldo
    balance = db_user.balance if db_user else 0
    if balance < price:
        await query.edit_message_text(
            f"❌ *Saldo Insuficiente!*\n\n"
            f"📱 {service_name}: *R$ {price:.2f}*\n"
            f"💰 Seu saldo: *R$ {balance:.2f}*\n\n"
            f"Use /depositar para adicionar créditos.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.deposit_options(),
        )
        return

    # Confirmar compra
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_{service_code}"),
            InlineKeyboardButton("❌ Cancelar", callback_data="comprar"),
        ]
    ]
    await query.edit_message_text(
            f"📱 *Confirmar Compra*\n\n"
            f"🌍 *País:* {country_name}\n"
            f"📱 *Serviço:* {service_name}\n"
            f"💵 *Preço:* R$ {price:.2f}\n"
            f"💰 Saldo após compra: *R$ {balance - price:.2f}*\n\n"
            f"Confirma a compra?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def confirm_purchase(update: Update, context: CallbackContext):
    """Confirma e processa a compra."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    service_code = query.data[8:]  # remove 'confirm_'

    db_user = db.get_user(user.id)
    country_code = context.user_data.get('selected_country', Config.DEFAULT_COUNTRY)
    price = await run_blocking(pricing.calculate_price, service_code, country_code)
    service_name = pricing.get_service_name(service_code)
    country_name = pricing.get_country_name(country_code)

    # Verificar saldo novamente
    if db_user.balance < price:
        await query.edit_message_text(
            "❌ Saldo insuficiente. A compra foi cancelada.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    # Mensagem de "processando"
    await query.edit_message_text(
        f"⏳ *Buscando número para {service_name}...*\n\n"
        f"Aguarde, estamos alocando um número virtual.",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        # Solicitar número — ProviderManager tenta do mais barato primeiro
        result = await run_blocking(provider_manager.get_number, service_code, country_code)

        if not result:
            await query.edit_message_text(
                f"❌ *Número indisponível*\n\n"
                f"Não há números disponíveis para {service_name} em {country_name} no momento.\n"
                f"Tente novamente em alguns instantes.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboards.back(),
            )
            return

        # Registrar compra no banco
        provider_used = result.get('provider', 'desconhecido')
        purchase = db.create_sms_purchase(
            user_id=user.id,
            service=service_code,
            service_name=service_name,
            country=country_code,
            price=price,
            cost=pricing.get_base_price(service_code, country_code),
            provider=provider_used,
        )

        # Atualizar com dados da ativação
        db.update_sms_purchase(
            purchase.id,
            phone_number=result['phone_number'],
            activation_id=result['activation_id'],
            status='waiting_sms',
        )

        # Debitar saldo
        db.update_balance(user.id, -price)
        db.add_transaction(
            user_id=user.id,
            tx_type='purchase',
            amount=-price,
            description=f'Compra SMS {service_name} - {result["phone_number"]}',
            reference_id=result['activation_id'],
        )

        # Atualizar total gasto
        with db.session() as s:
            from bot.database import User
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u:
                u.total_spent = (u.total_spent or 0) + price

        # Comissão de referral
        referral_service.add_purchase_commission(user.id, price)

        # Número recebido — mostrar ao usuário
        phone = result['phone_number']
        formatted_phone = f"+{phone}" if not phone.startswith('+') else phone

        text = (
            f"✅ *Número Alocado!*\n\n"
            f"🌍 *País:* {country_name}\n"
            f"📱 *Serviço:* {service_name}\n"
            f"📞 *Número:* `{formatted_phone}`\n"
            f"💰 *Valor:* R$ {price:.2f}\n\n"
            f"⏳ *Aguardando SMS...*\n\n"
            f"O código será exibido aqui automaticamente.\n"
            f"Tempo médio: 30s a 2 minutos.\n\n"
            f"🔄 *Não recebeu?*\n"
            f"Use o botão abaixo para verificar novamente."
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Verificar SMS", callback_data=f"check_{purchase.id}")],
            [InlineKeyboardButton("📱 Comprar outro", callback_data="comprar")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        # Iniciar verificação automática em background
        asyncio.create_task(
            _wait_for_sms(purchase.id, user.id, context)
        )

    except InsufficientBalanceError as e:
        await query.edit_message_text(
            f"❌ *Saldo insuficiente no fornecedor*\n\n"
            f"{str(e)}\n\n"
            f"Contate o suporte para recarregar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
    except ProviderError as e:
        await query.edit_message_text(
            f"❌ *Erro no fornecedor*\n\n"
            f"{str(e)}\n\n"
            f"Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
    except Exception as e:
        logger.error(f"Purchase error: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ *Erro interno*\n\n"
            "Ocorreu um erro ao processar sua compra.\n"
            "Tente novamente ou contate o suporte.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )


async def check_sms_callback(update: Update, context: CallbackContext):
    """Callback para verificar SMS manualmente."""
    query = update.callback_query
    await query.answer()

    purchase_id = int(query.data.split('_')[1])

    from bot.database import SMSPurchase
    purchase = None
    with db.session() as s:
        purchase = s.query(SMSPurchase).filter_by(id=purchase_id).first()

    if not purchase:
        await query.edit_message_text(
            "❌ Compra não encontrada.",
            reply_markup=Keyboards.back(),
        )
        return

    if purchase.status == 'received':
        await query.edit_message_text(
            f"✅ *SMS Recebido!*\n\n"
            f"📱 *Código:* `{purchase.sms_code}`\n\n"
            f"Use este código para verificar sua conta no {purchase.service_name}.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back(),
        )
        return

    # Verificar na API
    status = await run_blocking(provider_manager.get_status, purchase.activation_id, getattr(purchase, 'provider', None))
    if status and status not in ('CANCELLED', None):
        # SMS recebido!
        db.update_sms_purchase(purchase.id, sms_code=status, status='received')
        sb = purchase
        await query.edit_message_text(
            f"✅ *SMS Recebido!*\n\n"
            f"📱 *Serviço:* {sb.service_name}\n"
            f"📞 *Número:* `{sb.phone_number}`\n"
            f"🔑 *Código:* `{status}`\n\n"
            f"Use este código para verificar sua conta.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.main_menu(),
        )
    else:
        await query.edit_message_text(
            f"⏳ *Aguardando SMS...*\n\n"
            f"Ainda não recebemos o SMS.\n"
            f"Tente novamente em alguns segundos.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Verificar novamente", callback_data=f"check_{purchase.id}"),
                InlineKeyboardButton("🔙 Menu", callback_data="menu"),
            ]]),
        )


async def _wait_for_sms(purchase_id: int, user_id: int, context: CallbackContext):
    """Verifica SMS automaticamente por até 5 minutos."""
    from bot.database import SMSPurchase

    for _ in range(30):  # 30 tentativas a cada 10s = 5 min
        await asyncio.sleep(10)

        with db.session() as s:
            purchase = s.query(SMSPurchase).filter_by(id=purchase_id).first()
            if not purchase or purchase.status == 'received':
                return

        status = await run_blocking(provider_manager.get_status, purchase.activation_id, getattr(purchase, 'provider', None))
        if status and status not in ('CANCELLED', None):
            db.update_sms_purchase(purchase_id, sms_code=status, status='received')

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ *SMS Recebido!*\n\n"
                        f"📱 *Serviço:* {purchase.service_name}\n"
                        f"📞 *Número:* `{purchase.phone_number}`\n"
                        f"🔑 *Código:* `{status}`\n\n"
                        f"Use este código para verificar sua conta."
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            return


def get_handlers():
    return [
        CommandHandler('comprar', comprar_command),
        CallbackQueryHandler(comprar_callback, pattern='^comprar$'),
        CallbackQueryHandler(comprar_callback, pattern='^page_'),
        CallbackQueryHandler(comprar_callback, pattern='^buy_'),
        CallbackQueryHandler(confirm_purchase, pattern='^confirm_'),
        CallbackQueryHandler(check_sms_callback, pattern='^check_'),
    ]