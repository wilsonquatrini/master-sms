"""
Sistema de pagamento PIX.
Suporta Mercado Pago (principal) e fallback manual (chave PIX estática).
"""

import json
import logging
import base64
from typing import Optional, Dict
from datetime import datetime

import requests

from bot.config import Config

logger = logging.getLogger(__name__)


class PixPayment:
    """Gerencia pagamentos via PIX."""

    def __init__(self):
        self.use_mercadopago = bool(Config.MERCADO_PAGO_ACCESS_TOKEN)
        self.use_pluggy = bool(
            Config.PLUGGY_CLIENT_ID and Config.PLUGGY_CLIENT_SECRET
        )
        self.pluggy_token = None
        self.pluggy_token_expires = None

    # =================================================================
    # MERCADO PAGO (recomendado)
    # =================================================================

    def create_mercadopago_pix(self, amount: float, user_id: int,
                               description: str = None) -> Optional[Dict]:
        """
        Cria cobrança PIX via Mercado Pago.
        Retorna QR Code (base64) e código copia-e-cola.
        Documentação: https://www.mercadopago.com.br/developers/pt/reference/payments/_payments/post
        """
        if not self.use_mercadopago:
            return None

        desc = description or f'Master SMS - Recarga #{user_id}'
        payment_id = f'MS{user_id}_{int(datetime.utcnow().timestamp())}'

        try:
            headers = {
                'Authorization': f'Bearer {Config.MERCADO_PAGO_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
                'X-Idempotency-Key': payment_id,
            }

            # Payload para pagamento PIX
            payload = {
                'transaction_amount': amount,
                'description': desc,
                'payment_method_id': 'pix',
                'payer': {
                    'email': f'user_{user_id}@mastersms.com.br',
                },
                'notification_url': f'{Config.WEBHOOK_URL}/mercadopago-webhook' if Config.WEBHOOK_URL else None,
                'external_reference': str(payment_id),
            }

            # Remover notification_url se não configurado
            if not payload['notification_url']:
                del payload['notification_url']

            resp = requests.post(
                'https://api.mercadopago.com/v1/payments',
                json=payload,
                headers=headers,
                timeout=15,
            )

            # Se der 401, token inválido
            if resp.status_code == 401:
                logger.error("Mercado Pago: token inválido ou expirado")
                return None

            resp.raise_for_status()
            data = resp.json()

            # Extrair QR Code do ponto de interação
            qr_code = None
            copy_paste = None

            if 'point_of_interaction' in data:
                poi = data['point_of_interaction']
                if 'transaction_data' in poi:
                    td = poi['transaction_data']
                    qr_code = td.get('qr_code_base64')  # Base64 da imagem
                    copy_paste = td.get('qr_code')       # Código copia-e-cola

            logger.info(f"Mercado Pago PIX criado: ID={data.get('id')}, valor={amount}")

            return {
                'payment_id': str(data.get('id')),
                'client_payment_id': payment_id,
                'qr_code_base64': qr_code,
                'copy_paste': copy_paste,
                'amount': amount,
                'status': data.get('status', 'pending'),
                'status_detail': data.get('status_detail', ''),
                'provider': 'mercadopago',
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Mercado Pago error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text[:500]}")
            return None

    def check_mercadopago_payment(self, payment_id: str) -> Optional[Dict]:
        """
        Verifica status de um pagamento PIX no Mercado Pago.
        """
        try:
            headers = {
                'Authorization': f'Bearer {Config.MERCADO_PAGO_ACCESS_TOKEN}',
            }

            resp = requests.get(
                f'https://api.mercadopago.com/v1/payments/{payment_id}',
                headers=headers,
                timeout=10,
            )

            if resp.status_code == 404:
                return None

            resp.raise_for_status()
            data = resp.json()

            return {
                'status': data.get('status'),
                'status_detail': data.get('status_detail'),
                'amount': data.get('transaction_amount'),
                'paid_at': data.get('date_approved'),
                'external_reference': data.get('external_reference'),
            }

        except Exception as e:
            logger.error(f"Mercado Pago check error: {e}")
            return None

    # =================================================================
    # PLUGGY (fallback)
    # =================================================================

    def _pluggy_auth(self) -> Optional[str]:
        """Autentica na API do Pluggy e retorna token."""
        if not self.use_pluggy:
            return None

        if (self.pluggy_token and self.pluggy_token_expires
                and datetime.utcnow() < self.pluggy_token_expires):
            return self.pluggy_token

        try:
            resp = requests.post(
                'https://api.pluggy.ai/auth',
                json={
                    'clientId': Config.PLUGGY_CLIENT_ID,
                    'clientSecret': Config.PLUGGY_CLIENT_SECRET,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self.pluggy_token = data['access_token']
            self.pluggy_token_expires = datetime.utcnow().replace(
                second=0, microsecond=0
            )
            return self.pluggy_token
        except Exception as e:
            logger.error(f"Pluggy auth error: {e}")
            return None

    def create_pluggy_pix(self, amount: float, user_id: int,
                          description: str = None) -> Optional[Dict]:
        """Cria cobrança PIX via Pluggy (fallback)."""
        token = self._pluggy_auth()
        if not token:
            return None

        desc = description or f'Recarga - Usuário {user_id}'
        payment_id = f'sms_{user_id}_{int(datetime.utcnow().timestamp())}'

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            }
            payload = {
                'amount': amount,
                'description': desc,
                'clientPaymentId': payment_id,
                'recipientId': Config.PLUGGY_RECIPIENT_ID,
                'isSandbox': Config.PLUGGY_ENVIRONMENT == 'sandbox',
            }

            if Config.WEBHOOK_URL:
                payload['callbackUrls'] = {
                    'webhook': f'{Config.WEBHOOK_URL}/pix-webhook/{user_id}',
                }

            resp = requests.post(
                f'{Config.PLUGGY_BASE_URL}/payments/requests',
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            return {
                'payment_id': data.get('id'),
                'client_payment_id': payment_id,
                'qr_code_base64': data.get('pixQrCode'),
                'copy_paste': data.get('pixCopiaECola'),
                'amount': amount,
                'status': data.get('status', 'pending'),
                'provider': 'pluggy',
            }
        except Exception as e:
            logger.error(f"Pluggy create PIX error: {e}")
            return None

    def check_pluggy_payment(self, payment_id: str) -> Optional[Dict]:
        """Verifica status de pagamento no Pluggy."""
        token = self._pluggy_auth()
        if not token:
            return None

        try:
            headers = {'Authorization': f'Bearer {token}'}
            resp = requests.get(
                f'{Config.PLUGGY_BASE_URL}/payments/requests/{payment_id}',
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                'status': data.get('status'),
                'amount': data.get('amount'),
                'paid_at': data.get('paidAt'),
                'provider': 'pluggy',
            }
        except Exception as e:
            logger.error(f"Pluggy check error: {e}")
            return None

    # =================================================================
    # MÉTODO PRINCIPAL (Tenta Mercado Pago, depois Pluggy, depois Manual)
    # =================================================================

    def create_pix(self, amount: float, user_id: int,
                   unique_id: str = None) -> Optional[Dict]:
        """
        Cria PIX tentando provedores em ordem:
        1. Mercado Pago (se configurado)
        2. Pluggy (se configurado)
        3. Manual (fallback)
        """
        # 1. Mercado Pago
        if self.use_mercadopago:
            result = self.create_mercadopago_pix(amount, user_id)
            if result:
                return result

        # 2. Pluggy
        if self.use_pluggy:
            result = self.create_pluggy_pix(amount, user_id)
            if result:
                return result

        # 3. Manual
        return self.generate_manual_pix(amount, user_id, unique_id or str(user_id))

    def check_payment(self, payment_id: str, provider: str = None) -> Optional[Dict]:
        """Verifica status do pagamento no provedor correto."""
        if provider == 'mercadopago':
            return self.check_mercadopago_payment(payment_id)
        elif provider == 'pluggy':
            return self.check_pluggy_payment(payment_id)
        return None

    # =================================================================
    # MANUAL (fallback — chave PIX estática)
    # =================================================================

    def generate_manual_pix(self, amount: float, user_id: int,
                            unique_id: str) -> Dict:
        """Gera instruções PIX manuais (chave estática)."""
        return {
            'method': 'manual',
            'pix_key': Config.PIX_KEY,
            'pix_name': Config.PIX_NAME,
            'pix_city': Config.PIX_CITY,
            'amount': amount,
            'unique_id': unique_id,
            'description': f'MASTER{unique_id}',
            'provider': 'manual',
            'instructions': (
                f'1️⃣ Faça um PIX no valor de *{Config.CURRENCY} {amount:.2f}*\n'
                f'2️⃣ Chave PIX: `{Config.PIX_KEY}`\n'
                f'3️⃣ *IMPORTANTE:* Coloque o ID na descrição:\n'
                f'   `MASTER{unique_id}`\n'
                f'4️⃣ O saldo é creditado automaticamente em até 2 minutos'
            ),
        }


# Singleton
pix = PixPayment()