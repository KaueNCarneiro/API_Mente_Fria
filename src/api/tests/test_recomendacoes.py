"""Testes de recomendações e sugestões de marketing (Fase 6 — P6-14).

Restritas a `ADMINISTRADOR`. Resultados são calculados sob demanda e **não** persistem
histórico; a indisponibilidade do solver vira `503` com `ApiError`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.integrations import optimizer
from src.api.models import hoje

from .conftest import assert_api_error


@pytest.fixture
def solver_indisponivel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula ausência/falha do solver sem desinstalar a dependência."""

    def _falhar() -> None:
        raise optimizer.SolverIndisponivelError("Solver de otimização indisponível.")

    monkeypatch.setattr(optimizer, "_pulp", _falhar)


# --- produção --------------------------------------------------------------------------------


def test_recomendacao_de_producao_devolve_o_schema_do_contrato(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.post("/api/v1/recomendacoes/producao", headers=admin)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "calculadoEm",
        "criterioOtimizacao",
        "lucroTotalEstimado",
        "itens",
        "observacao",
    }
    assert corpo["criterioOtimizacao"] == "LUCRO_ESTIMADO"


def test_producao_recomenda_quantidades_inteiras_dentro_do_estoque(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    """1000 g de estoque e 200 g por unidade: no máximo 5 unidades."""
    itens = client.post("/api/v1/recomendacoes/producao", headers=admin).json()["itens"]
    assert len(itens) == 1
    item = itens[0]
    assert isinstance(item["quantidadeRecomendada"], int)
    assert item["quantidadeRecomendada"] == 5
    assert item["produtoId"] == cenario_venda["produtoId"]


def test_producao_calcula_lucro_unitario_e_total(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    """Preço 15,00 menos custo (200 g × 0,05) = 5,00 por unidade; 5 unidades = 25,00."""
    corpo = client.post("/api/v1/recomendacoes/producao", headers=admin).json()
    item = corpo["itens"][0]
    assert Decimal(str(item["lucroEstimadoUnitario"])) == Decimal("5.00")
    assert Decimal(str(item["lucroEstimadoTotal"])) == Decimal("25.00")
    assert Decimal(str(corpo["lucroTotalEstimado"])) == Decimal("25.00")


def test_producao_ignora_estoque_vencido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    criar_produto: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 1000, hoje() - timedelta(days=1))
    criar_produto(composicao=[{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 100}])
    corpo = client.post("/api/v1/recomendacoes/producao", headers=admin).json()
    assert corpo["itens"] == []
    assert Decimal(str(corpo["lucroTotalEstimado"])) == 0


def test_producao_ignora_produto_desativado(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    client.delete(f"/api/v1/produtos/{cenario_venda['produtoId']}", headers=admin)
    assert client.post("/api/v1/recomendacoes/producao", headers=admin).json()["itens"] == []


def test_producao_sem_produtos_responde_200_com_lista_vazia(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.post("/api/v1/recomendacoes/producao", headers=admin).json()
    assert corpo["itens"] == []


def test_producao_nao_persiste_historico(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    """Sob demanda: calcular não altera estoque, pedidos nem movimentações."""
    antes = (
        client.get(f"/api/v1/ingredientes/{cenario_venda['ingredienteId']}", headers=admin).json(),
        client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"],
        client.get("/api/v1/movimentacoes-estoque", headers=admin).json()["paginacao"]["totalElements"],
    )
    client.post("/api/v1/recomendacoes/producao", headers=admin)
    depois = (
        client.get(f"/api/v1/ingredientes/{cenario_venda['ingredienteId']}", headers=admin).json(),
        client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"],
        client.get("/api/v1/movimentacoes-estoque", headers=admin).json()["paginacao"]["totalElements"],
    )
    assert antes == depois


# --- reposição --------------------------------------------------------------------------------


def test_reposicao_devolve_o_schema_do_contrato(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    criar_ingrediente(quantidade_minima=100)
    resposta = client.post(
        "/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 30, "orcamento": 100}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "calculadoEm",
        "periodoDias",
        "orcamento",
        "custoTotalEstimado",
        "itens",
    }
    assert corpo["periodoDias"] == 30


def test_reposicao_respeita_o_orcamento(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    criar_ingrediente(nome="Caro", custo_unitario=1.00, quantidade_minima=1000)
    criar_ingrediente(nome="Barato", custo_unitario=0.01, quantidade_minima=100)
    corpo = client.post(
        "/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 7, "orcamento": 10}
    ).json()
    assert Decimal(str(corpo["custoTotalEstimado"])) <= Decimal(10)


def test_reposicao_ignora_ingrediente_abastecido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente(quantidade_minima=10)
    entrada_estoque(ingrediente_id, 1000)
    corpo = client.post(
        "/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 7, "orcamento": 500}
    ).json()
    assert corpo["itens"] == []


def test_reposicao_sugere_o_que_falta(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente(custo_unitario=0.10, quantidade_minima=200)
    corpo = client.post(
        "/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 7, "orcamento": 100}
    ).json()
    assert len(corpo["itens"]) == 1
    item = corpo["itens"][0]
    assert set(item) == {
        "ingredienteId",
        "nomeIngrediente",
        "quantidadeRecomendada",
        "unidadeMedida",
        "custoEstimado",
    }
    assert item["ingredienteId"] == ingrediente_id
    assert Decimal(str(item["quantidadeRecomendada"])) == 200
    assert Decimal(str(item["custoEstimado"])) == Decimal("20.00")


@pytest.mark.parametrize(
    ("corpo", "campo"),
    [
        ({"periodoDias": 0, "orcamento": 10}, "periodoDias"),
        ({"periodoDias": 366, "orcamento": 10}, "periodoDias"),
        ({"periodoDias": 7, "orcamento": -1}, "orcamento"),
        ({"orcamento": 10}, "periodoDias"),
    ],
)
def test_reposicao_valida_entrada(
    client: TestClient, admin: dict[str, str], corpo: dict, campo: str
) -> None:
    erro = assert_api_error(
        client.post("/api/v1/recomendacoes/reposicao", headers=admin, json=corpo), 422
    )
    assert erro["detalhes"][0]["campo"] == campo


# --- indisponibilidade do solver (503) ------------------------------------------------------------


def test_producao_com_solver_indisponivel_resulta_em_503(
    client: TestClient,
    admin: dict[str, str],
    cenario_venda: dict[str, Any],
    solver_indisponivel: None,
) -> None:
    resposta = client.post("/api/v1/recomendacoes/producao", headers=admin)
    assert_api_error(resposta, 503, "SERVICE_UNAVAILABLE")


def test_reposicao_com_solver_indisponivel_resulta_em_503(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    solver_indisponivel: None,
) -> None:
    criar_ingrediente(quantidade_minima=100)
    resposta = client.post(
        "/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 7, "orcamento": 50}
    )
    assert_api_error(resposta, 503)


def test_503_nao_vaza_detalhe_do_solver(
    client: TestClient,
    admin: dict[str, str],
    cenario_venda: dict[str, Any],
    solver_indisponivel: None,
) -> None:
    resposta = client.post("/api/v1/recomendacoes/producao", headers=admin)
    assert "pulp" not in resposta.text.lower()
    assert "Traceback" not in resposta.text


# --- marketing --------------------------------------------------------------------------------


def test_sugestoes_de_marketing_devolvem_textos(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.post("/api/v1/sugestoes-marketing", headers=admin)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"geradoEm", "sugestoes", "observacao"}
    assert isinstance(corpo["sugestoes"], list)
    assert all(isinstance(s, str) and s for s in corpo["sugestoes"])


def test_marketing_nao_persiste_historico(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    primeira = client.post("/api/v1/sugestoes-marketing", headers=admin).json()
    segunda = client.post("/api/v1/sugestoes-marketing", headers=admin).json()
    assert primeira["sugestoes"] == segunda["sugestoes"]  # mesma base, sem acúmulo
    assert client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"] == 0


def test_marketing_sem_dados_ainda_responde_200(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.post("/api/v1/sugestoes-marketing", headers=admin).json()
    assert len(corpo["sugestoes"]) >= 1


# --- autorização --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        "/api/v1/recomendacoes/producao",
        "/api/v1/recomendacoes/reposicao",
        "/api/v1/sugestoes-marketing",
    ],
)
def test_recomendacoes_exigem_administrador(
    client: TestClient, funcionario: dict[str, str], caminho: str
) -> None:
    resposta = client.post(
        caminho, headers=funcionario, json={"periodoDias": 7, "orcamento": 10}
    )
    assert_api_error(resposta, 403, "FORBIDDEN")


@pytest.mark.parametrize(
    "caminho",
    [
        "/api/v1/recomendacoes/producao",
        "/api/v1/recomendacoes/reposicao",
        "/api/v1/sugestoes-marketing",
    ],
)
def test_recomendacoes_exigem_autenticacao(client: TestClient, caminho: str) -> None:
    assert_api_error(client.post(caminho, json={"periodoDias": 7, "orcamento": 10}), 401)
