"""Routers por domínio da Mente Fria API (Fase 5 — P5-64).

Cada módulo cuida apenas da camada HTTP de um domínio: declara caminho, `operationId`,
tag, parâmetros, corpo, status e `responses` **exatamente** como o contrato, resolve a
autorização pela matriz RBAC e delega a regra de negócio ao service correspondente.

``ROUTERS`` é a ordem de registro em ``main.py``, igual à ordem das tags no contrato.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    alertas,
    auth,
    clientes,
    dashboard,
    ingredientes,
    movimentacoes_estoque,
    pedidos,
    produtos,
    recomendacoes,
    saude,
    sugestoes_marketing,
    unidades_medida,
    usuarios,
)

ROUTERS: tuple[APIRouter, ...] = (
    saude.router,
    auth.router,
    usuarios.router,
    clientes.router,
    unidades_medida.router,
    ingredientes.router,
    movimentacoes_estoque.router,
    produtos.router,
    pedidos.router,
    alertas.router,
    recomendacoes.router,
    sugestoes_marketing.router,
    dashboard.router,
)

__all__ = ["ROUTERS"]
