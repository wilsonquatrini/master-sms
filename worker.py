"""
Worker assíncrono — verifica pagamentos PIX e atualiza saldos.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.config import Config
from bot.database import db
from bot.services.pix import pix

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def check_pending_deposits():
    """
    Verifica pagamentos PIX pendentes.
    Suporta Mercado Pago e Pluggy.
    """
    from bot.database import Transaction

    # Buscar transações pending (depósitos não confirmados)
    with db.session() as s:
        pending = (s.query(Transaction)
                   .filter_by(type='deposit', status='pending')
                   .order_by(Transaction.created_at.desc())
                   .limit(50)
                   .all())

    if not pending:
        return

    for tx in pending:
        if not tx.reference_id:
            continue

        # Determinar provedor pelo ID
        provider = 'mercadopago'
        if tx.reference_id.startswith('pluggy_'):
            provider = 'pluggy'

        result = pix.check_payment(tx.reference_id, provider)
        if not result:
            continue

        status = result.get('status', '').upper()

        if status in ('APPROVED', 'COMPLETED', 'PAID', 'CONFIRMED'):
            # Creditar saldo
            amount = result.get('amount', tx.amount)
            db.update_balance(tx.user_id, amount)

            # Criar transação de confirmação
            db.add_transaction(
                user_id=tx.user_id,
                tx_type='deposit',
                amount=amount,
                description=f'Depósito PIX confirmado ({provider})',
                status='completed',
            )

            # Marcar a antiga como completed
            with db.session() as s2:
                t = s2.query(Transaction).filter_by(id=tx.id).first()
                if t:
                    t.status = 'completed'

            logger.info(f"✅ Depósito confirmado: user={tx.user_id}, amount={amount}, provider={provider}")


async def check_expired_activations():
    """
    Cancela ativações SMS que expiraram (sem SMS em 10 min).
    """
    from bot.database import SMSPurchase
    from bot.services.providers import provider_manager

    cutoff = datetime.utcnow() - timedelta(minutes=10)

    with db.session() as s:
        old_pending = (s.query(SMSPurchase)
                       .filter(SMSPurchase.status.in_(['pending', 'waiting_sms']))
                       .filter(SMSPurchase.created_at < cutoff)
                       .all())

    for p in old_pending:
        if p.activation_id:
            provider_manager.set_status(p.activation_id, 6, p.provider)

        db.update_sms_purchase(p.id, status='cancelled')

        # Reembolsar (50% do valor)
        refund = p.price * 0.5
        db.update_balance(p.user_id, refund)
        db.add_transaction(
            user_id=p.user_id,
            tx_type='refund',
            amount=refund,
            description=f'Reembolso parcial 50% — SMS não recebido ({p.service_name})',
        )

        logger.info(f"Ativação expirada cancelada: {p.id}, reembolso R$ {refund:.2f}")


async def main_loop():
    logger.info("🔄 Worker Master SMS iniciado")
    loop_count = 0

    while True:
        try:
            await check_pending_deposits()
            await check_expired_activations()
            loop_count += 1
            if loop_count % 10 == 0:
                logger.info(f"Worker ativo — {loop_count} ciclos")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)

        await asyncio.sleep(Config.CHECK_PAYMENT_INTERVAL)


if __name__ == '__main__':
    Config.validate()
    db.init_db()
    asyncio.run(main_loop())