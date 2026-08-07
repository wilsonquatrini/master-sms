"""
Provider base — interface comum para todos os fornecedores de SMS.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple


class SMSProvider(ABC):
    """Interface que todo provider de SMS deve implementar."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do provider (ex: 'hero_sms', 'five_sim')."""
        ...

    @abstractmethod
    def get_balance(self) -> Optional[float]:
        """Saldo disponível em USD. Retorna None se erro."""
        ...

    @abstractmethod
    def get_number(self, service: str, country: str) -> Optional[Dict]:
        """
        Solicita um número para ativação.
        Retorna {'activation_id': str, 'phone_number': str} ou None.
        """
        ...

    @abstractmethod
    def get_status(self, activation_id: str) -> Optional[str]:
        """
        Verifica status da ativação.
        Retorna o código SMS se recebido, None se aguardando, 'CANCELLED' se cancelado.
        """
        ...

    @abstractmethod
    def set_status(self, activation_id: str, status: int) -> bool:
        """
        Altera status: 1=finalizar, 6=cancelar, 8=relatar SMS recebido.
        Retorna True se sucesso.
        """
        ...

    @abstractmethod
    def get_services_by_country(self, country: str) -> Dict[str, int]:
        """
        Retorna dict {service_code: quantidade_disponivel} para um país.
        """
        ...

    @abstractmethod
    def get_countries(self) -> Dict[str, str]:
        """
        Retorna dict {country_code: country_name} com todos os países suportados.
        """
        ...

    @abstractmethod
    def get_price(self, service: str, country: str) -> Optional[float]:
        """
        Retorna o preço BASE (custo) em USD para um serviço em um país.
        None se indisponível.
        """
        ...

    def cancel_activation(self, activation_id: str) -> bool:
        """Cancela uma ativação. Método helper."""
        return self.set_status(activation_id, 6)


class ProviderError(Exception):
    """Erro genérico do provider."""
    pass


class InsufficientBalanceError(ProviderError):
    """Saldo insuficiente no provider."""
    pass


class NoNumbersError(ProviderError):
    """Números indisponíveis para o serviço/país."""
    pass