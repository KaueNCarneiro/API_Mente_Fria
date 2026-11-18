"""Testes de alertas de reposição e validade (Fase 6 — P6-13).

Exigem Bearer; o contrato não restringe perfil nestas operações.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.models import hoje

from .conftest import assert_api_error

# --- reposição ----------------------------------------------------------------------------


def test_ingrediente_abaixo_do_minimo_gera_alerta(
    client: TestClient, funcionario: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente(nome="Açaí", quantidade_minima=500)
    corpo = client.get("/api/v1/alertas/reposicao", headers=funcionario).json()
    assert set(corpo) == {"itens"}
    assert len(corpo["itens"]) == 1
    alerta = corpo["itens"][0]
    assert set(alerta) == {
        "ingredienteId",
        "nomeIngrediente",
        "quantidadeEstoqueValido",
        "quantidadeMinima",
        "unidadeMedida",
        "deficit",
    }
    assert alerta["ingredienteId"] == ingrediente_id
    assert Decimal(str(alerta["deficit"])) == 500


def test_deficit_considera_o_saldo_existente(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente(quantidade_minima=500)
    entrada_estoque(ingrediente_id, 200)
    alerta = client.get("/api/v1/alertas/reposicao", headers=funcionario).json()["itens"][0]
    assert Decimal(str(alerta["quantidadeEstoqueValido"])) == 200
    assert Decimal(str(alerta["deficit"])) == 300


def test_ingrediente_abastecido_nao_gera_alerta(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente(quantidade_minima=100)
    entrada_estoque(ingrediente_id, 500)
    assert client.get("/api/v1/alertas/reposicao", headers=funcionario).json()["itens"] == []


def test_alerta_usa_saldo_valido_e_nao_conta_vencido(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente(quantidade_minima=100)
    entrada_estoque(ingrediente_id, 999, hoje() - timedelta(days=1))
    alerta = client.get("/api/v1/alertas/reposicao", headers=funcionario).json()["itens"][0]
    assert Decimal(str(alerta["quantidadeEstoqueValido"])) == 0
    assert Decimal(str(alerta["deficit"])) == 100


def test_somente_criticos_filtra_saldo_zero(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    zerado = criar_ingrediente(nome="Zerado", quantidade_minima=100)
    parcial = criar_ingrediente(nome="Parcial", quantidade_minima=100)
    entrada_estoque(parcial, 50)

    todos = client.get("/api/v1/alertas/reposicao", headers=funcionario).json()["itens"]
    criticos = client.get(
        "/api/v1/alertas/reposicao", headers=funcionario, params={"somenteCriticos": True}
    ).json()["itens"]

    assert {i["ingredienteId"] for i in todos} == {zerado, parcial}
    assert [i["ingredienteId"] for i in criticos] == [zerado]


# --- validade ------------------------------------------------------------------------------


def test_lote_proximo_do_vencimento(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    lote = entrada_estoque(ingrediente_id, 100, hoje() + timedelta(days=3))
    itens = client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"]
    assert len(itens) == 1
    alerta = itens[0]
    assert set(alerta) == {
        "movimentacaoId",
        "ingredienteId",
        "nomeIngrediente",
        "dataValidade",
        "quantidadeRestante",
        "diasAteVencimento",
        "situacao",
    }
    assert alerta["movimentacaoId"] == lote
    assert alerta["situacao"] == "PROXIMO_VENCIMENTO"
    assert alerta["diasAteVencimento"] == 3


def test_lote_vencido_tem_dias_negativos(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100, hoje() - timedelta(days=2))
    alerta = client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"][0]
    assert alerta["situacao"] == "VENCIDO"
    assert alerta["diasAteVencimento"] == -2


def test_dias_antecedencia_define_a_janela(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100, hoje() + timedelta(days=20))
    padrao = client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"]
    ampliado = client.get(
        "/api/v1/alertas/validade", headers=funcionario, params={"diasAntecedencia": 30}
    ).json()["itens"]
    assert padrao == []  # padrão do contrato: 7 dias
    assert len(ampliado) == 1


def test_incluir_vencidos_false_remove_os_vencidos(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 50, hoje() - timedelta(days=1))
    entrada_estoque(ingrediente_id, 50, hoje() + timedelta(days=2))

    com = client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"]
    sem = client.get(
        "/api/v1/alertas/validade", headers=funcionario, params={"incluirVencidos": False}
    ).json()["itens"]
    assert len(com) == 2
    assert [i["situacao"] for i in sem] == ["PROXIMO_VENCIMENTO"]


def test_lote_sem_validade_nao_entra_no_alerta(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    """O contrato considera somente linhas de ENTRADA com `dataValidade` informada."""
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100)
    assert client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"] == []


def test_lote_esgotado_sai_do_alerta(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100, hoje() + timedelta(days=2))
    client.post(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        json={"ingredienteId": ingrediente_id, "tipo": "SAIDA", "quantidade": 100},
    )
    assert client.get("/api/v1/alertas/validade", headers=funcionario).json()["itens"] == []


@pytest.mark.parametrize("dias", [-1, 366])
def test_dias_antecedencia_fora_dos_limites_resulta_em_400(
    client: TestClient, funcionario: dict[str, str], dias: int
) -> None:
    resposta = client.get(
        "/api/v1/alertas/validade", headers=funcionario, params={"diasAntecedencia": dias}
    )
    assert_api_error(resposta, 400, "BAD_REQUEST")


# --- autorização ------------------------------------------------------------------------------


@pytest.mark.parametrize("papel", ["admin", "funcionario"])
@pytest.mark.parametrize("caminho", ["/api/v1/alertas/reposicao", "/api/v1/alertas/validade"])
def test_alertas_aceitam_ambos_os_perfis(
    client: TestClient, request: pytest.FixtureRequest, papel: str, caminho: str
) -> None:
    headers = request.getfixturevalue(papel)
    assert client.get(caminho, headers=headers).status_code == 200


@pytest.mark.parametrize("caminho", ["/api/v1/alertas/reposicao", "/api/v1/alertas/validade"])
def test_alertas_exigem_autenticacao(client: TestClient, caminho: str) -> None:
    assert_api_error(client.get(caminho), 401, "UNAUTHORIZED")
