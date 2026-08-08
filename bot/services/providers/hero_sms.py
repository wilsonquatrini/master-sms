"""
Provider HeroSMS — API parcialmente compatível com SMS-Activate.
https://hero-sms.com
"""

import json
import logging
import os
import time
from typing import Optional, Dict

import requests

from bot.config import Config
from bot.services.providers.base import (
    SMSProvider, ProviderError, InsufficientBalanceError, NoNumbersError,
)

logger = logging.getLogger(__name__)


# Mapeamento de códigos de serviço internos para códigos do HeroSMS
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

# Mapeamento de países (nosso código interno SMS-Activate -> ID real da HeroSMS)
# IDs confirmados via getCountries da HeroSMS (08/2026)
COUNTRY_CODE_MAP = {
    '24': '73',   # Brasil
    '12': '187',  # EUA
    '16': '16',   # Reino Unido
    '6': '36',    # Canadá
    '22': '43',   # Alemanha
    '4': '175',   # Austrália
    '9': '3',     # China
    '14': '22',   # Índia
    '23': '54',   # México
    '7': '151',   # Chile
    '29': '39',   # Argentina
    '25': '33',   # Colômbia
    '30': '65',   # Peru
    '3': '56',    # Espanha
    '13': '78',   # França
    '10': '86',   # Itália
    '5': '182',   # Japão
    '15': '6',    # Indonésia
    '17': '62',   # Turquia
    '18': '10',   # Vietnã
    '19': '31',   # África do Sul
    '20': '117',  # Portugal
    '21': '15',   # Polônia
    '2': '1',     # Ucrânia
}

# Preços base referenciais (USD) — serão substituídos pela consulta em tempo real
FALLBACK_PRICES = {
    'wa': 0.15, 'tg': 0.12, 'ig': 0.02, 'fb': 0.02, 'tw': 0.15,
    'tk': 0.20, 'go': 0.02, 'mm': 0.25, 'am': 0.30, 'pa': 0.35,
    'ap': 0.40, 'sb': 0.20, 'tb': 0.18, 'li': 0.22, 'ub': 0.25,
    'ds': 0.15, 'ok': 0.15, 'vk': 0.10, 'ya': 0.15, 'ot': 0.20,
}


