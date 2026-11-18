"""Fixtures compartilhadas da suíte (Fase 6 — P6-02, P6-03).

Isolamento (SPEC §9.10): cada teste recebe um banco SQLite **em memória, novo**, com as
tabelas criadas na hora e descartadas ao final. O banco de desenvolvimento
(`mente_fria.db`) nunca é tocado — a configuração de teste é montada aqui e a dependência
`get_db` é sobrescrita na aplicação.

As variáveis `MENTE_FRIA_*` são definidas **antes** de qualquer import da aplicação: a
configuração é lida na importação de `config.get_settings`, e um ambiente herdado da
máquina poderia apontar para produção.

Fixtures de identidade usam os perfis reais do domínio (`ADMINISTRADOR`, `FUNCIONARIO`) e
e-mails próprios da suíte — nada de `ADMIN`/`MEMBER` nem de usuários de demonstração de
outros projetos.
"""

from __future__ import annotations

import os

# --- ambiente de teste, antes de importar a aplicação --------------------------------
for _chave in [c for c in os.environ if c.startswith("MENTE_FRIA_")]:
    del os.environ[_chave]
os.environ.update(
    MENTE_FRIA_ENV="test",
    MENTE_FRIA_DATABASE_URL="sqlite:///:memory:",
    MENTE_FRIA_JWT_SECRET_KEY="segredo-exclusivo-da-suite-de-testes",
    MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS="3600",
    MENTE_FRIA_LOG_LEVEL="WARNING",
)

import json
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from src.api.config import Settings
from src.api.database import SessionLocal, create_db_engine, get_db, init_db
from src.api.main import create_app
from src.api.models import Base, hoje

CONTRATO = Path(__file__).resolve().parents[3] / "Mente Fria API.openapi.json"

SENHA_PADRAO = "SenhaDeTeste#2026"
EMAIL_ADMIN = "administradora@mentefria.com"
EMAIL_FUNCIONARIO = "funcionario@mentefria.com"


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def contrato() -> dict[str, Any]:
    """O `Mente Fria API.openapi.json` carregado: fonte da verdade dos testes de contrato."""
    return json.loads(CONTRATO.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Banco e aplicação
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Configuração de teste explícita (não depende de `.env` nem de segredo real)."""
    return Settings(
        env="test",
        database_url="sqlite:///:memory:",
        jwt_secret_key="segredo-exclusivo-da-suite-de-testes",
        jwt_access_token_expire_seconds=3600,
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """Banco em memória novo por teste, com as tabelas criadas e descartadas ao final."""
    eng = create_db_engine(settings)
    init_db(eng, settings)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Sessão direta ao banco do teste, para montar cenários e inspecionar o estado."""
    sessao = SessionLocal(bind=engine)
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture
def app(settings: Settings, engine: Engine) -> FastAPI:
    """Aplicação real com `get_db` apontando para o banco isolado do teste."""
    aplicacao = create_app(settings)

    def get_db_de_teste() -> Iterator[Session]:
        sessao = SessionLocal(bind=engine)
        try:
            yield sessao
        finally:
            sessao.close()

    aplicacao.dependency_overrides[get_db] = get_db_de_teste
    return aplicacao


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Cliente HTTP. `raise_server_exceptions=False` deixa o handler de 500 responder."""
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


# ---------------------------------------------------------------------------
# Identidades e tokens (P6-03)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_token(client: TestClient) -> str:
    """Faz o bootstrap do primeiro ADMINISTRADOR pela própria API e devolve o token."""
    resposta = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    )
    assert resposta.status_code == 201, resposta.text
    login = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN, "senha": SENHA_PADRAO}
    )
    assert login.status_code == 200, login.text
    return str(login.json()["accessToken"])


@pytest.fixture
def admin(admin_token: str) -> dict[str, str]:
    """Cabeçalho `Authorization` de um ADMINISTRADOR."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def funcionario_token(client: TestClient, admin: dict[str, str]) -> str:
    """Cadastra um FUNCIONARIO (o servidor define o perfil) e devolve o token dele."""
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Caio Funcionário", "email": EMAIL_FUNCIONARIO, "senha": SENHA_PADRAO},
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["perfil"] == "FUNCIONARIO"
    login = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_FUNCIONARIO, "senha": SENHA_PADRAO}
    )
    assert login.status_code == 200, login.text
    return str(login.json()["accessToken"])


@pytest.fixture
def funcionario(funcionario_token: str) -> dict[str, str]:
    """Cabeçalho `Authorization` de um FUNCIONARIO."""
    return {"Authorization": f"Bearer {funcionario_token}"}


@pytest.fixture
def usuario_admin_id(client: TestClient, admin: dict[str, str]) -> int:
    """Id do administrador criado no bootstrap."""
    pagina = client.get("/api/v1/usuarios", headers=admin).json()
    return int(next(u["id"] for u in pagina["data"] if u["perfil"] == "ADMINISTRADOR"))


# ---------------------------------------------------------------------------
# Construtores de cenário
# ---------------------------------------------------------------------------


