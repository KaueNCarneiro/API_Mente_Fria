"""Testes do dashboard e da exportação CSV (Fase 6 — P6-15, P6-22).

Restritos a `ADMINISTRADOR`. Somente pedidos `ATIVO` entram nos indicadores.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.models import hoje

from .conftest import assert_api_error

HOJE = hoje()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)

PERIODO = {"dataInicio": ONTEM.isoformat(), "dataFim": AMANHA.isoformat()}


def _pedido(client: TestClient, headers: dict[str, str], produto_id: int, quantidade: int = 1):
    return client.post(
        "/api/v1/pedidos",
        headers=headers,
        json={"itens": [{"produtoId": produto_id, "quantidade": quantidade}]},
    )


# --- indicadores ------------------------------------------------------------------------------


def test_dashboard_devolve_o_schema_do_contrato(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    assert set(corpo) == {
        "periodoInicio",
        "periodoFim",
        "quantidadePedidos",
        "faturamentoTotal",
        "ticketMedio",
        "produtosMaisVendidos",
        "ingredientesEmReposicao",
        "linhasProximasVencimento",
    }
    assert corpo["periodoInicio"] == ONTEM.isoformat()
    assert corpo["periodoFim"] == AMANHA.isoformat()


def test_dashboard_sem_pedidos_zera_indicadores(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    assert corpo["quantidadePedidos"] == 0
    assert Decimal(str(corpo["faturamentoTotal"])) == 0
    assert Decimal(str(corpo["ticketMedio"])) == 0
    assert corpo["produtosMaisVendidos"] == []


def test_dashboard_agrega_pedidos_ativos(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _pedido(client, funcionario, cenario_venda["produtoId"], 2)  # 30,00
    _pedido(client, funcionario, cenario_venda["produtoId"], 1)  # 15,00
    corpo = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    assert corpo["quantidadePedidos"] == 2
    assert Decimal(str(corpo["faturamentoTotal"])) == Decimal("45.00")
    assert Decimal(str(corpo["ticketMedio"])) == Decimal("22.50")


def test_dashboard_ignora_pedidos_cancelados(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    """SPEC §6.5: cancelados continuam consultáveis, mas fora dos indicadores."""
    ativo = _pedido(client, funcionario, cenario_venda["produtoId"], 1).json()
    cancelado = _pedido(client, funcionario, cenario_venda["produtoId"], 2).json()
    client.post(
        f"/api/v1/pedidos/{cancelado['id']}/cancelamento", headers=admin, json={}
    )

    corpo = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    assert corpo["quantidadePedidos"] == 1
    assert Decimal(str(corpo["faturamentoTotal"])) == Decimal("15.00")
    assert corpo["produtosMaisVendidos"][0]["quantidadeVendida"] == 1
    # o pedido cancelado segue existindo
    assert client.get(f"/api/v1/pedidos/{cancelado['id']}", headers=admin).status_code == 200
    assert ativo["status"] == "ATIVO"


def test_ranking_de_produtos_mais_vendidos(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
    criar_produto,
) -> None:
    outro = criar_produto(
        nome="Açaí pequeno",
        preco_venda=8.00,
        composicao=[{"ingredienteId": cenario_venda["ingredienteId"], "quantidadeUtilizada": 50}],
    )
    _pedido(client, funcionario, cenario_venda["produtoId"], 1)
    _pedido(client, funcionario, outro, 3)

    ranking = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()[
        "produtosMaisVendidos"
    ]
    assert [p["produtoId"] for p in ranking] == [outro, cenario_venda["produtoId"]]
    assert ranking[0]["quantidadeVendida"] == 3
    assert set(ranking[0]) == {"produtoId", "nomeProduto", "quantidadeVendida"}


def test_periodo_fora_do_intervalo_nao_conta(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _pedido(client, funcionario, cenario_venda["produtoId"])
    passado = {
        "dataInicio": (HOJE - timedelta(days=30)).isoformat(),
        "dataFim": (HOJE - timedelta(days=10)).isoformat(),
    }
    corpo = client.get("/api/v1/dashboard", headers=admin, params=passado).json()
    assert corpo["quantidadePedidos"] == 0


def test_indicadores_de_estoque(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente,
    entrada_estoque,
) -> None:
    criar_ingrediente(nome="Em falta", quantidade_minima=100)
    com_validade = criar_ingrediente(nome="A vencer", quantidade_minima=0)
    entrada_estoque(com_validade, 10, HOJE + timedelta(days=2))

    corpo = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    assert corpo["ingredientesEmReposicao"] == 1
    assert corpo["linhasProximasVencimento"] == 1


def test_periodo_invertido_resulta_em_400(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get(
        "/api/v1/dashboard",
        headers=admin,
        params={"dataInicio": AMANHA.isoformat(), "dataFim": ONTEM.isoformat()},
    )
    assert_api_error(resposta, 400, "BAD_REQUEST")


@pytest.mark.parametrize("faltando", ["dataInicio", "dataFim"])
def test_periodo_e_obrigatorio(
    client: TestClient, admin: dict[str, str], faltando: str
) -> None:
    params = {k: v for k, v in PERIODO.items() if k != faltando}
    erro = assert_api_error(
        client.get("/api/v1/dashboard", headers=admin, params=params), 400
    )
    assert erro["detalhes"][0]["campo"] == faltando


def test_data_malformada_resulta_em_400(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get(
        "/api/v1/dashboard",
        headers=admin,
        params={"dataInicio": "32/13/2026", "dataFim": AMANHA.isoformat()},
    )
    assert_api_error(resposta, 400)


# --- exportação CSV (P6-22) ---------------------------------------------------------------------


def test_exportacao_responde_csv_utf8(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _pedido(client, funcionario, cenario_venda["produtoId"])
    resposta = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "utf-8" in resposta.headers["content-type"].lower()


def test_exportacao_traz_content_disposition(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO)
    disposicao = resposta.headers.get("content-disposition", "")
    assert "attachment" in disposicao
    assert ".csv" in disposicao


def test_corpo_e_csv_e_nao_json(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO)
    assert not resposta.text.lstrip().startswith("{")
    linhas = list(csv.reader(io.StringIO(resposta.text)))
    assert linhas[0] == ["secao", "chave", "valor"]


def test_csv_decodifica_em_utf8_sem_bom(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO)
    assert not resposta.content.startswith(b"\xef\xbb\xbf")
    assert resposta.content.decode("utf-8") == resposta.text


def test_csv_aplica_as_mesmas_regras_do_dashboard(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _pedido(client, funcionario, cenario_venda["produtoId"], 1)
    cancelado = _pedido(client, funcionario, cenario_venda["produtoId"], 2).json()
    client.post(f"/api/v1/pedidos/{cancelado['id']}/cancelamento", headers=admin, json={})

    painel = client.get("/api/v1/dashboard", headers=admin, params=PERIODO).json()
    texto = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO).text
    valores = {linha[1]: linha[2] for linha in csv.reader(io.StringIO(texto)) if len(linha) == 3}

    assert valores["quantidadePedidos"] == str(painel["quantidadePedidos"])
    assert Decimal(valores["faturamentoTotal"]) == Decimal(str(painel["faturamentoTotal"]))


def test_csv_preserva_acentuacao(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _pedido(client, funcionario, cenario_venda["produtoId"])
    texto = client.get("/api/v1/dashboard/exportacao", headers=admin, params=PERIODO).text
    assert "Açaí" in texto


def test_exportacao_valida_periodo(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get(
        "/api/v1/dashboard/exportacao",
        headers=admin,
        params={"dataInicio": AMANHA.isoformat(), "dataFim": ONTEM.isoformat()},
    )
    assert_api_error(resposta, 400)


# --- autorização ---------------------------------------------------------------------------------


@pytest.mark.parametrize("caminho", ["/api/v1/dashboard", "/api/v1/dashboard/exportacao"])
def test_dashboard_exige_administrador(
    client: TestClient, funcionario: dict[str, str], caminho: str
) -> None:
    assert_api_error(
        client.get(caminho, headers=funcionario, params=PERIODO), 403, "FORBIDDEN"
    )


@pytest.mark.parametrize("caminho", ["/api/v1/dashboard", "/api/v1/dashboard/exportacao"])
def test_dashboard_exige_autenticacao(client: TestClient, caminho: str) -> None:
    assert_api_error(client.get(caminho, params=PERIODO), 401)
