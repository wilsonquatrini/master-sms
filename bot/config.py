"""
Configuração centralizada do Master SMS Bot.
Carrega e valida todas as variáveis de ambiente.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis de ambiente (se existir .env local)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class Config:
    """Configurações do bot — todas via variáveis de ambiente."""

    # ---------- Telegram ----------
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    ADMIN_IDS = [
        int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()
    ]

    # ---------- SMS-Activate ----------
    SMS_ACTIVATE_API_KEY = os.getenv('SMS_ACTIVATE_API_KEY', '')
    SMS_ACTIVATE_BASE_URL = os.getenv(
        'SMS_ACTIVATE_BASE_URL',
        'https://api.sms-activate.org/stubs/handler_api.php',
    )

    # ---------- HeroSMS (sucessor do SMS-Activate) ----------
    HEROSMS_API_KEY = os.getenv('HEROSMS_API_KEY', SMS_ACTIVATE_API_KEY)
    HEROSMS_BASE_URL = os.getenv(
        'HEROSMS_BASE_URL',
        'https://hero-sms.com/stubs/handler_api.php',
    )

    # ---------- 5SIM ----------
    FIVESIM_API_KEY = os.getenv('FIVESIM_API_KEY', '')
    FIVESIM_BASE_URL = os.getenv(
        'FIVESIM_BASE_URL',
        'https://5sim.net/v1',
    )

    # ---------- Multi-provider ----------
    # Providers ativos: separados por vírgula (ex: "hero_sms,five_sim")
    SMS_PROVIDERS = [
        x.strip() for x in os.getenv('SMS_PROVIDERS', 'hero_sms').split(',') if x.strip()
    ]
    DEFAULT_COUNTRY = os.getenv('DEFAULT_COUNTRY', '24')

    # ---------- Banco de Dados ----------
    DATABASE_URL = os.getenv(
        'DATABASE_URL',
        'sqlite:///master_sms.db'
    )

    # ---------- PIX / Mercado Pago (recomendado) ----------
    MERCADO_PAGO_ACCESS_TOKEN = os.getenv('MERCADO_PAGO_ACCESS_TOKEN', '')
    # ---------- PIX / Pluggy (fallback) ----------
    PLUGGY_CLIENT_ID = os.getenv('PLUGGY_CLIENT_ID', '')
    PLUGGY_CLIENT_SECRET = os.getenv('PLUGGY_CLIENT_SECRET', '')
    PLUGGY_API_KEY = os.getenv('PLUGGY_API_KEY', '')
    PLUGGY_RECIPIENT_ID = os.getenv('PLUGGY_RECIPIENT_ID', '')
    PLUGGY_ENVIRONMENT = os.getenv('PLUGGY_ENVIRONMENT', 'production')
    PLUGGY_BASE_URL = (
        'https://api.pluggy.ai'
        if PLUGGY_ENVIRONMENT == 'production'
        else 'https://api.sandbox.pluggy.ai'
    )

    # Fallback manual PIX
    PIX_KEY = os.getenv('PIX_KEY', '')
    PIX_NAME = os.getenv('PIX_NAME', 'Master SMS')
    PIX_CITY = os.getenv('PIX_CITY', 'Sao Paulo')

    # ---------- Depósitos ----------
    MIN_DEPOSIT = float(os.getenv('MIN_DEPOSIT', '5.0'))
    MAX_DEPOSIT = float(os.getenv('MAX_DEPOSIT', '1000.0'))
    CHECK_PAYMENT_INTERVAL = int(os.getenv('CHECK_PAYMENT_INTERVAL', '30'))

    # ---------- Referral (3 níveis) ----------
    REFERRAL_LEVEL_1 = float(os.getenv('REFERRAL_LEVEL_1', '10'))
    REFERRAL_LEVEL_2 = float(os.getenv('REFERRAL_LEVEL_2', '0'))
    REFERRAL_LEVEL_3 = float(os.getenv('REFERRAL_LEVEL_3', '0'))
    REFERRAL_SIGNUP_BONUS = float(os.getenv('REFERRAL_SIGNUP_BONUS', '0'))

    # ---------- Markup (lucro) ----------
    MARKUP_GLOBAL = float(os.getenv('MARKUP_GLOBAL', '100'))
    MARKUP_BY_SERVICE = {}
    for _kv in os.getenv('MARKUP_BY_SERVICE', '').split(','):
        if ':' in _kv:
            _k, _v = _kv.strip().split(':', 1)
            MARKUP_BY_SERVICE[_k] = float(_v)

    MARKUP_BY_COUNTRY = {}
    for _kv in os.getenv('MARKUP_BY_COUNTRY', '').split(','):
        if ':' in _kv:
            _k, _v = _kv.strip().split(':', 1)
            MARKUP_BY_COUNTRY[_k] = float(_v)

    # ---------- Suporte ----------
    SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME', '')

    # ---------- Debug ----------
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

    # ---------- Moeda ----------
    CURRENCY = os.getenv('CURRENCY', 'R$')

    @classmethod
    def validate(cls) -> bool:
        """Valida se variáveis obrigatórias estão configuradas."""
        required = [
            ('TELEGRAM_BOT_TOKEN', cls.TELEGRAM_BOT_TOKEN),
        ]
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(
                f"Variáveis obrigatórias não configuradas: {', '.join(missing)}\n"
                f"Copie .env.example para .env e preencha."
            )

        # Validar que pelo menos um provider SMS tem API key
        if not cls.HEROSMS_API_KEY and not cls.FIVESIM_API_KEY:
            raise ValueError(
                "Nenhum provider SMS configurado! Defina HEROSMS_API_KEY ou FIVESIM_API_KEY no .env"
            )

        # Validar SMS_PROVIDERS
        valid_providers = {'hero_sms', 'five_sim'}
        invalid = [p for p in cls.SMS_PROVIDERS if p not in valid_providers]
        if invalid:
            raise ValueError(
                f"Providers inválidos em SMS_PROVIDERS: {invalid}. Válidos: {valid_providers}"
            )

        return True