@pytest.fixture
def criar_unidade(client: TestClient, admin: dict[str, str]) -> Callable[..., str]:
    """Cria uma unidade de medida e devolve a chave textual."""

    def _criar(unidade: str = "g", porcao_padrao: float = 100) -> str:
        resposta = client.post(
            "/api/v1/unidades-medida",
            headers=admin,
            json={"unidadeMedida": unidade, "porcaoPadrao": porcao_padrao},
        )
        assert resposta.status_code == 201, resposta.text
        return str(resposta.json()["unidadeMedida"])

    return _criar


@pytest.fixture
def criar_ingrediente(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> Callable[..., int]:
    """Cria um ingrediente (criando a unidade, se preciso) e devolve o id."""
    criadas: set[str] = set()

    def _criar(
        nome: str = "Açaí",
        unidade: str = "g",
        custo_unitario: float = 0.05,
        porcao_padrao: float = 100,
        quantidade_minima: float = 0,
    ) -> int:
        if unidade not in criadas:
            existe = client.get(f"/api/v1/unidades-medida/{unidade}", headers=admin)
            if existe.status_code == 404:
                criar_unidade(unidade, porcao_padrao)
            criadas.add(unidade)
        resposta = client.post(
            "/api/v1/ingredientes",
            headers=admin,
            json={
                "nome": nome,
                "unidadeMedida": unidade,
                "custoUnitario": custo_unitario,
                "porcaoPadrao": porcao_padrao,
                "quantidadeMinima": quantidade_minima,
            },
        )
        assert resposta.status_code == 201, resposta.text
        return int(resposta.json()["id"])

    return _criar


@pytest.fixture
def entrada_estoque(client: TestClient, admin: dict[str, str]) -> Callable[..., int]:
    """Registra uma ENTRADA (lote) e devolve o id da movimentação."""

    def _entrada(
        ingrediente_id: int,
        quantidade: float,
        validade: date | None = None,
        observacao: str | None = None,
    ) -> int:
        corpo: dict[str, Any] = {
            "ingredienteId": ingrediente_id,
            "tipo": "ENTRADA",
            "quantidade": quantidade,
        }
        if validade is not None:
            corpo["dataValidade"] = validade.isoformat()
        if observacao is not None:
            corpo["observacao"] = observacao
        resposta = client.post("/api/v1/movimentacoes-estoque", headers=admin, json=corpo)
        assert resposta.status_code == 201, resposta.text
        return int(resposta.json()["id"])

    return _entrada


@pytest.fixture
def criar_produto(client: TestClient, admin: dict[str, str]) -> Callable[..., int]:
    """Cria um produto com composição e devolve o id."""

    def _criar(
        nome: str = "Açaí 300ml",
        preco_venda: float = 15.00,
        composicao: list[dict[str, Any]] | None = None,
        ativo: bool = True,
    ) -> int:
        resposta = client.post(
            "/api/v1/produtos",
            headers=admin,
            json={
                "nome": nome,
                "precoVenda": preco_venda,
                "ativo": ativo,
                "composicao": composicao or [],
            },
        )
        assert resposta.status_code == 201, resposta.text
        return int(resposta.json()["id"])

    return _criar


@pytest.fixture
def cenario_venda(
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    criar_produto: Callable[..., int],
) -> dict[str, Any]:
    """Cenário mínimo de venda: ingrediente com lote válido e produto que o consome.

    Devolve ids e as quantidades usadas, para que cada teste afirme sobre números
    conhecidos em vez de recalcular o cenário.
    """
    ingrediente_id = criar_ingrediente(quantidade_minima=100)
    lote_id = entrada_estoque(ingrediente_id, 1000, hoje() + timedelta(days=30))
    produto_id = criar_produto(
        composicao=[{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 200}]
    )
    return {
        "ingredienteId": ingrediente_id,
        "loteId": lote_id,
        "produtoId": produto_id,
        "quantidadeLote": Decimal(1000),
        "consumoPorUnidade": Decimal(200),
        "precoVenda": Decimal("15.00"),
    }


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def campos_do_api_error() -> set[str]:
    """Campos exatos do envelope `ApiError` do contrato."""
    return {"codigo", "mensagem", "detalhes", "timestamp", "caminho", "correlationId"}


def assert_api_error(resposta: Any, status: int, codigo: str | None = None) -> dict[str, Any]:
    """Confere status e envelope `ApiError`; devolve o corpo para asserções adicionais."""
    assert resposta.status_code == status, resposta.text
    corpo = resposta.json()
    assert set(corpo) == campos_do_api_error(), corpo
    assert "detail" not in corpo, corpo
    assert not {"type", "title", "status", "instance"} & set(corpo), corpo
    assert isinstance(corpo["detalhes"], list)
    assert corpo["caminho"].startswith("/api/v1")
    assert corpo["correlationId"]
    if codigo is not None:
        assert corpo["codigo"] == codigo, corpo
    return dict(corpo)
