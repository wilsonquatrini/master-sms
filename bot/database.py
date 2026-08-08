"""
Modelos de banco de dados + operações CRUD.
SQLAlchemy + suporte a PostgreSQL e SQLite.
"""

import logging
from datetime import datetime, timedelta
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, BigInteger, event
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

from bot.config import Config

logger = logging.getLogger(__name__)
Base = declarative_base()


# =====================================================================
# MODELOS
# =====================================================================

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)

    # Financeiro
    balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)

    # Referral
    referral_code = Column(String(20), unique=True, index=True, nullable=True)
    referred_by = Column(BigInteger, nullable=True, index=True)  # telegram_id de quem indicou
    referral_earnings = Column(Float, default=0.0)

    # Status
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User(tg={self.telegram_id}, bal={self.balance:.2f})>"


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    type = Column(String(50), nullable=False)  # deposit, purchase, refund, referral_bonus, cashback
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default='completed')  # pending, completed, failed, refunded
    reference_id = Column(String(255), nullable=True, index=True)  # ID externo (ex: pagamento, ativação)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Transaction({self.type}, {self.amount})>"


class SMSPurchase(Base):
    __tablename__ = 'sms_purchases'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)

    # Provider
    provider = Column(String(50), nullable=True, default=None)  # hero_sms, five_sim, etc.

    # Serviço
    service = Column(String(50), nullable=False)  # wa, tg, ig, etc.
    service_name = Column(String(100), nullable=True)  # WhatsApp, Telegram, etc.
    country = Column(String(10), default='24')  # BR = 24

    # Número
    phone_number = Column(String(50), nullable=True)
    activation_id = Column(String(255), index=True, nullable=True)

    # Financeiro
    price = Column(Float, nullable=False)
    cost = Column(Float, nullable=True)  # custo real (o que pagamos ao SMS-Activate)

    # Status
    status = Column(String(30), default='pending')  # pending, received, cancelled, expired
    sms_code = Column(String(100), nullable=True)
    sms_text = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<SMSPurchase({self.service}, {self.phone_number}, {self.status})>"


class Coupon(Base):
    __tablename__ = 'coupons'

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    discount_percent = Column(Float, nullable=False)
    max_uses = Column(Integer, nullable=True)
    current_uses = Column(Integer, default=0)
    min_purchase = Column(Float, default=0.0)
    active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Coupon({self.code}, {self.discount_percent}%)>"


class CouponUsage(Base):
    __tablename__ = 'coupon_usages'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    coupon_code = Column(String(50), nullable=False, index=True)
    used_at = Column(DateTime, default=datetime.utcnow)


class Referral(Base):
    """Registro de indicação (3 níveis)."""
    __tablename__ = 'referrals'

    id = Column(Integer, primary_key=True)
    referrer_id = Column(BigInteger, nullable=False, index=True)  # quem indicou
    referred_id = Column(BigInteger, nullable=False, index=True)  # quem foi indicado
    level = Column(Integer, default=1)  # 1, 2, ou 3
    commission = Column(Float, default=0.0)  # comissão gerada
    created_at = Column(DateTime, default=datetime.utcnow)


class PriceRule(Base):
    """Regra de markup por serviço (sobrescreve o global)."""
    __tablename__ = 'price_rules'

    id = Column(Integer, primary_key=True)
    service = Column(String(50), nullable=False, index=True)  # wa, tg, ig, etc.
    country = Column(String(10), default='24')
    markup_percent = Column(Float, nullable=False)  # ex: 150 = 150% markup
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =====================================================================
# DATABASE WRAPPER
# =====================================================================

