"""
Master SMS Bot — Entry point principal.
"""

import logging
import sys

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.config import Config
from bot.database import db
from bot.handlers import start, balance, deposit, purchase, referral, admin, coupons, countries

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    # Validar configuração
    Config.validate()

    # Inicializar banco de dados
    db.init_db()
    logger.info("Database initialized")

    # Criar aplicação
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Registrar handlers
    handlers = []
    for module in [start, balance, deposit, purchase, referral, admin, coupons, countries]:
        try:
            handlers += module.get_handlers()
        except Exception as e:
            logger.warning(f"Failed to load handlers from {module.__name__}: {e}")

    for handler in handlers:
        app.add_handler(handler)

    logger.info(f"Registered {len(handlers)} handlers")

    # Iniciar
    logger.info("Master SMS Bot iniciado!")

    if Config.WEBHOOK_URL:
        # Modo webhook
        app.run_webhook(
            listen='0.0.0.0',
            port=8080,
            url_path=Config.TELEGRAM_BOT_TOKEN,
            webhook_url=f"{Config.WEBHOOK_URL}/{Config.TELEGRAM_BOT_TOKEN}",
        )
    else:
        # Modo polling
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)