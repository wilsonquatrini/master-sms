"""
ProviderManager — orquestra múltiplos providers com fallback e lógica de preço.

Estratégia de preço (conforme Wilson):
- Preço de venda (markup) calculado sobre o MAIOR preço entre os providers
- Compra executada no provider de MENOR preço
- Se um provider falha (sem números), tenta o próximo
"""

import logging
from typing import Optional, Dict, List, Tuple

from bot.config import Config
from bot.services.providers.base import (
    SMSProvider, ProviderError, InsufficientBalanceError, NoNumbersError,
)

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Gerencia múltiplos providers de SMS.
    Ordem de tentativa: mais barato primeiro (para compra).
    """

    def __init__(self):
        self._providers: List[SMSProvider] = []
        self._initialized = False

    def init_providers(self):
        """Inicializa providers baseado na configuração."""
        if self._initialized:
            return

        providers_enabled = Config.SMS_PROVIDERS

        if 'hero_sms' in providers_enabled and Config.HEROSMS_API_KEY:
            from bot.services.providers.hero_sms import HeroSMSProvider
            self._providers.append(HeroSMSProvider())
            logger.info("Provider HeroSMS ativado")

        if 'five_sim' in providers_enabled and Config.FIVESIM_API_KEY:
            from bot.services.providers.five_sim import FiveSimProvider
            self._providers.append(FiveSimProvider())
            logger.info("Provider 5SIM ativado")

        if not self._providers:
            logger.warning("Nenhum provider configurado! Verifique SMS_PROVIDERS e as chaves de API.")

        self._initialized = True

    @property
    def providers(self) -> List[SMSProvider]:
        """Lista de providers ativos."""
        self.init_providers()
        return self._providers

    def get_balance(self) -> Dict[str, Optional[float]]:
        """Saldo de cada provider."""
        return {p.name: p.get_balance() for p in self.providers}

    def get_total_balance(self) -> float:
        """Saldo total somado de todos os providers."""
        total = 0.0
        for p in self.providers:
            bal = p.get_balance()
            if bal is not None:
                total += bal
        return total

    # ----- Preços -----

    def get_all_prices(self, service: str, country: str) -> Dict[str, Optional[float]]:
        """Preço de cada provider para um serviço+país (USD)."""
        return {p.name: p.get_price(service, country) for p in self.providers}

    def get_min_price(self, service: str, country: str) -> Optional[float]:
        """Menor preço disponível (USD) — usado para COMPRA."""
        prices = self.get_all_prices(service, country)
        valid = [v for v in prices.values() if v is not None]
        return min(valid) if valid else None

    def get_max_price(self, service: str, country: str) -> Optional[float]:
        """Maior preço disponível (USD) — usado para MARKUP."""
        prices = self.get_all_prices(service, country)
        valid = [v for v in prices.values() if v is not None]
        return max(valid) if valid else None

    def get_best_provider(self, service: str, country: str) -> Tuple[Optional[SMSProvider], Optional[float]]:
        """
        Retorna o (provider, preço) mais barato para um serviço+país.
        Providers são ordenados por preço (menor primeiro).
        """
        prices = []
        for p in self.providers:
            price = p.get_price(service, country)
            if price is not None:
                prices.append((price, p))

        if not prices:
            return None, None

        prices.sort(key=lambda x: x[0])  # menor preço primeiro
        return prices[0][1], prices[0][0]

    # ----- Compra com fallback -----

    def get_number(self, service: str, country: str) -> Optional[Dict]:
        """
        Compra um número tentando providers do mais barato ao mais caro.
        Se um falha (sem números), tenta o próximo.
        """
        errors = []

        # 1. Tentar do mais barato primeiro
        providers_sorted = self._get_providers_sorted_by_price(service, country)

        if not providers_sorted:
            providers_sorted = self.providers

        for provider in providers_sorted:
            try:
                logger.info(f"Tentando comprar {service}/{country} via {provider.name}")
                result = provider.get_number(service, country)
                if result:
                    result['provider'] = provider.name
                    logger.info(f"Compra bem-sucedida via {provider.name}: {result['phone_number']}")
                    return result
            except NoNumbersError as e:
                logger.warning(f"{provider.name}: sem números - {e}")
                errors.append(f"{provider.name}: sem números")
                continue
            except InsufficientBalanceError as e:
                logger.warning(f"{provider.name}: saldo insuficiente - {e}")
                errors.append(f"{provider.name}: saldo insuficiente")
                continue
            except ProviderError as e:
                logger.error(f"{provider.name}: erro - {e}")
                errors.append(f"{provider.name}: {e}")
                continue
            except Exception as e:
                logger.error(f"{provider.name}: erro inesperado - {e}")
                errors.append(f"{provider.name}: erro interno")
                continue

        logger.error(f"Todos os providers falharam para {service}/{country}: {errors}")
        return None

    def get_status(self, activation_id: str, provider_name: str = None) -> Optional[str]:
        """
        Verifica status de uma ativação.
        Se provider_name for especificado, usa aquele provider.
        Caso contrário, tenta todos.
        """
        if provider_name:
            provider = self._get_provider(provider_name)
            if provider:
                return provider.get_status(activation_id)
            return None

        for p in self.providers:
            try:
                result = p.get_status(activation_id)
                if result:
                    return result
            except Exception:
                continue
        return None

    def set_status(self, activation_id: str, status: int, provider_name: str = None) -> bool:
        """Altera status de uma ativação."""
        if provider_name:
            provider = self._get_provider(provider_name)
            if provider:
                return provider.set_status(activation_id, status)
            return False

        for p in self.providers:
            try:
                if p.set_status(activation_id, status):
                    return True
            except Exception:
                continue
        return False

    # ----- Disponibilidade -----

    def get_services_by_country(self, country: str) -> Dict[str, int]:
        """
        Serviços disponíveis em um país (agregado de todos providers).
        """
        aggregated = {}
        for p in self.providers:
            try:
                services = p.get_services_by_country(country)
                for svc, qty in services.items():
                    aggregated[svc] = aggregated.get(svc, 0) + qty
            except Exception:
                continue
        return aggregated

    def get_countries(self) -> Dict[str, str]:
        """Países suportados (unindo todos providers)."""
        all_countries = {}
        for p in self.providers:
            try:
                all_countries.update(p.get_countries())
            except Exception:
                continue
        return all_countries

    # ----- Helpers internos -----

    def _get_provider(self, name: str) -> Optional[SMSProvider]:
        """Retorna provider pelo nome."""
        for p in self.providers:
            if p.name == name:
                return p
        return None

    def _get_providers_sorted_by_price(self, service: str, country: str) -> List[SMSProvider]:
        """Providers ordenados do menor preço para o maior."""
        prices = []
        for p in self.providers:
            price = p.get_price(service, country)
            if price is not None:
                prices.append((price, p))
            else:
                prices.append((float('inf'), p))

        prices.sort(key=lambda x: x[0])
        return [p for _, p in prices]


# Singleton
provider_manager = ProviderManager()