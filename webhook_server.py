"""
Webhook server — recebe callbacks de pagamento PIX.
Suporta: Mercado Pago, Pluggy.
"""

import json
import logging
import os
import sys

from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.config import Config
from bot.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'master-sms-webhook'})


# =====================================================================
# MERCADO PAGO WEBHOOK
# =====================================================================

@app.route('/mercadopago-webhook', methods=['POST'])
def mercadopago_webhook():
    """
    Recebe notificação do Mercado Pago quando um pagamento é atualizado.
    Documentação: https://www.mercadopago.com.br/developers/pt/docs/ipn
    """
    try:
        data = request.json
        logger.info(f"Mercado Pago webhook: {json.dumps(data, default=str)[:300]}")

        action = data.get('action', '')
        payment_id = None

        # Extrair payment_id do payload
        if 'data' in data and 'id' in data['data']:
            payment_id = str(data['data']['id'])
        elif 'resource' in data:
            # Tentar extrair ID da URL
            resource = data['resource']
            if resource:
                payment_id = resource.split('/')[-1]

        if not payment_id:
            logger.warning("Mercado Pago webhook: sem payment_id")
            return jsonify({'status': 'ignored'}), 200

        # Consultar status do pagamento na API
        from bot.services.pix import pix
        status = pix.check_mercadopago_payment(payment_id)

        if not status:
            logger.warning(f"Mercado Pago: pagamento {payment_id} não encontrado na API")
            return jsonify({'status': 'not_found'}), 200

        payment_status = status.get('status', '').upper()
        logger.info(f"Mercado Pago: pagamento {payment_id} status={payment_status}")

        if payment_status in ('APPROVED', 'CONFIRMED'):
            amount = status.get('amount', 0)
            external_ref = status.get('external_reference', '')

            # Extrair user_id do external_reference (formato: MS{user_id}_timestamp)
            user_id = None
            if external_ref and external_ref.startswith('MS'):
                try:
                    user_id = int(external_ref.split('_')[0][2:])
                except (ValueError, IndexError):
                    pass

            if not user_id:
                logger.error(f"Mercado Pago: não foi possível extrair user_id de {external_ref}")
                return jsonify({'status': 'error', 'message': 'user_id not found'}), 200

            # Creditar saldo
            db.update_balance(user_id, amount)
            db.add_transaction(
                user_id=user_id,
                tx_type='deposit',
                amount=amount,
                description=f'Depósito PIX confirmado (Mercado Pago)',
                status='completed',
                reference_id=str(payment_id),
            )

            logger.info(f"✅ Mercado Pago: saldo creditado user={user_id}, amount={amount}")
            return jsonify({'status': 'success'}), 200

        return jsonify({'status': 'pending', 'payment_status': payment_status}), 200

    except Exception as e:
        logger.error(f"Erro Mercado Pago webhook: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


# =====================================================================
# PLUGGY WEBHOOK (fallback)
# =====================================================================

@app.route('/pix-webhook/<int:user_id>', methods=['POST'])
def pluggy_webhook(user_id):
    """Recebe webhook do Pluggy quando um pagamento é confirmado."""
    try:
        data = request.json
        logger.info(f"Pluggy webhook: user={user_id}, data={json.dumps(data)[:200]}")

        status = data.get('status', '').upper()
        amount = float(data.get('amount', 0))
        payment_id = data.get('id', data.get('paymentId', ''))

        if status in ('COMPLETED', 'PAID', 'APPROVED'):
            db.update_balance(user_id, amount)
            db.add_transaction(
                user_id=user_id,
                tx_type='deposit',
                amount=amount,
                description='Depósito PIX confirmado (Pluggy)',
                status='completed',
                reference_id=str(payment_id),
            )
            logger.info(f"✅ Pluggy: saldo creditado user={user_id}, amount={amount}")
            return jsonify({'status': 'success'}), 200

        return jsonify({'status': 'pending'}), 200

    except Exception as e:
        logger.error(f"Pluggy webhook error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/pix-webhook', methods=['POST'])
def pix_webhook_generic():
    """Webhook genérico sem user_id na URL (alguns provedores não suportam)."""
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    Config.validate()
    db.init_db()
    port = int(os.getenv('WEBHOOK_PORT', '5000'))
    logger.info(f"🌐 Webhook Master SMS iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)