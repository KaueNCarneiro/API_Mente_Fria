"""Ponto de entrada da Mente Fria API (Fase 1: P1-13, P1-14, P1-15).

Fábrica FastAPI com metadados do contrato, ciclo de vida (``lifespan``), CORS por
ambiente e registro centralizado de routers sob ``/api/v1``.

A Fase 4 acrescentou o registro dos handlers globais de erro (``ApiError``). Os routers
de negócio pertencem à Fase 5: a aplicação ainda sobe sem rotas de negócio.

Execução (a partir da raiz do repositório, com o ambiente virtual ativo)::

    uvicorn --factory src.api.main:create_app
    # ou
    python -m src.api.main
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, configure_logging, get_settings
from .exceptions import registrar_handlers

logger = logging.getLogger(__name__)

# Prefixo contratual de todos os caminhos (OpenAPI: /api/v1/...).
API_V1_PREFIX = "/api/v1"

# Metadados copiados de `info` do Mente Fria API.openapi.json (versão 1.0.0).
API_TITLE = "Mente Fria API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Contrato Design-First da API REST do Mente Fria, sistema de apoio à gestão de "
    "pequenos comércios, com piloto em uma açaiteria. Centraliza cadastro de usuários, "
    "clientes, ingredientes, produtos, composição, estoque e pedidos; oferece alertas, "
    "dashboard e cálculos de recomendação. A recomendação de produção utiliza "
    "Programação Linear Inteira e maximiza o lucro estimado. Este documento especifica "
    "o contrato desejado no padrão /api/v1 e não afirma que todas as rotas já estejam "
    "implementadas."
)
API_CONTACT = {
    "name": "Equipe Mente Fria",
    "url": "https://github.com/KaueNCarneiro/Mente_Fria",
}

# Tags de nível superior do contrato, na ordem original.
OPENAPI_TAGS = [
    {"name": name}
    for name in (
        "Saúde",
        "Autenticação",
        "Usuários",
        "Clientes",
        "Unidades de Medida",
        "Ingredientes",
        "Movimentações de Estoque",
        "Produtos",
        "Pedidos",
        "Alertas",
        "Recomendações",
        "Dashboard",
    )
]


def register_routers(app: FastAPI) -> None:
    """Registro centralizado dos routers sob ``/api/v1``.

    Fase 1: ainda não existem routers. Na Fase 5 (P5-64/P5-65) os módulos de
    ``routers/`` — saude, auth, usuarios, clientes, unidades_medida, ingredientes,
    movimentacoes_estoque, produtos, pedidos, alertas, recomendacoes,
    sugestoes_marketing e dashboard — serão incluídos aqui, em ``api_v1``.
    """
    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    app.include_router(api_v1)


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    """Habilita CORS somente para as origens configuradas (padrão: nenhuma)."""
    if not settings.cors_allowed_origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a aplicação FastAPI.

    ``settings`` pode ser injetado (testes); por padrão usa ``get_settings()``.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Fase 3 (P3-19) inicializará o banco aqui; por ora apenas registra o ciclo.
        logger.info("Mente Fria API iniciando (ambiente=%s)", settings.env.value)
        yield
        logger.info("Mente Fria API encerrada")

    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=API_VERSION,
        contact=API_CONTACT,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    _configure_cors(app, settings)
    # Fase 4 (P4-12): handlers globais do envelope ApiError, antes dos routers.
    registrar_handlers(app)
    register_routers(app)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:create_app", factory=True)
