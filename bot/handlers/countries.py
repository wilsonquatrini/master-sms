"""
Handler de Países e Serviços — mostra países disponíveis e serviços por país.
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from bot.database import db
from bot.keyboards import Keyboards
from bot.services.pricing import pricing, COUNTRIES
from bot.services.providers import provider_manager
from bot.async_utils import run_blocking

logger = logging.getLogger(__name__)

# Cache de países por usuário (para paginação)
_COUNTRY_PAGE = {}  # user_id -> page
_COUNTRY_LIST_CACHE = {}  # user_id -> [(code, name, available), ...]


async def paises_command(update: Update, context: CallbackContext):
    """Handle /paises — mostra lista de países com disponibilidade."""
    user = update.effective_user
    _COUNTRY_PAGE[user.id] = 0

    await _show_countries(update.message.reply_text, user, context)


async def paises_callback(update: Update, context: CallbackContext):
    """Callback do botão de países."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    _COUNTRY_PAGE[user.id] = 0

    await _show_countries(query.edit_message_text, user, context)


async def _show_countries(reply_func, user, context: CallbackContext):
    """Monta e exibe a lista de países com disponibilidade."""
    # Buscar disponibilidade de todos os países
    countries_with_status = []

    # Montar lista com verificação de disponibilidade
    for code, name in sorted(COUNTRIES.items(), key=lambda x: x[1]):
        available = None  # None = não verificado
        countries_with_status.append((code, name, available))

    # Cache para evitar re-consultar
    _COUNTRY_LIST_CACHE[user.id] = countries_with_status

    page = _COUNTRY_PAGE.get(user.id, 0)
    text = (
        "🌍 *Países Disponíveis*\\n\\n"
        "Selecione um país para ver os serviços disponíveis:\\n"
        "🟢 = tem números disponíveis\\n"
        "⚪ = disponibilidade não verificada\\n\\n"
        f"*País atual:* {pricing.get_country_flag(context.user_data.get('selected_country', '24'))} {pricing.get_country_name(context.user_data.get('selected_country', '24'))}\n"
        f"*Total de países:* {len(countries_with_status)}"
    )

    await reply_func(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.countries_list(countries_with_status, page),
    )


async def country_page_callback(update: Update, context: CallbackContext):
    """Paginação da lista de países."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    page = int(query.data.split('_')[1])
    _COUNTRY_PAGE[user.id] = page

    countries = _COUNTRY_LIST_CACHE.get(user.id, [])
    if not countries:
        # Recarregar
        for code, name in sorted(COUNTRIES.items(), key=lambda x: x[1]):
            countries.append((code, name, None))
        _COUNTRY_LIST_CACHE[user.id] = countries

    await query.edit_message_reply_markup(
        reply_markup=Keyboards.countries_list(countries, page),
    )


FEATURED_SERVICES = ['wa', 'tg', 'ub', '99', 'ifood']  # WhatsApp, Telegram, Uber, 99, iFood (1ª página)


def _build_country_services(country_code: str):
    """Síncrono: consulta disponibilidade + preços de um país (roda em thread)."""
    try:
        status = provider_manager.get_services_by_country(country_code)
    except Exception:
        status = {}
    status = status or {}

    # Códigos = serviços conhecidos (BASE_PRICES) + disponíveis no provider (catálogo dinâmico)
    all_codes = set(pricing.BASE_PRICES.keys()) | set(status.keys())

    def order_key(code):
        if code in FEATURED_SERVICES:
            return FEATURED_SERVICES.index(code)
        return len(FEATURED_SERVICES) + sorted(all_codes).index(code)

    services_list = []
    for svc_code in sorted(all_codes, key=order_key):
        svc_name = pricing.get_service_name(svc_code)
        try:
            price = pricing.calculate_price(svc_code, country_code)
        except Exception:
            price = 0.0
        qty = status.get(svc_code, 0)
        services_list.append((svc_code, svc_name, price, qty))
    return status, services_list


async def country_selected_callback(update: Update, context: CallbackContext):
    """Callback quando um país é selecionado — mostra serviços disponíveis."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    # Extrair código do país: cntry_24, cntry_12, etc.
    country_code = query.data.split('_')[1]
    country_name = pricing.get_country_name(country_code)

    # Salvar país selecionado na sessão do usuário
    context.user_data['selected_country'] = country_code

    # Consultar disponibilidade + preços (bloqueante) em thread única
    status, services_list = await run_blocking(_build_country_services, country_code)

    # Contar quantos disponíveis
    available_count = sum(1 for _, _, _, q in services_list if q > 0)
    total_count = len(services_list)

    text = (
        f"🌍 {pricing.get_country_flag(country_code)} *{country_name}*\n\n"
        f"📱 *Serviços disponíveis:* {available_count}/{total_count}\\n"
        f"💰 *Moeda:* R$ (BRL)\\n\\n"
        f"👇 Selecione o serviço desejado:\\n"
        f"📱 = Disponível  |  🔴 = Indisponível no momento"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.country_services(services_list, country_code, country_name),
    )


async def country_buy_callback(update: Update, context: CallbackContext):
    """Callback de compra a partir da tela de países."""
    query = update.callback_query
    await query.answer()

    # Formato: cntrybuy_{country_code}_{service_code}
    parts = query.data.split('_')
    country_code = parts[1]
    service_code = parts[2]

    # Salvar país na sessão
    context.user_data['selected_country'] = country_code

    # Redirecionar para o fluxo de compra
    # Importa o módulo de compra para reutilizar a lógica
    from bot.handlers.purchase import _process_purchase
    await _process_purchase(query, update.effective_user, service_code, country_code)


def get_handlers():
    return [
        CommandHandler('paises', paises_command),
        CallbackQueryHandler(paises_callback, pattern='^paises$'),
        CallbackQueryHandler(country_page_callback, pattern='^cpage_'),
        CallbackQueryHandler(country_selected_callback, pattern='^cntry_[a-zA-Z0-9]+$'),
        CallbackQueryHandler(country_buy_callback, pattern='^cntrybuy_'),
    ]