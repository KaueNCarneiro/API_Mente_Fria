"""Engine, SessionLocal, ``get_db``, inicialização de schema e seed (Fase 3 — P3-18 a P3-21).

Princípios:
- A URL do banco vem exclusivamente de ``config.Settings`` (nada duplicado aqui).
- Nada é criado na importação: a ``Engine`` é construída sob demanda (``get_engine``),
  de modo que importar este módulo não exige variáveis de ambiente.
- Escritas gerenciam a transação explicitamente nos services (``commit``/``rollback``);
  ``get_db`` apenas abre e fecha a sessão.
- Migrações: **decisão pendente** (PLAN.md, decisão 4). ``init_db`` usa
  ``metadata.create_all`` apenas em ``local``/``test`` e é recusada em ``production``.
"""

from __future__ import annotations

import logging
from collections.abc import Generator, Iterable
from decimal import Decimal
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import Environment, Settings, get_settings
from .models import Base, UnidadeMedidaModel

logger = logging.getLogger(__name__)

# Sessão sem autoflush (flush explícito nos services); ``expire_on_commit`` mantém o
# padrão True para que saldos derivados sejam relidos após cada commit.
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=True)


def _is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def _is_sqlite_memory(url: str) -> bool:
    parsed = make_url(url)
    return parsed.get_backend_name() == "sqlite" and parsed.database in (None, "", ":memory:")


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Cria uma ``Engine`` a partir de ``Settings`` (sem cache; testes podem chamar à vontade).

    SQLite: ``check_same_thread=False`` (o FastAPI atende em threads distintas) e
    ``PRAGMA foreign_keys=ON`` em cada conexão — sem isso o SQLite ignora FKs e os
    ``ON DELETE RESTRICT`` do modelo não seriam aplicados. Banco em memória usa
    ``StaticPool`` (uma única conexão compartilhada entre threads, caso contrário cada
    thread veria um banco vazio diferente).
    """
    settings = settings or get_settings()
    url = settings.database_url

    kwargs: dict[str, Any] = {}
    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_sqlite_memory(url):
            kwargs["poolclass"] = StaticPool

    engine = create_engine(url, **kwargs)

    if _is_sqlite(url):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    """``Engine`` única do processo, criada na primeira utilização."""
    return create_db_engine(get_settings())


def get_db() -> Generator[Session, None, None]:
    """Dependência FastAPI: uma sessão por requisição, sempre encerrada ao final.

    Não faz ``commit`` automático: cada escrita decide sua transação. Uma transação
    pendente ao encerrar é descartada (``close`` faz rollback).
    """
    session = SessionLocal(bind=get_engine())
    try:
        yield session
    finally:
        session.close()


def init_db(engine: Engine | None = None, settings: Settings | None = None) -> None:
    """Cria as tabelas via ``metadata.create_all`` — somente ``local`` e ``test``.

    Não é uma estratégia de migração (decisão 4 pendente): não altera tabelas
    existentes e é recusada em ``production``. Deve ser chamada explicitamente; nenhum
    código a executa automaticamente.
    """
    settings = settings or get_settings()
    if settings.env is Environment.PRODUCTION:
        raise RuntimeError(
            "init_db não é permitida em production: a estratégia de migrações ainda "
            "não foi aprovada (PLAN.md, decisão 4)"
        )
    Base.metadata.create_all(engine or get_engine())


# ---------------------------------------------------------------------------
# Seed (P3-20)
# ---------------------------------------------------------------------------

# Dados de referência APROVADOS (unidade, porção padrão). Vazio de propósito: não há lista
# aprovada (PLAN.md, decisão 5). Nenhuma unidade, usuário ou registro de exemplo é
# inventado. O administrador NÃO é criado aqui: o primeiro admin nasce exclusivamente
# em ``POST /api/v1/auth/administrador``.
UNIDADES_MEDIDA_REFERENCIA: tuple[tuple[str, Decimal], ...] = ()


def seed_reference_data(
    session: Session,
    unidades_medida: Iterable[tuple[str, Decimal]] = UNIDADES_MEDIDA_REFERENCIA,
) -> int:
    """Insere dados de referência ausentes; idempotente. Retorna quantos registros criou.

    Não altera registros já existentes (ex.: ``porcaoPadrao`` editada depois) e faz o
    ``commit`` ao final somente se algo foi inserido.
    """
    criados = 0
    for unidade, porcao_padrao in unidades_medida:
        if session.scalar(
            select(UnidadeMedidaModel.unidadeMedida).where(
                UnidadeMedidaModel.unidadeMedida == unidade
            )
        ):
            continue
        session.add(UnidadeMedidaModel(unidadeMedida=unidade, porcaoPadrao=porcao_padrao))
        criados += 1
    if criados:
        session.commit()
    logger.info("seed de referência: %d registro(s) criado(s)", criados)
    return criados
