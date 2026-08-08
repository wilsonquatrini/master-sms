"""
Teclados inline do bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.pricing import pricing


class Keyboards:
    """Constrói teclados reutilizáveis."""

    @staticmethod
    def main_menu():
        """Menu principal do bot."""
        kb = [
            [InlineKeyboardButton("💰 Ver Saldo", callback_data="saldo")],
            [InlineKeyboardButton("💳 Depositar", callback_data="depositar")],
            [InlineKeyboardButton("📱 Comprar SMS", callback_data="comprar")],
            [InlineKeyboardButton("🌍 Países", callback_data="paises")],
            [InlineKeyboardButton("👥 Indicar Amigos", callback_data="referral")],
            [InlineKeyboardButton("📊 Histórico", callback_data="historico")],
            [InlineKeyboardButton("❓ Ajuda", callback_data="ajuda")],
        ]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def deposit_options():
        kb = [
            [InlineKeyboardButton("💰 R$ 10", callback_data="dep_10"),
             InlineKeyboardButton("💰 R$ 25", callback_data="dep_25")],
            [InlineKeyboardButton("💰 R$ 50", callback_data="dep_50"),
             InlineKeyboardButton("💰 R$ 100", callback_data="dep_100")],
            [InlineKeyboardButton("💰 Outro valor", callback_data="dep_custom")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu")],
        ]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def back():
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data="menu")]]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def back_to(back_callback: str, text: str = "🔙 Voltar"):
        kb = [[InlineKeyboardButton(text, callback_data=back_callback)]]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def countries_list(countries: list, page: int = 0, items_per_page: int = 8):
        """
        Gera teclado de países com paginação.
        countries: list of (code, name, available)
        """
        total_pages = (len(countries) - 1) // items_per_page + 1 if countries else 1
        start = page * items_per_page
        end = start + items_per_page
        page_countries = countries[start:end]

        kb = []
        for code, name, available in page_countries:
            status = "🟢" if available else "⚪"
            flag = pricing.get_country_flag(code)
            kb.append([
                InlineKeyboardButton(
                    f"{status} {flag} {name}",
                    callback_data=f"cntry_{code}"
                )
            ])

        # Paginação
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"cpage_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"cpage_{page+1}"))
        if nav:
            kb.append(nav)

        kb.append([InlineKeyboardButton("🔙 Voltar", callback_data="menu")])
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def country_services(services: list, country_code: str, country_name: str):
        """
        Gera teclado de serviços disponíveis em um país.
        services: list of (code, name, price, available_qty)
        """
        kb = []
        for svc_code, svc_name, price, qty in services:
            if qty > 0:
                btn = InlineKeyboardButton(
                    f"📱 {svc_name} - R$ {price:.2f} ({qty} disp.)",
                    callback_data=f"cntrybuy_{country_code}_{svc_code}"
                )
            else:
                btn = InlineKeyboardButton(
                    f"🔴 {svc_name} - indisponível",
                    callback_data="noop"
                )
            kb.append([btn])

        kb.append([InlineKeyboardButton("🔙 Outro país", callback_data="paises")])
        kb.append([InlineKeyboardButton("🔙 Menu", callback_data="menu")])
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def inline_url(text: str, url: str):
        kb = [[InlineKeyboardButton(text, url=url)]]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def admin_menu():
        kb = [
            [InlineKeyboardButton("📊 Estatísticas", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Usuários", callback_data="admin_users")],
            [InlineKeyboardButton("💰 Preços", callback_data="admin_prices")],
            [InlineKeyboardButton("🏷️ Cupons", callback_data="admin_coupons")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu")],
        ]
        return InlineKeyboardMarkup(kb)

    @staticmethod
    def purchase_services(services: list, page: int = 0, items_per_page: int = 6):
        """
        Gera teclado de serviços com paginação.
        services: list of (code, name, price)
        """
        total_pages = (len(services) - 1) // items_per_page + 1 if services else 1
        start = page * items_per_page
        end = start + items_per_page
        page_services = services[start:end]

        kb = []
        for svc_code, svc_name, svc_price in page_services:
            kb.append([
                InlineKeyboardButton(
                    f"{svc_name} - {svc_price:.2f}",
                    callback_data=f"buy_{svc_code}"
                )
            ])

        # Paginação
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
        if nav:
            kb.append(nav)

        kb.append([InlineKeyboardButton("🔙 Voltar", callback_data="menu")])
        return InlineKeyboardMarkup(kb)