"""
Motor de preços — calcula markup em cima do MAIOR preço entre providers.
Compra executada no MENOR preço (via ProviderManager).
"""

import logging
from typing import Optional

from bot.config import Config
from bot.database import db
from bot.services.providers import provider_manager

logger = logging.getLogger(__name__)


# Preços base dos serviços (fallback, em USD)
# Usados apenas se a consulta ao provider falhar
BASE_PRICES = {
    'wa': 0.20,   # WhatsApp
    'tg': 0.15,   # Telegram
    'ds': 0.18,   # Discord
    'ig': 0.25,   # Instagram
    'fb': 0.20,   # Facebook
    'tw': 0.22,   # Twitter/X
    'tk': 0.30,   # TikTok
    'go': 0.50,   # Google
    'mm': 0.35,   # Microsoft
    'am': 0.40,   # Amazon
    'pa': 0.45,   # PayPal
    'ap': 0.55,   # Apple
    'sb': 0.28,   # Snapchat
    'tb': 0.25,   # Tinder
    'li': 0.30,   # LinkedIn
    'ub': 0.35,   # Uber
    'ok': 0.20,   # OK.ru
    'vk': 0.15,   # VKontakte
    'ya': 0.20,   # Yandex
    'ot': 0.30,   # Outros
}

SERVICE_NAMES = {
    'wa': 'WhatsApp',
    'tg': 'Telegram',
    'ds': 'Discord',
    'ig': 'Instagram',
    'fb': 'Facebook',
    'tw': 'Twitter',
    'tk': 'TikTok',
    'go': 'Google',
    'mm': 'Microsoft',
    'am': 'Amazon',
    'pa': 'PayPal',
    'ap': 'Apple',
    'sb': 'Snapchat',
    'tb': 'Tinder',
    'li': 'LinkedIn',
    'ub': 'Uber',
    'ok': 'OK.ru',
    'vk': 'VKontakte',
    'ya': 'Yandex',
    'ot': 'Outros',
    '99': '99 (Moto/Táxi)',
    'ifood': 'iFood',
}

# Países disponíveis com código ISO
COUNTRIES = {
    '24': 'Brasil',
    '12': 'EUA',
    '16': 'Reino Unido',
    '6': 'Canadá',
    '22': 'Alemanha',
    '4': 'Austrália',
    '9': 'China',
    '14': 'Índia',
    '23': 'México',
    '7': 'Chile',
    '29': 'Argentina',
    '25': 'Colômbia',
    '30': 'Peru',
    '3': 'Espanha',
    '13': 'França',
    '10': 'Itália',
    '5': 'Japão',
    '2': 'Ucrânia',
    '15': 'Indonésia',
    '17': 'Turquia',
    '18': 'Vietnã',
    '19': 'África do Sul',
    '20': 'Portugal',
    '21': 'Polônia',
}

# Taxa de câmbio USD -> BRL
USD_TO_BRL = 5.50

# Bandeiras dos países (emoji) — exibidas na interface, igual ao Notz
COUNTRY_FLAGS = {
    '24': '🇧🇷',  # Brasil
    '12': '🇺🇸',  # EUA
    '16': '🇬🇧',  # Reino Unido
    '6': '🇨🇦',   # Canadá
    '22': '🇩🇪',  # Alemanha
    '4': '🇦🇺',   # Austrália
    '9': '🇨🇳',   # China
    '14': '🇮🇳',  # Índia
    '23': '🇲🇽',  # México
    '7': '🇨🇱',   # Chile
    '29': '🇦🇷',  # Argentina
    '25': '🇨🇴',  # Colômbia
    '30': '🇵🇪',  # Peru
    '3': '🇪🇸',   # Espanha
    '13': '🇫🇷',  # França
    '10': '🇮🇹',  # Itália
    '5': '🇯🇵',   # Japão
    '15': '🇮🇩',  # Indonésia
    '17': '🇹🇷',  # Turquia
    '18': '🇻🇳',  # Vietnã
    '19': '🇿🇦',  # África do Sul
    '20': '🇵🇹',  # Portugal
    '21': '🇵🇱',  # Polônia
    '2': '🇺🇦',   # Ucrânia
}


