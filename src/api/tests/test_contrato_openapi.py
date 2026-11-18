"""Conformidade entre o OpenAPI gerado e o contrato (Fase 6 — P6-23, P6-19).

Para cada uma das 44 operações, compara o documento que a aplicação publica com o
`Mente Fria API.openapi.json`: método, caminho, tags, parâmetros, corpo, status, media
types, headers, schema das respostas e `security`. Também confere a matriz RBAC.

O contrato é a fonte da verdade (AGENTS.md §2): divergência aqui é erro da implementação,
não do arquivo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from src.api.main import rotas_da_api
from src.api.security import MATRIZ_RBAC, PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO

RAIZ = Path(__file__).resolve().parents[3]
CONTRATO = json.loads((RAIZ / "Mente Fria API.openapi.json").read_text(encoding="utf-8"))
METODOS = ("get", "post", "put", "patch", "delete")


def _operacoes(documento: dict[str, Any]) -> dict[str, dict[str, Any]]:
    saida: dict[str, dict[str, Any]] = {}
    for caminho, item in documento["paths"].items():
        for metodo in METODOS:
            operacao = item.get(metodo)
            if operacao:
                saida[operacao["operationId"]] = {
                    "caminho": caminho,
                    "metodo": metodo,
                    "op": operacao,
                    "item": item,
                }
    return saida


OPERACOES_DO_CONTRATO = _operacoes(CONTRATO)
IDS = sorted(OPERACOES_DO_CONTRATO)


@pytest.fixture(scope="module")
def gerado() -> dict[str, Any]:
    """Documento OpenAPI publicado pela aplicação."""
    from src.api.config import Settings
    from src.api.main import create_app

    configuracao = Settings(
        env="test",
        database_url="sqlite:///:memory:",
        jwt_secret_key="segredo-exclusivo-da-suite-de-testes",
        jwt_access_token_expire_seconds=3600,
    )
    return create_app(configuracao).openapi()


@pytest.fixture(scope="module")
def operacoes_geradas(gerado: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _operacoes(gerado)


def _parametros(documento: dict[str, Any], dados: dict[str, Any]) -> set[tuple[str, str, bool]]:
    brutos = list(dados["item"].get("parameters", [])) + list(dados["op"].get("parameters", []))
    saida: set[tuple[str, str, bool]] = set()
    for parametro in brutos:
        if "$ref" in parametro:
            parametro = documento["components"]["parameters"][parametro["$ref"].split("/")[-1]]
        saida.add(
            (parametro["name"], parametro["in"], bool(parametro.get("required", parametro["in"] == "path")))
        )
    return saida


def _schema(conteudo: dict[str, Any] | None) -> str | None:
    if not conteudo:
        return None
    esquema = conteudo.get("schema") or {}
    if "$ref" in esquema:
        return str(esquema["$ref"].split("/")[-1])
    return esquema.get("type")


def _resolver_resposta(documento: dict[str, Any], resposta: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in resposta:
        return dict(documento["components"]["responses"][resposta["$ref"].split("/")[-1]])
    return resposta


# --- inventário ---------------------------------------------------------------------------------


def test_26_caminhos_registrados(gerado: dict[str, Any]) -> None:
    assert len(gerado["paths"]) == 26
    assert set(gerado["paths"]) == set(CONTRATO["paths"])


def test_44_operacoes_registradas(operacoes_geradas: dict[str, Any]) -> None:
    assert len(operacoes_geradas) == 44
    assert set(operacoes_geradas) == set(OPERACOES_DO_CONTRATO)


def test_nenhuma_rota_duplicada(gerado: dict[str, Any]) -> None:
    from src.api.config import Settings
    from src.api.main import create_app

    app: FastAPI = create_app(
        Settings(
            env="test",
            database_url="sqlite:///:memory:",
            jwt_secret_key="segredo-exclusivo-da-suite-de-testes",
            jwt_access_token_expire_seconds=3600,
        )
    )
    assinaturas = [
        (rota.operation_id, tuple(sorted(rota.methods)))
        for rota in rotas_da_api(app)
        if rota.operation_id
    ]
    assert len(assinaturas) == 44
    assert len(set(assinaturas)) == 44


def test_nenhuma_rota_de_outro_projeto(gerado: dict[str, Any]) -> None:
    for termo in ("/auth/me", "/tasks", "/projects"):
        assert not any(termo in caminho for caminho in gerado["paths"]), termo


# --- comparação operação por operação --------------------------------------------------------------


@pytest.mark.parametrize("operation_id", IDS)
def test_metodo_caminho_e_tags(
    operation_id: str, operacoes_geradas: dict[str, Any]
) -> None:
    esperado = OPERACOES_DO_CONTRATO[operation_id]
    obtido = operacoes_geradas[operation_id]
    assert (obtido["metodo"], obtido["caminho"]) == (esperado["metodo"], esperado["caminho"])
    assert obtido["op"].get("tags") == esperado["op"].get("tags")


@pytest.mark.parametrize("operation_id", IDS)
def test_parametros(
    operation_id: str, operacoes_geradas: dict[str, Any], gerado: dict[str, Any]
) -> None:
    esperado = _parametros(CONTRATO, OPERACOES_DO_CONTRATO[operation_id])
    obtido = _parametros(gerado, operacoes_geradas[operation_id])
    assert obtido == esperado


@pytest.mark.parametrize("operation_id", IDS)
def test_schema_do_corpo(operation_id: str, operacoes_geradas: dict[str, Any]) -> None:
    esperado = _schema(
        (OPERACOES_DO_CONTRATO[operation_id]["op"].get("requestBody") or {})
        .get("content", {})
        .get("application/json")
    )
    obtido = _schema(
        (operacoes_geradas[operation_id]["op"].get("requestBody") or {})
        .get("content", {})
        .get("application/json")
    )
    assert obtido == esperado


@pytest.mark.parametrize("operation_id", IDS)
def test_status_declarados(operation_id: str, operacoes_geradas: dict[str, Any]) -> None:
    esperado = set(OPERACOES_DO_CONTRATO[operation_id]["op"]["responses"])
    obtido = set(operacoes_geradas[operation_id]["op"]["responses"])
    assert obtido == esperado


@pytest.mark.parametrize("operation_id", IDS)
def test_media_types_headers_e_schemas_das_respostas(
    operation_id: str, operacoes_geradas: dict[str, Any], gerado: dict[str, Any]
) -> None:
    esperadas = OPERACOES_DO_CONTRATO[operation_id]["op"]["responses"]
    obtidas = operacoes_geradas[operation_id]["op"]["responses"]
    for codigo, bruta in esperadas.items():
        esperada = _resolver_resposta(CONTRATO, bruta)
        obtida = _resolver_resposta(gerado, obtidas[codigo])
        tipos_esperados = set((esperada.get("content") or {}).keys())
        tipos_obtidos = set((obtida.get("content") or {}).keys())
        assert tipos_obtidos == tipos_esperados, (operation_id, codigo)
        if codigo == "204":
            assert not tipos_obtidos, "204 não pode declarar corpo"
        assert set(obtida.get("headers") or {}) >= set(esperada.get("headers") or {})
        if tipos_esperados == {"application/json"}:
            assert _schema(obtida["content"]["application/json"]) == _schema(
                esperada["content"]["application/json"]
            ), (operation_id, codigo)


@pytest.mark.parametrize("operation_id", IDS)
def test_security_por_operacao(operation_id: str, operacoes_geradas: dict[str, Any]) -> None:
    esperado = OPERACOES_DO_CONTRATO[operation_id]["op"].get("security", CONTRATO.get("security"))
    obtido = operacoes_geradas[operation_id]["op"].get("security")
    if esperado == []:
        assert not obtido, f"{operation_id} deveria ser pública"
    else:
        assert obtido, f"{operation_id} deveria exigir Bearer"
        assert "HTTPBearer" in json.dumps(obtido)


# --- matriz RBAC (P6-19) -------------------------------------------------------------------------


def test_matriz_cobre_exatamente_as_operacoes_do_contrato() -> None:
    assert set(MATRIZ_RBAC) == set(OPERACOES_DO_CONTRATO)


def test_contagem_da_matriz() -> None:
    publicas = [p for p in MATRIZ_RBAC.values() if p == ()]
    administrador = [p for p in MATRIZ_RBAC.values() if p == (PERFIL_ADMINISTRADOR,)]
    ambos = [
        p for p in MATRIZ_RBAC.values() if p == (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO)
    ]
    so_autenticadas = [p for p in MATRIZ_RBAC.values() if p is None]
    assert (len(publicas), len(administrador), len(ambos), len(so_autenticadas)) == (3, 27, 5, 9)


@pytest.mark.parametrize("operation_id", IDS)
def test_matriz_reflete_a_descricao_da_operacao(operation_id: str) -> None:
    dados = OPERACOES_DO_CONTRATO[operation_id]
    descricao = f"{dados['op'].get('summary', '')} {dados['op'].get('description', '')}"
    perfis = MATRIZ_RBAC[operation_id]
    publica = dados["op"].get("security", CONTRATO.get("security")) == []

    if publica:
        assert perfis == (), operation_id
        return

    assert "401" in dados["op"]["responses"] and "403" in dados["op"]["responses"]
    if "ADMINISTRADOR e FUNCIONARIO" in descricao:
        assert perfis == (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO), operation_id
    elif "Restrito ao perfil ADMINISTRADOR" in descricao or "somente ADMINISTRADOR" in descricao:
        assert perfis == (PERFIL_ADMINISTRADOR,), operation_id
    elif "ADMINISTRADOR" not in descricao and "FUNCIONARIO" not in descricao:
        assert perfis is None, f"{operation_id}: a descrição não restringe perfil"
