"""
Utils assíncronos — evitam travar o bot com chamadas bloqueantes (rede/DB).
"""
import asyncio


async def run_blocking(fn, *args, **kwargs):
    """
    Roda uma função síncrona (requests/DB) em uma thread separada,
    sem bloquear o loop de eventos do bot.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)
