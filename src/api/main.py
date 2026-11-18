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
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from .config import Environment, Settings, configure_logging, get_settings
from .database import init_db
from .exceptions import registrar_handlers
from .routers import ROUTERS

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


def rotas_da_api(app: FastAPI) -> list[APIRoute]:
    """Todas as ``APIRoute`` da aplicação, inclusive as de routers aninhados.

    A partir do FastAPI 0.163, ``include_router`` não achata mais as rotas em
    ``app.routes``: elas ficam sob um router incluído, então a varredura é recursiva.
    """
    encontradas: list[APIRoute] = []

    vistos: set[int] = set()

    def percorrer(rotas: object) -> None:
        for rota in rotas or ():  # type: ignore[union-attr]
            if id(rota) in vistos:
                continue
            vistos.add(id(rota))
            if isinstance(rota, APIRoute):
                encontradas.append(rota)
                continue
            # Router incluído (FastAPI >= 0.163) ou aplicação montada: desce um nível.
            for atributo in ("routes", "original_router", "router", "app"):
                filho = getattr(rota, atributo, None)
                if filho is None:
                    continue
                percorrer(filho if isinstance(filho, list) else getattr(filho, "routes", None))

    percorrer(app.routes)
    return encontradas


def _alinhar_openapi_ao_contrato(app: FastAPI) -> None:
    """Remove do documento gerado o `422` que o FastAPI acrescenta por conta própria.

    O FastAPI adiciona automaticamente `422 Validation Error` a toda operação que tenha
    parâmetros ou corpo. Em 25 das 44 operações o contrato **não** declara esse status, e
    o `Mente Fria API.openapi.json` é a fonte normativa (AGENTS.md §2): quem se ajusta é o
    documento gerado, não o contrato.

    Só é removido onde a própria rota não declarou `422` — ou seja, onde o contrato não o
    tem. Isso **não** altera o comportamento em execução: o handler de erro da Fase 4 lê
    `route.responses`, que continua exatamente como declarado em cada router.
    """
    gerar = app.openapi

    def openapi_do_contrato() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        esquema = gerar()
        # Casamento por `operationId`: a partir do FastAPI 0.163 o `path_format` da rota
        # não inclui o prefixo do router que a contém, então o caminho não serve de chave.
        declara_422 = {
            rota.operation_id: any(str(codigo) == "422" for codigo in (rota.responses or {}))
            for rota in rotas_da_api(app)
            if rota.operation_id
        }
        for operacoes in esquema.get("paths", {}).values():
            for operacao in operacoes.values():
                if not isinstance(operacao, dict):
                    continue
                operation_id = operacao.get("operationId")
                if operation_id in declara_422 and not declara_422[operation_id]:
                    operacao.get("responses", {}).pop("422", None)
        app.openapi_schema = esquema
        return esquema

    app.openapi = openapi_do_contrato  # type: ignore[method-assign]


def register_routers(app: FastAPI) -> None:
    """Registro centralizado dos 13 routers sob ``/api/v1`` (P5-65).

    A ordem vem de ``routers.ROUTERS`` e acompanha as tags do contrato. As rotas públicas
    (``GET /saude``, ``POST /auth/administrador`` e ``POST /auth/login``) não recebem
    dependência de autenticação; as demais trazem a autorização declarada em cada router.
    """
    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    for router in ROUTERS:
        api_v1.include_router(router)
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
        """Ciclo de vida conforme a estratégia de banco aprovada (P5-66 / decisão 4).

        Nenhuma ferramenta de migração foi adotada: em ``local`` e ``test`` as tabelas
        são criadas por ``init_db()`` (``metadata.create_all``), que **não** altera
        tabelas existentes. Em ``production`` nada é criado automaticamente — a própria
        ``init_db`` recusa esse ambiente —, e o schema é responsabilidade do processo de
        implantação. Nenhum dado de seed é inserido: a lista de referência segue vazia
        (decisão 5) e o primeiro administrador nasce em ``POST /auth/administrador``.
        """
        logger.info("Mente Fria API iniciando (ambiente=%s)", settings.env.value)
        if settings.env is not Environment.PRODUCTION:
            init_db(settings=settings)
            logger.info("schema verificado via init_db (ambiente=%s)", settings.env.value)
        else:
            logger.info(
                "ambiente de produção: criação de schema não é feita pela aplicação"
            )
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
    # Fase 5 (P5-66): o documento publicado espelha o contrato, sem o 422 automático.
    _alinhar_openapi_ao_contrato(app)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:create_app", factory=True)