class HeroSMSProvider(SMSProvider):
    """Provider HeroSMS (ex-SMS-Activate)."""

    def __init__(self):
        self.api_key = Config.HEROSMS_API_KEY
        self.base_url = Config.HEROSMS_BASE_URL
        self.loyalty_discount = Config.LOYALTY_BY_PROVIDER.get('hero_sms', Config.LOYALTY_DISCOUNT)
        # Cache de preços: {(service, country): (timestamp, price_usd)}
        self._price_cache = {}
        # Cache de ações/disponibilidade por país: {country: (timestamp, {svc: qty})}
        self._status_cache = {}
        self._country_names = None  # cache do getCountries
        self._country_names_ts = 0
        # TTL do cache do catálogo (padrão 120s) — reduz chamadas à API em volume
        self.TTL = int(os.getenv('HEROSMS_TTL', '120'))

    @property
    def name(self) -> str:
        return 'hero_sms'

    def _request(self, params: dict) -> str:
        """Faz requisição à API. Retorna texto bruto."""
        params['api_key'] = self.api_key
        try:
            resp = requests.get(self.base_url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.text.strip()
        except requests.exceptions.Timeout:
            logger.error("HeroSMS timeout")
            raise ProviderError("Timeout na API HeroSMS")
        except requests.exceptions.RequestException as e:
            logger.error(f"HeroSMS request error: {e}")
            raise ProviderError(f"Erro na API HeroSMS: {e}")

    def _request_json(self, params: dict) -> Optional[dict]:
        """Faz requisição e tenta parsear JSON."""
        text = self._request(params)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return None

    def get_balance(self) -> Optional[float]:
        try:
            data = self._request_json({'action': 'getBalance'})
            if data and isinstance(data, dict):
                # Pode ser {"title": "...", "details": "..."} com saldo
                if 'balance' in data:
                    return float(data['balance'])
                # Formato: {"title":"ACCESS_BALANCE","details":"123.45"}
                if data.get('title') == 'ACCESS_BALANCE':
                    return float(data['details'])
            # Fallback: formato texto
            text = self._request({'action': 'getBalance'})
            if text.startswith('ACCESS_BALANCE:'):
                return float(text.split(':')[1])
            return None
        except Exception as e:
            logger.error(f"HeroSMS get_balance error: {e}")
            return None

    def get_number(self, service: str, country: str) -> Optional[Dict]:
        hs_service = SERVICE_CODE_MAP.get(service, service)
        hs_country = COUNTRY_CODE_MAP.get(country, country)

        params = {
            'action': 'getNumber',
            'service': hs_service,
            'country': hs_country,
        }
        try:
            text = self._request(params)
            if text.startswith('ACCESS_NUMBER:'):
                parts = text.split(':')
                return {
                    'activation_id': parts[1],
                    'phone_number': parts[2],
                }
            elif text == 'NO_NUMBERS':
                raise NoNumbersError(f"Sem números para {service} em {country}")
            elif text == 'NO_BALANCE':
                raise InsufficientBalanceError("Saldo insuficiente no HeroSMS")
            elif text == 'BAD_KEY':
                raise ProviderError("API key do HeroSMS inválida")
            else:
                # Tentar JSON
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        if data.get('title') == 'BAD_KEY':
                            raise ProviderError("API key do HeroSMS inválida")
                        if data.get('title') == 'NO_NUMBERS':
                            raise NoNumbersError(f"Sem números para {service} em {country}")
                except (json.JSONDecodeError, Exception):
                    pass
                logger.error(f"HeroSMS getNumber unexpected: {text}")
                return None
        except (NoNumbersError, InsufficientBalanceError, ProviderError):
            raise
        except Exception as e:
            logger.error(f"HeroSMS get_number error: {e}")
            return None

    def get_status(self, activation_id: str) -> Optional[str]:
        try:
            text = self._request({'action': 'getStatus', 'id': activation_id})
            if text.startswith('STATUS_OK:'):
                return text.split(':', 1)[1]
            elif text.startswith('STATUS_WAIT_CODE'):
                return None
            elif text.startswith('STATUS_CANCEL'):
                return 'CANCELLED'
            # Tentar JSON
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if data.get('title') == 'STATUS_OK':
                        return data.get('details')
                    if data.get('title') == 'STATUS_WAIT_CODE':
                        return None
            except (json.JSONDecodeError, Exception):
                pass
            return None
        except Exception as e:
            logger.error(f"HeroSMS get_status error: {e}")
            return None

    def set_status(self, activation_id: str, status: int) -> bool:
        try:
            text = self._request({
                'action': 'setStatus',
                'id': activation_id,
                'status': str(status),
            })
            if text.startswith('ACCESS_'):
                return True
            # Tentar JSON
            try:
                data = json.loads(text)
                if isinstance(data, dict) and data.get('title', '').startswith('ACCESS_'):
                    return True
            except (json.JSONDecodeError, Exception):
                pass
            return False
        except Exception as e:
            logger.error(f"HeroSMS set_status error: {e}")
            return False

    def get_services_by_country(self, country: str) -> Dict[str, int]:
        hs_country = COUNTRY_CODE_MAP.get(country, country)
        now = time.time()
        cached = self._status_cache.get(hs_country)
        if cached and now - cached[0] < self.TTL:
            return cached[1]
        try:
            data = self._request_json({
                'action': 'getNumbersStatus',
                'country': hs_country,
            })
            if data and isinstance(data, dict):
                result = {}
                for our_code, hs_code in SERVICE_CODE_MAP.items():
                    qty = data.get(hs_code, 0)
                    if isinstance(qty, (int, float)) and qty > 0:
                        result[our_code] = int(qty)
                self._status_cache[hs_country] = (now, result)
                return result
            return {}
        except Exception as e:
            logger.error(f"HeroSMS get_services_by_country error: {e}")
            return {}

    def get_countries(self) -> Dict[str, str]:
        # HeroSMS usa os mesmos códigos do SMS-Activate
        from bot.services.pricing import COUNTRIES
        return dict(COUNTRIES)

    def get_price(self, service: str, country: str) -> Optional[float]:
        """
        Tenta obter preço real via API. Fallback para tabela.
        Retorna preço em USD.
        """
        cache_key = (service, country)
        now = time.time()
        cached = self._price_cache.get(cache_key)
        if cached and now - cached[0] < self.TTL:
            return cached[1]

        hs_service = SERVICE_CODE_MAP.get(service, service)
        hs_country = COUNTRY_CODE_MAP.get(country, country)

        try:
            data = self._request_json({
                'action': 'getPrices',
                'service': hs_service,
                'country': hs_country,
            })
            if data and isinstance(data, dict):
                # Formato: {"service": {"country": {"price": X, "count": Y}}}
                service_data = data.get(hs_service, {})
                country_data = service_data.get(hs_country, {})
                if isinstance(country_data, dict):
                    price = country_data.get('price')
                    if price:
                        self._price_cache[cache_key] = (now, float(price))
                        return float(price)
        except Exception:
            pass

        # Fallback
        price = FALLBACK_PRICES.get(service)
        if price:
            self._price_cache[cache_key] = (time.time(), price)
        return price