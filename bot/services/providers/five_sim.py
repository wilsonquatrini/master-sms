"""
Provider 5SIM — API REST moderna com JWT.
https://5sim.net
"""

import logging
from typing import Optional, Dict

import requests

from bot.config import Config
from bot.services.providers.base import (
    SMSProvider, ProviderError, InsufficientBalanceError, NoNumbersError,
)

logger = logging.getLogger(__name__)


# Mapeamento de países: código interno (SMS-Activate style) -> ISO alpha-2 (5SIM)
COUNTRY_TO_5SIM = {
    '24': 'br',   # Brasil
    '12': 'us',   # EUA
    '1': 'ru',    # Rússia
    '16': 'gb',   # Reino Unido
    '6': 'ca',    # Canadá
    '22': 'de',   # Alemanha
    '4': 'au',    # Austrália
    '9': 'cn',    # China
    '14': 'in',   # Índia
    '23': 'mx',   # México
    '7': 'cl',    # Chile
    '29': 'ar',   # Argentina
    '25': 'co',   # Colômbia
    '30': 'pe',   # Peru
    '3': 'es',    # Espanha
    '13': 'fr',   # França
    '10': 'it',   # Itália
    '5': 'jp',    # Japão
    '8': 'kr',    # Coreia do Sul
    '2': 'ua',    # Ucrânia
    '15': 'id',   # Indonésia
    '17': 'tr',   # Turquia
    '18': 'vn',   # Vietnã
    '19': 'za',   # África do Sul
    '20': 'pt',   # Portugal
    '21': 'pl',   # Polônia
}

# Reverse mapping: ISO -> código interno
_5SIM_TO_COUNTRY = {v: k for k, v in COUNTRY_TO_5SIM.items()}

# Mapeamento de serviços: código interno -> código 5SIM
# 5SIM usa os mesmos códigos na maioria dos casos
SERVICE_CODE_MAP = {
    'wa': 'wa',      # WhatsApp
    'tg': 'tg',      # Telegram
    'ig': 'ig',      # Instagram
    'fb': 'fb',      # Facebook
    'tw': 'tw',      # Twitter/X
    'tk': 'tk',      # TikTok
    'go': 'go',      # Google
    'mm': 'mm',      # Microsoft
    'am': 'am',      # Amazon
    'pa': 'pa',      # PayPal
    'ap': 'ap',      # Apple
    'sb': 'sb',      # Snapchat
    'tb': 'tb',      # Tinder
    'li': 'li',      # LinkedIn
    'ub': 'ub',      # Uber
    'ds': 'ds',      # Discord
    'ok': 'ok',      # OK.ru
    'vk': 'vk',      # VKontakte
    'ya': 'ya',      # Yandex
    'ot': 'ot',      # Outros
}

# Preços base de referência (USD) para 5SIM
FALLBACK_PRICES = {
    'wa': 0.12, 'tg': 0.10, 'ig': 0.01, 'fb': 0.01, 'tw': 0.12,
    'tk': 0.15, 'go': 0.01, 'mm': 0.20, 'am': 0.25, 'pa': 0.30,
    'ap': 0.35, 'sb': 0.15, 'tb': 0.14, 'li': 0.18, 'ub': 0.20,
    'ds': 0.12, 'ok': 0.12, 'vk': 0.08, 'ya': 0.12, 'ot': 0.15,
}