class PricingEngine:
    """
    Calcula preços de venda.
    Estratégia:
    - Preço de venda (markup) calculado sobre o MAIOR preço base entre os providers
    - Compra executada no MENOR preço (via ProviderManager.get_number)
    """

    def get_base_price(self, service: str, country: str = '24') -> float:
        """
        Retorna o MAIOR preço base (custo) em USD entre todos os providers.
        Usado como base para cálculo do markup.
        """
        max_price = provider_manager.get_max_price(service, country)
        if max_price is not None:
            return max_price
        # Fallback para tabela estática
        return BASE_PRICES.get(service, 0.30)

    def get_min_price(self, service: str, country: str = '24') -> Optional[float]:
        """
        Retorna o MENOR preço disponível (custo) em USD.
        Útil para relatórios/margem de lucro.
        """
        return provider_manager.get_min_price(service, country)

    def get_max_price(self, service: str, country: str = '24') -> Optional[float]:
        """
        Retorna o MAIOR preço disponível (custo) em USD.
        """
        return provider_manager.get_max_price(service, country)

    def get_markup(self, service: str, country: str = '24') -> float:
        """
        Retorna markup (%) para o serviço e país.
        Prioridade: PriceRule no DB > MARKUP_BY_SERVICE > MARKUP_GLOBAL.
        """
        # 1. Verificar regra no DB
        rule = db.get_price_rule(service, country)
        if rule:
            return rule.markup_percent

        # 2. Verificar markup por serviço no config
        if service in Config.MARKUP_BY_SERVICE:
            return Config.MARKUP_BY_SERVICE[service]

        # 3. Verificar markup por país
        if country in Config.MARKUP_BY_COUNTRY:
            return Config.MARKUP_BY_COUNTRY[country]

        # 4. Markup global
        return Config.MARKUP_GLOBAL

    def calculate_price(self, service: str, country: str = '24') -> float:
        """
        Calcula preço de venda em R$.
        preço = (maior_custo_entre_providers) * (1 + markup/100) * taxa_câmbio
        """
        base_cost = self.get_base_price(service, country)
        markup = self.get_markup(service, country)

        price = base_cost * (1 + markup / 100) * USD_TO_BRL

        # Arredondar pra 2 casas decimais (mínimo 1 real)
        price = max(round(price, 2), 1.0)

        return price

    def get_service_name(self, service: str) -> str:
        return SERVICE_NAMES.get(service, service)

    def get_country_name(self, country_code: str) -> str:
        return COUNTRIES.get(country_code, f'Código {country_code}')

    def get_country_flag(self, country_code: str) -> str:
        return COUNTRY_FLAGS.get(country_code, '🌐')

    def get_all_services(self) -> list:
        """Lista de todos os serviços disponíveis."""
        return [(svc, SERVICE_NAMES.get(svc, svc), self.calculate_price(svc))
                for svc in sorted(BASE_PRICES.keys())]

    def get_services_by_country(self, country: str) -> list:
        """
        Lista de serviços disponíveis em um país, com preço e quantidade.
        Usa dados agregados de todos os providers.
        """
        available = provider_manager.get_services_by_country(country)
        result = []
        for svc_code in sorted(BASE_PRICES.keys()):
            svc_name = self.get_service_name(svc_code)
            price = self.calculate_price(svc_code, country)
            qty = available.get(svc_code, 0)
            result.append((svc_code, svc_name, price, qty))
        return result

    def get_provider_details(self, service: str, country: str = '24') -> dict:
        """
        Retorna detalhes de preço por provider para um serviço+país.
        Útil para admin/debug.
        """
        prices = provider_manager.get_all_prices(service, country)
        min_p = provider_manager.get_min_price(service, country)
        max_p = provider_manager.get_max_price(service, country)
        return {
            'prices_by_provider': prices,
            'min_price_usd': min_p,
            'max_price_usd': max_p,
            'sell_price_brl': self.calculate_price(service, country),
            'markup': self.get_markup(service, country),
        }


# Singleton
pricing = PricingEngine()