"""Testes de unidades de medida (Fase 6 — P6-08). Restritas a `ADMINISTRADOR`."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from .conftest import assert_api_error


def test_cadastrar_unidade_responde_201_com_location(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/unidades-medida", headers=admin, json={"unidadeMedida": "g", "porcaoPadrao": 100}
    )
    assert resposta.status_code == 201
    assert resposta.json() == {"unidadeMedida": "g", "porcaoPadrao": 100}
    assert resposta.headers["location"] == "/api/v1/unidades-medida/g"


def test_unidade_duplicada_resulta_em_409(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("g", 100)
    resposta = client.post(
        "/api/v1/unidades-medida", headers=admin, json={"unidadeMedida": "g", "porcaoPadrao": 50}
    )
    assert_api_error(resposta, 409, "CONFLICT")


def test_consultar_unidade(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("ml", 50)
    corpo = client.get("/api/v1/unidades-medida/ml", headers=admin).json()
    assert corpo == {"unidadeMedida": "ml", "porcaoPadrao": 50}


def test_consultar_unidade_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/unidades-medida/xx", headers=admin), 404, "NOT_FOUND")


def test_atualizar_porcao_padrao(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("g", 100)
    resposta = client.put(
        "/api/v1/unidades-medida/g", headers=admin, json={"porcaoPadrao": 250}
    )
    assert resposta.status_code == 200
    assert resposta.json()["porcaoPadrao"] == 250


def test_atualizar_porcao_padrao_nao_recalcula_ingredientes_existentes(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    """SPEC §6.2: a porção padrão é sugestão para **novos** ingredientes."""
    ingrediente_id = criar_ingrediente(porcao_padrao=100)
    antes = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()
    client.put("/api/v1/unidades-medida/g", headers=admin, json={"porcaoPadrao": 999})
    depois = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()
    assert Decimal(str(depois["porcaoPadrao"])) == Decimal(str(antes["porcaoPadrao"])) == 100


def test_atualizar_unidade_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(
        client.put("/api/v1/unidades-medida/xx", headers=admin, json={"porcaoPadrao": 10}), 404
    )


def test_excluir_unidade_livre_responde_204_sem_corpo(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("un", 1)
    resposta = client.delete("/api/v1/unidades-medida/un", headers=admin)
    assert resposta.status_code == 204
    assert resposta.content == b""
    assert client.get("/api/v1/unidades-medida/un", headers=admin).status_code == 404


def test_excluir_unidade_em_uso_resulta_em_409(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    criar_ingrediente(unidade="g")
    assert_api_error(client.delete("/api/v1/unidades-medida/g", headers=admin), 409, "CONFLICT")
    assert client.get("/api/v1/unidades-medida/g", headers=admin).status_code == 200


def test_excluir_unidade_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.delete("/api/v1/unidades-medida/xx", headers=admin), 404)


# --- validação e limites ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("corpo", "campo"),
    [
        ({"unidadeMedida": "", "porcaoPadrao": 1}, "unidadeMedida"),
        ({"unidadeMedida": "x" * 21, "porcaoPadrao": 1}, "unidadeMedida"),
        ({"unidadeMedida": "g", "porcaoPadrao": 0}, "porcaoPadrao"),
        ({"unidadeMedida": "g", "porcaoPadrao": 10_000_000}, "porcaoPadrao"),
    ],
)
def test_limites_do_contrato_sao_aplicados(
    client: TestClient, admin: dict[str, str], corpo: dict, campo: str
) -> None:
    erro = assert_api_error(
        client.post("/api/v1/unidades-medida", headers=admin, json=corpo), 422
    )
    assert erro["detalhes"][0]["campo"] == campo


def test_update_aceita_somente_porcao_padrao(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("g", 100)
    resposta = client.put(
        "/api/v1/unidades-medida/g",
        headers=admin,
        json={"porcaoPadrao": 10, "unidadeMedida": "kg"},
    )
    assert_api_error(resposta, 422)


# --- paginação e autorização -----------------------------------------------------------


def test_listagem_pagina_e_ordena(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    for unidade in ("g", "kg", "ml"):
        criar_unidade(unidade, 10)
    pagina = client.get(
        "/api/v1/unidades-medida", headers=admin, params={"size": 2, "sort": "unidadeMedida,desc"}
    ).json()
    assert pagina["paginacao"] == {"page": 0, "size": 2, "totalElements": 3, "totalPages": 2}
    assert pagina["data"][0]["unidadeMedida"] == "ml"


def test_listagem_nao_declara_parametro_q(client: TestClient, admin: dict[str, str]) -> None:
    """O contrato não declara `q` nesta operação: o parâmetro é ignorado, não filtra."""
    resposta = client.get("/api/v1/unidades-medida", headers=admin, params={"q": "qualquer"})
    assert resposta.status_code == 200


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/api/v1/unidades-medida"),
        ("POST", "/api/v1/unidades-medida"),
        ("GET", "/api/v1/unidades-medida/g"),
        ("PUT", "/api/v1/unidades-medida/g"),
        ("DELETE", "/api/v1/unidades-medida/g"),
    ],
)
def test_unidades_exigem_administrador(
    client: TestClient, funcionario: dict[str, str], metodo: str, caminho: str
) -> None:
    resposta = client.request(metodo, caminho, headers=funcionario, json={"porcaoPadrao": 1})
    assert_api_error(resposta, 403, "FORBIDDEN")


def test_unidades_exigem_autenticacao(client: TestClient) -> None:
    assert_api_error(client.get("/api/v1/unidades-medida"), 401)