class Database:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or Config.DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=Config.DEBUG,
        )
        self.SessionLocal = scoped_session(sessionmaker(bind=self.engine, expire_on_commit=False))

        # Enable WAL mode for SQLite (better concurrency)
        if 'sqlite' in self.database_url:
            @event.listens_for(self.engine, 'connect')
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.close()

    def init_db(self):
        """Cria todas as tabelas."""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized")

    @contextmanager
    def session(self):
        """Context manager para sessão de banco."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- USERS ----------

    def get_or_create_user(self, telegram_id: int, username: str = None,
                           first_name: str = None) -> User:
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                import secrets
                code = secrets.token_hex(4).upper()
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    referral_code=code,
                    referral_earnings=0.0,
                )
                # Verificar se é admin
                if telegram_id in Config.ADMIN_IDS:
                    user.is_admin = True
                s.add(user)
                s.flush()
                logger.info(f"New user created: {telegram_id}")
            else:
                # Atualizar dados se mudou
                if username and user.username != username:
                    user.username = username
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
            return user

    def get_user(self, telegram_id: int) -> User:
        with self.session() as s:
            return s.query(User).filter_by(telegram_id=telegram_id).first()

    def get_user_by_referral_code(self, code: str) -> User:
        with self.session() as s:
            return s.query(User).filter_by(referral_code=code.upper()).first()

    def update_balance(self, telegram_id: int, amount: float) -> float:
        """Adiciona (ou subtrai) valor ao saldo. Retorna novo saldo."""
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).with_for_update().first()
            if not user:
                raise ValueError(f"User {telegram_id} not found")
            user.balance += amount
            user.updated_at = datetime.utcnow()
            s.flush()
            return user.balance

    def get_balance(self, telegram_id: int) -> float:
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).first()
            return user.balance if user else 0.0

    def set_user_referrer(self, telegram_id: int, referrer_id: int):
        """Define quem indicou o usuário."""
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).first()
            if user and not user.referred_by:
                user.referred_by = referrer_id
                s.flush()

    def get_all_users(self) -> list:
        with self.session() as s:
            return s.query(User).order_by(User.created_at.desc()).all()

    def get_user_count(self) -> int:
        with self.session() as s:
            return s.query(User).count()

    def ban_user(self, telegram_id: int, ban: bool = True):
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                user.is_banned = ban
                s.flush()

    def set_admin(self, telegram_id: int, admin: bool = True):
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                user.is_admin = admin
                s.flush()

    # ---------- TRANSACTIONS ----------

    def add_transaction(self, user_id: int, tx_type: str, amount: float,
                        description: str = None, status: str = 'completed',
                        reference_id: str = None):
        with self.session() as s:
            tx = Transaction(
                user_id=user_id,
                type=tx_type,
                amount=amount,
                description=description,
                status=status,
                reference_id=reference_id,
            )
            s.add(tx)
            s.flush()
            return tx

    def get_user_transactions(self, user_id: int, limit: int = 20,
                              offset: int = 0) -> list:
        with self.session() as s:
            return (s.query(Transaction)
                    .filter_by(user_id=user_id)
                    .order_by(Transaction.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all())

    def get_all_transactions(self, limit: int = 50, offset: int = 0) -> list:
        with self.session() as s:
            return (s.query(Transaction)
                    .order_by(Transaction.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all())

    # ---------- SMS PURCHASES ----------

    def create_sms_purchase(self, user_id: int, service: str, service_name: str,
                            country: str, price: float, cost: float = None,
                            provider: str = None) -> SMSPurchase:
        with self.session() as s:
            purchase = SMSPurchase(
                user_id=user_id,
                service=service,
                service_name=service_name,
                country=country,
                price=price,
                cost=cost,
                provider=provider,
                status='pending',
            )
            s.add(purchase)
            s.flush()
            return purchase

    def update_sms_purchase(self, purchase_id: int, **kwargs) -> SMSPurchase:
        with self.session() as s:
            purchase = s.query(SMSPurchase).filter_by(id=purchase_id).first()
            if purchase:
                for k, v in kwargs.items():
                    setattr(purchase, k, v)
                if kwargs.get('status') == 'received':
                    purchase.completed_at = datetime.utcnow()
                purchase.updated_at = datetime.utcnow()
                s.flush()
            return purchase

    def get_user_purchases(self, user_id: int, limit: int = 20) -> list:
        with self.session() as s:
            return (s.query(SMSPurchase)
                    .filter_by(user_id=user_id)
                    .order_by(SMSPurchase.created_at.desc())
                    .limit(limit)
                    .all())

    def get_active_purchases(self, user_id: int = None) -> list:
        """Compras em andamento (pending, aguardando SMS)."""
        with self.session() as s:
            q = s.query(SMSPurchase).filter(
                SMSPurchase.status.in_(['pending', 'waiting_sms'])
            )
            if user_id:
                q = q.filter_by(user_id=user_id)
            return q.order_by(SMSPurchase.created_at.desc()).all()

    def get_purchase_by_activation(self, activation_id: str) -> SMSPurchase:
        with self.session() as s:
            return s.query(SMSPurchase).filter_by(activation_id=activation_id).first()

    # ---------- COUPONS ----------

    def create_coupon(self, code: str, discount_percent: float,
                      max_uses: int = None, min_purchase: float = 0.0,
                      expires_at: datetime = None, created_by: int = None) -> Coupon:
        with self.session() as s:
            coupon = Coupon(
                code=code.upper(),
                discount_percent=discount_percent,
                max_uses=max_uses,
                min_purchase=min_purchase,
                expires_at=expires_at,
                created_by=created_by,
            )
            s.add(coupon)
            s.flush()
            return coupon

    def get_coupon(self, code: str) -> Coupon:
        with self.session() as s:
            return s.query(Coupon).filter_by(code=code.upper()).first()

    def use_coupon(self, code: str, user_id: int) -> bool:
        """Registra uso de um cupom. Retorna True se ok."""
        with self.session() as s:
            coupon = s.query(Coupon).filter_by(code=code.upper()).with_for_update().first()
            if not coupon or not coupon.active:
                return False
            if coupon.max_uses and coupon.current_uses >= coupon.max_uses:
                return False
            if coupon.expires_at and datetime.utcnow() > coupon.expires_at:
                return False
            # Verificar se usuário já usou
            already = s.query(CouponUsage).filter_by(
                user_id=user_id, coupon_code=code.upper()
            ).first()
            if already:
                return False
            coupon.current_uses += 1
            usage = CouponUsage(user_id=user_id, coupon_code=code.upper())
            s.add(usage)
            s.flush()
            return True

    def get_active_coupons(self) -> list:
        with self.session() as s:
            now = datetime.utcnow()
            return (s.query(Coupon)
                    .filter(Coupon.active == True)
                    .filter((Coupon.expires_at == None) | (Coupon.expires_at > now))
                    .filter((Coupon.max_uses == None) | (Coupon.current_uses < Coupon.max_uses))
                    .all())

    # ---------- REFERRALS ----------

    def add_referral(self, referrer_id: int, referred_id: int, level: int = 1):
        with self.session() as s:
            ref = Referral(
                referrer_id=referrer_id,
                referred_id=referred_id,
                level=level,
            )
            s.add(ref)
            s.flush()

    def get_referrals(self, user_id: int, level: int = 1) -> list:
        """Retorna lista de indicados de um usuário em determinado nível."""
        with self.session() as s:
            return (s.query(Referral)
                    .filter_by(referrer_id=user_id, level=level)
                    .all())

    def get_referral_count(self, user_id: int) -> dict:
        """Contagem de indicados por nível."""
        with self.session() as s:
            counts = {1: 0, 2: 0, 3: 0}
            for level in [1, 2, 3]:
                counts[level] = (s.query(Referral)
                                 .filter_by(referrer_id=user_id, level=level)
                                 .count())
            return counts

    def get_referral_chain(self, user_id: int) -> list:
        """Retorna a cadeia de referral acima do usuário (até 3 níveis)."""
        chain = []
        with self.session() as s:
            user = s.query(User).filter_by(telegram_id=user_id).first()
            if not user or not user.referred_by:
                return chain

            # Nível 1
            l1 = s.query(User).filter_by(telegram_id=user.referred_by).first()
            if l1:
                chain.append((l1, 1))
                # Nível 2
                if l1.referred_by:
                    l2 = s.query(User).filter_by(telegram_id=l1.referred_by).first()
                    if l2:
                        chain.append((l2, 2))
                        # Nível 3
                        if l2.referred_by:
                            l3 = s.query(User).filter_by(telegram_id=l2.referred_by).first()
                            if l3:
                                chain.append((l3, 3))
        return chain

    # ---------- PRICE RULES ----------

    def get_price_rule(self, service: str, country: str = '24') -> PriceRule:
        with self.session() as s:
            return (s.query(PriceRule)
                    .filter_by(service=service, country=country, is_active=True)
                    .first())

    def set_price_rule(self, service: str, markup_percent: float,
                       country: str = '24') -> PriceRule:
        with self.session() as s:
            rule = (s.query(PriceRule)
                    .filter_by(service=service, country=country)
                    .first())
            if rule:
                rule.markup_percent = markup_percent
            else:
                rule = PriceRule(
                    service=service, country=country,
                    markup_percent=markup_percent,
                )
                s.add(rule)
            s.flush()
            return rule

    def get_all_price_rules(self) -> list:
        with self.session() as s:
            return s.query(PriceRule).filter_by(is_active=True).all()

    # ---------- STATS ----------

    def get_total_client_balance(self) -> float:
        """Soma os saldos positivos dos clientes (custódia que devemos entregar)."""
        try:
            with self.session() as s:
                rows = s.query(User.balance).filter(User.balance > 0).all()
                return round(sum((r[0] or 0) for r in rows), 2)
        except Exception:
            return 0.0

    def get_stats(self) -> dict:
        """Estatísticas gerais para admin."""
        with self.session() as s:
            total_users = s.query(User).count()
            total_balance = s.query(User).with_entities(User.balance).all()
            total_balance = sum(b[0] for b in total_balance if b[0] > 0)

            # Vendas do dia
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_sales = (s.query(SMSPurchase)
                           .filter(SMSPurchase.created_at >= today)
                           .count())
            today_revenue = (s.query(SMSPurchase)
                             .filter(SMSPurchase.created_at >= today)
                             .with_entities(SMSPurchase.price)
                             .all())
            today_revenue = sum(r[0] for r in today_revenue)

            # Total vendido
            total_sales = s.query(SMSPurchase).count()
            total_revenue = (s.query(SMSPurchase)
                             .with_entities(SMSPurchase.price)
                             .all())
            total_revenue = sum(r[0] for r in total_revenue)

            return {
                'total_users': total_users,
                'total_balance': total_balance,
                'today_sales': today_sales,
                'today_revenue': today_revenue,
                'total_sales': total_sales,
                'total_revenue': total_revenue,
            }


# Singleton global
db = Database()