# 🤖 Master SMS — Bot de Números Virtuais (SMS-Activate Reseller)

Bot Telegram profissional para revenda de números virtuais (SMS de verificação)
usando a API do **SMS-Activate** como fornecedor.

Feito para competir com bots como o Notz SMS: **referral 3 níveis, PIX, 
markup dinâmico, cupons, fidelidade, admin completo**.

## 🚀 Stack

- Python 3.11 + python-telegram-bot 20.x (async)
- PostgreSQL (persistência) + SQLAlchemy
- PIX via Pluggy.ai (webhook automático)
- API SMS-Activate (fornecedor)
- Docker + Coolify (deploy)

## 📦 Estrutura

```
master-sms/
├── bot/
│   ├── main.py           # Entry point
│   ├── config.py         # Configuração centralizada (env)
│   ├── database.py       # Modelos + operações de banco
│   ├── keyboards.py      # Teclados inline
│   ├── handlers/         # Handlers do Telegram
│   │   ├── start.py      # /start, boas-vindas
│   │   ├── balance.py    # /saldo, histórico
│   │   ├── deposit.py    # /depositar (PIX)
│   │   ├── purchase.py   # /comprar (fluxo SMS)
│   │   ├── referral.py   # /indicar (referral 3 níveis)
│   │   ├── admin.py      # /admin (gerenciar preços, users)
│   │   └── coupons.py    # /cupom
│   └── services/
│       ├── sms_activate.py  # Cliente API SMS-Activate
│       ├── pix.py           # Pagamento PIX (Pluggy)
│       ├── pricing.py       # Motor de markup/preços
│       └── referral.py      # Sistema referral 3 níveis
├── worker.py            # Worker assíncrono (verifica pagamentos)
├── webhook_server.py    # Webhook PIX (Flask)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 🧰 Funcionalidades

### Para o usuário
- ✅ Depósito via PIX (código copia-e-cola + QR Code)
- ✅ Compra de número virtual por serviço (WhatsApp, Telegram, Instagram, etc.)
- ✅ Recebimento do código SMS automaticamente
- ✅ Saldo interno, histórico de transações
- ✅ Sistema de referral 3 níveis (comissão em cascata)
- ✅ Cupons de desconto
- ✅ Níveis de fidelidade (Bronze → Silver → Gold → Platinum) com cashback

### Para o admin
- ✅ Definir markup % global ou por serviço/país
- ✅ Gerenciar usuários (saldo, ban, permissões)
- ✅ Ver estatísticas de vendas/lucro
- ✅ Broadcast de mensagens
- ✅ Criar cupons
- ✅ Visualizar pedidos ativos

## 🛠️ Configuração

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token do @BotFather |
| `ADMIN_IDS` | ✅ | IDs dos admins (separados por vírgula) |
| `SMS_ACTIVATE_API_KEY` | ✅ | Chave da API do SMS-Activate |
| `DATABASE_URL` | ✅ | URL do PostgreSQL |
| `PLUGGY_CLIENT_ID` | ❌ | Para PIX automático via Pluggy |
| `PLUGGY_CLIENT_SECRET` | ❌ | Secret do Pluggy |
| `PIX_KEY` | ❌ | Chave PIX manual (fallback) |
| `REFERRAL_LEVEL_1` | ❌ | % comissão nível 1 (padrão: 10) |
| `REFERRAL_LEVEL_2` | ❌ | % comissão nível 2 (padrão: 5) |
| `REFERRAL_LEVEL_3` | ❌ | % comissão nível 3 (padrão: 2) |

## 🚢 Deploy (Coolify / Docker)

```bash
docker compose up -d --build
```

### No Coolify
1. Crie um novo recurso → Docker Compose
2. Cole o conteúdo do `docker-compose.yml`
3. Configure as variáveis de ambiente na UI
4. Deploy!

## 📄 Licença

Projeto baseado em [bot-sms-telegram](https://github.com/popovidismarcoantonionista-lang/bot-sms-telegram)
— MIT. Modificado e expandido para uso comercial.