class FiveSimProvider(SMSProvider):
    """Provider 5SIM — API REST com JWT."""

    def __init__(self):
        self.api_key = Config.FIVESIM_API_KEY
        self.base_url = Config.FIVESIM_BASE_URL
        self._price_cache = {}

    @property
    def name(self) -> str:
        return 'five_sim'

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json',
        }

    def _get(self, path: str) -> Optional[dict]:
        """Faz GET request para a API 5SIM."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 401:
                raise ProviderError("API key do 5SIM inválida")
            if resp.status_code == 402:
                raise InsufficientBalanceError("Saldo insuficiente no 5SIM")
            if resp.status_code == 400:
                data = resp.json()
                if 'no numbers' in str(data).lower():
                    raise NoNumbersError("Sem números disponíveis no 5SIM")
                raise ProviderError(f"5SIM error: {data}")
            resp.raise_for_status()
            return resp.json()
        except (NoNumbersError, InsufficientBalanceError, ProviderError):
            raise
        except requests.exceptions.Timeout:
            raise ProviderError("Timeout na API 5SIM")
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"Erro na API 5SIM: {e}")

    def get_balance(self) -> Optional[float]:
        try:
            data = self._get('/user/profile')
            if data and 'balance' in data:
                return float(data['balance'])
            return None
        except Exception as e:
            logger.error(f"5SIM get_balance error: {e}")
            return None

    def get_number(self, service: str, country: str) -> Optional[Dict]:
        """
        Compra um número no 5SIM.
        Formato: /user/buy/activation/{country}/{operator}/{product}
        Usamos 'any' como operador para pegar o mais barato disponível.
        """
        iso_country = COUNTRY_TO_5SIM.get(country, country)
        product = SERVICE_CODE_MAP.get(service, service)

        try:
            data = self._get(f'/user/buy/activation/{iso_country}/any/{product}')
            if data:
                activation_id = str(data.get('id', ''))
                phone = data.get('phone', '')
                if activation_id and phone:
                    return {
                        'activation_id': activation_id,
                        'phone_number': phone,
                    }
            return None
        except (NoNumbersError, InsufficientBalanceError, ProviderError):
            raise
        except Exception as e:
            logger.error(f"5SIM get_number error: {e}")
            return None

    def get_status(self, activation_id: str) -> Optional[str]:
        """
        Verifica status no 5SIM.
        Pode retornar SMS code através do check endpoint.
        """
        try:
            data = self._get(f'/user/check/{activation_id}')
            if data:
                status = data.get('status', '')
                if status == 'RECEIVED':
                    sms = data.get('sms', [])
                    if sms:
                        return sms[0].get('code', '')
                    return 'RECEIVED'
                elif status == 'FINISHED':
                    return 'CANCELLED'
                elif status in ('CANCELED', 'TIMEOUT'):
                    return 'CANCELLED'
                # PENDING, WAITING_CODE, etc.
                return None
            return None
        except Exception as e:
            logger.error(f"5SIM get_status error: {e}")
            return None

    def set_status(self, activation_id: str, status: int) -> bool:
        """
        5SIM não tem setStatus como SMS-Activate.
        Usamos diferentes endpoints:
        - 1 (finalizar) -> /user/finish/{id}
        - 6 (cancelar) -> /user/cancel/{id}
        - 8 (relatar SMS) -> já recebido automaticamente
        """
        try:
            if status == 6:
                self._get(f'/user/cancel/{activation_id}')
            elif status in (1, 8):
                self._get(f'/user/finish/{activation_id}')
            else:
                return False
            return True
        except Exception as e:
            logger.error(f"5SIM set_status error: {e}")
            return False

    def get_services_by_country(self, country: str) -> Dict[str, int]:
        """5SIM não tem endpoint direto de disponibilidade por país.
        Usamos o endpoint de preços para ver o que está disponível."""
        iso_country = COUNTRY_TO_5SIM.get(country, country)
        try:
            data = self._get(f'/guest/prices?country={iso_country}')
            if data and isinstance(data, dict):
                result = {}
                # A estrutura de resposta é complexa, vamos simplificar
                for our_code, five_code in SERVICE_CODE_MAP.items():
                    if five_code in data:
                        prices = data[five_code]
                        if isinstance(prices, dict):
                            for op, info in prices.items():
                                qty = info.get('count', 0) if isinstance(info, dict) else 0
                                if qty > 0:
                                    result[our_code] = result.get(our_code, 0) + qty
                return result
            return {}
        except Exception as e:
            logger.error(f"5SIM get_services_by_country error: {e}")
            return {}

    def get_countries(self) -> Dict[str, str]:
        """Retorna países que o 5SIM suporta (mesmo mapping)."""
        from bot.services.pricing import COUNTRIES
        # Filtrar apenas países que temos mapeamento
        mapped = {}
        for code, name in COUNTRIES.items():
            if code in COUNTRY_TO_5SIM:
                mapped[code] = name
        return mapped

    def get_price(self, service: str, country: str) -> Optional[float]:
        """
        Obtém o menor preço disponível para um serviço+país.
        5SIM tem preços por operadora — pegamos o menor.
        """
        cache_key = (service, country)
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        iso_country = COUNTRY_TO_5SIM.get(country, country)
        product = SERVICE_CODE_MAP.get(service, service)

        try:
            data = self._get(f'/guest/prices?country={iso_country}&product={product}')
            if data and isinstance(data, dict):
                prices = data.get(product, data)
                if isinstance(prices, dict):
                    min_price = None
                    for op, info in prices.items():
                        if isinstance(info, dict):
                            price = info.get('price', 0)
                            if isinstance(price, (int, float)) and price > 0:
                                if min_price is None or price < min_price:
                                    min_price = price
                    if min_price is not None:
                        self._price_cache[cache_key] = min_price
                        return min_price
        except Exception as e:
            logger.debug(f"5SIM get_price error for {service}/{country}: {e}")

        # Fallback
        price = FALLBACK_PRICES.get(service)
        if price:
            self._price_cache[cache_key] = price
        return price