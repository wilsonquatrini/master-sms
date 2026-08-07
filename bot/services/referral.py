"""
Sistema de Referral (Indicação) de 3 níveis.
Nível 1: comissão direta (ex: 10%)
Nível 2: comissão do indicado do indicado (ex: 5%)
Nível 3: comissão do indicado do indicado do indicado (ex: 2%)
"""

import logging
import secrets

from bot.config import Config
from bot.database import db

logger = logging.getLogger(__name__)


class ReferralService:
    """Gerencia o sistema de indicação de 3 níveis."""

    def generate_code(self, user_id: int) -> str:
        """Gera código de referral único."""
        code = secrets.token_hex(4).upper()
        # Garantir unicidade
        while db.get_user_by_referral_code(code):
            code = secrets.token_hex(4).upper()
        return code

    def get_or_create_code(self, user_id: int) -> str:
        """Retorna código existente ou cria um novo."""
        user = db.get_user(user_id)
        if user and user.referral_code:
            return user.referral_code
        code = self.generate_code(user_id)
        # Salvar no user
        from bot.database import User
        from bot.database import db as _db
        with _db.session() as s:
            u = s.query(User).filter_by(telegram_id=user_id).first()
            if u:
                u.referral_code = code
                s.flush()
        return code

    def process_referral(self, new_user_id: int, referral_code: str) -> dict:
        """
        Processa o uso de um código de indicação.
        Estabelece a cadeia de 3 níveis e dá bônus.
        """
        result = {
            'success': False,
            'message': '',
            'bonus_received': 0,
        }

        referrer = db.get_user_by_referral_code(referral_code)
        if not referrer:
            result['message'] = '❌ Código de indicação inválido.'
            return result

        if referrer.telegram_id == new_user_id:
            result['message'] = '❌ Você não pode usar seu próprio código.'
            return result

        # Verificar se já tem indicador
        new_user = db.get_user(new_user_id)
        if new_user and new_user.referred_by:
            result['message'] = '❌ Você já usou um código de indicação.'
            return result

        # Registrar indicação nível 1
        db.set_user_referrer(new_user_id, referrer.telegram_id)
        db.add_referral(referrer.telegram_id, new_user_id, level=1)

        # Bônus de cadastro para o novo usuário
        bonus = Config.REFERRAL_SIGNUP_BONUS
        if bonus > 0:
            db.update_balance(new_user_id, bonus)
            db.add_transaction(
                user_id=new_user_id,
                tx_type='referral_bonus',
                amount=bonus,
                description=f'Bônus de indicação!',
            )
            result['bonus_received'] = bonus

        # Bônus para o indicador (nível 1)
        level1_bonus = Config.REFERRAL_SIGNUP_BONUS * 2
        if level1_bonus > 0:
            db.update_balance(referrer.telegram_id, level1_bonus)
            db.add_transaction(
                user_id=referrer.telegram_id,
                tx_type='referral_bonus',
                amount=level1_bonus,
                description=f'Bônus por indicação de {new_user_id}',
            )

        # Propagar para níveis 2 e 3
        self._propagate_referral(referrer.telegram_id, new_user_id, level1_bonus)

        result['success'] = True
        result['message'] = (
            f'✅ Código válido! Você ganhou R$ {bonus:.2f} de bônus!'
        )
        return result

    def _propagate_referral(self, referrer_id: int, new_user_id: int,
                            base_amount: float):
        """Propaga o referral para níveis 2 e 3."""
        # Encontrar indicador do indicador (nível 2)
        l1_user = db.get_user(referrer_id)
        if l1_user and l1_user.referred_by:
            # Nível 2: o indicador do meu indicador
            l2_id = l1_user.referred_by
            commission = base_amount * (Config.REFERRAL_LEVEL_2 / 100)
            if commission > 0:
                db.update_balance(l2_id, commission)
                db.add_referral(l2_id, new_user_id, level=2)
                db.add_transaction(
                    user_id=l2_id,
                    tx_type='referral_bonus',
                    amount=commission,
                    description=f'Bônus nível 2 (indicação em cadeia)',
                )

            # Nível 3
            l2_user = db.get_user(l2_id)
            if l2_user and l2_user.referred_by:
                l3_id = l2_user.referred_by
                commission3 = base_amount * (Config.REFERRAL_LEVEL_3 / 100)
                if commission3 > 0:
                    db.update_balance(l3_id, commission3)
                    db.add_referral(l3_id, new_user_id, level=3)
                    db.add_transaction(
                        user_id=l3_id,
                        tx_type='referral_bonus',
                        amount=commission3,
                        description=f'Bônus nível 3 (indicação em cadeia)',
                    )

    def add_purchase_commission(self, buyer_id: int, purchase_amount: float):
        """
        Quando um usuário faz uma compra, distribui comissão para
        os indicadores nos 3 níveis.
        """
        buyer = db.get_user(buyer_id)
        if not buyer or not buyer.referred_by:
            return

        # Nível 1: indicador direto
        l1 = db.get_user(buyer.referred_by)
        if l1:
            commission1 = purchase_amount * (Config.REFERRAL_LEVEL_1 / 100)
            if commission1 > 0:
                db.update_balance(l1.telegram_id, commission1)
                db.add_transaction(
                    user_id=l1.telegram_id,
                    tx_type='referral_bonus',
                    amount=commission1,
                    description=f'Comissão de compra (nível 1)',
                )
                db.add_referral(l1.telegram_id, buyer_id, level=1)
                # Somar nos earnings do referral
                with db.session() as s:
                    from bot.database import User
                    u = s.query(User).filter_by(telegram_id=l1.telegram_id).first()
                    if u:
                        u.referral_earnings += commission1

            # Nível 2
            if l1.referred_by:
                l2 = db.get_user(l1.referred_by)
                if l2:
                    commission2 = purchase_amount * (Config.REFERRAL_LEVEL_2 / 100)
                    if commission2 > 0:
                        db.update_balance(l2.telegram_id, commission2)
                        db.add_transaction(
                            user_id=l2.telegram_id,
                            tx_type='referral_bonus',
                            amount=commission2,
                            description=f'Comissão de compra (nível 2)',
                        )
                        db.add_referral(l2.telegram_id, buyer_id, level=2)
                        with db.session() as s:
                            u = s.query(User).filter_by(telegram_id=l2.telegram_id).first()
                            if u:
                                u.referral_earnings += commission2

                    # Nível 3
                    if l2.referred_by:
                        l3 = db.get_user(l2.referred_by)
                        if l3:
                            commission3 = purchase_amount * (Config.REFERRAL_LEVEL_3 / 100)
                            if commission3 > 0:
                                db.update_balance(l3.telegram_id, commission3)
                                db.add_transaction(
                                    user_id=l3.telegram_id,
                                    tx_type='referral_bonus',
                                    amount=commission3,
                                    description=f'Comissão de compra (nível 3)',
                                )
                                db.add_referral(l3.telegram_id, buyer_id, level=3)
                                with db.session() as s:
                                    u = s.query(User).filter_by(telegram_id=l3.telegram_id).first()
                                    if u:
                                        u.referral_earnings += commission3

    def get_stats(self, user_id: int) -> dict:
        """Estatísticas de referral do usuário."""
        counts = db.get_referral_count(user_id)
        user = db.get_user(user_id)
        return {
            'code': user.referral_code if user else '',
            'counts': counts,
            'total_referrals': sum(counts.values()),
            'earnings': user.referral_earnings if user else 0.0,
        }


# Singleton
referral_service = ReferralService()