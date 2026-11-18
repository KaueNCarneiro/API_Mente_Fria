"""Testes de pedidos: cálculo, transação, baixas e cancelamento (Fase 6 — P6-12, P6-21).

As quatro operações exigem Bearer, sem restrição de perfil no contrato.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.models import hoje

from .conftest import assert_api_error


def _saldo(client: TestClient, headers: dict[str, str], ingrediente_id: int) -> Decimal:
    corpo = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=headers).json()
    return Decimal(str(corpo["quantidadeEstoque"]))


def _registrar(
    client: TestClient, headers: dict[str, str], produto_id: int, quantidade: int = 1, **extra: Any
) -> Any:
    corpo = {"itens": [{"produtoId": produto_id, "quantidade": quantidade}], **extra}
    return client.post("/api/v1/pedidos", headers=headers, json=corpo)


# --- registro e cálculo --------------------------------------------------------------------


def test_registrar_pedido_responde_201_com_location(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = _registrar(client, funcionario, cenario_venda["produtoId"], 2)
    assert resposta.status_code == 201
    assert resposta.headers["location"] == f"/api/v1/pedidos/{resposta.json()['id']}"


def test_pedido_captura_preco_vigente_e_calcula_em_decimal(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    corpo = _registrar(client, funcionario, cenario_venda["produtoId"], 3).json()
    item = corpo["itens"][0]
    assert Decimal(str(item["precoUnitarioRegistrado"])) == Decimal("15.00")
    assert Decimal(str(item["subtotal"])) == Decimal("45.00")
    assert Decimal(str(corpo["valorTotal"])) == Decimal("45.00")
    assert item["nomeProduto"] == "Açaí 300ml"


def test_pedido_nasce_ativo_sem_dados_de_cancelamento(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    corpo = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    assert corpo["status"] == "ATIVO"
    assert corpo["dataCancelamento"] is None
    assert corpo["usuarioCancelamentoId"] is None


def test_usuario_do_pedido_vem_do_token(
    client: TestClient,
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
    usuario_admin_id: int,
) -> None:
    corpo = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    assert corpo["usuarioId"] != usuario_admin_id


def test_pedido_recusa_usuario_id_no_corpo(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={
            "usuarioId": 1,
            "itens": [{"produtoId": cenario_venda["produtoId"], "quantidade": 1}],
        },
    )
    assert_api_error(resposta, 422)


def test_pedido_com_varios_itens_soma_o_total(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
    criar_produto: Callable[..., int],
) -> None:
    segundo = criar_produto(
        nome="Açaí 500ml",
        preco_venda=22.50,
        composicao=[{"ingredienteId": cenario_venda["ingredienteId"], "quantidadeUtilizada": 100}],
    )
    resposta = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={
            "itens": [
                {"produtoId": cenario_venda["produtoId"], "quantidade": 2},
                {"produtoId": segundo, "quantidade": 1},
            ]
        },
    )
    assert resposta.status_code == 201
    assert Decimal(str(resposta.json()["valorTotal"])) == Decimal("52.50")


def test_produto_inexistente_resulta_em_404(
    client: TestClient, funcionario: dict[str, str]
) -> None:
    assert_api_error(_registrar(client, funcionario, 9999), 404, "NOT_FOUND")


def test_produto_desativado_resulta_em_409(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    """Decisão da Fase 5: produto desativado não é vendável."""
    client.delete(f"/api/v1/produtos/{cenario_venda['produtoId']}", headers=admin)
    assert_api_error(_registrar(client, funcionario, cenario_venda["produtoId"]), 409)


@pytest.mark.parametrize("quantidade", [0, 10_001])
def test_quantidade_fora_dos_limites_do_contrato(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any], quantidade: int
) -> None:
    assert_api_error(
        _registrar(client, funcionario, cenario_venda["produtoId"], quantidade), 422
    )


def test_pedido_sem_itens_resulta_em_422(
    client: TestClient, funcionario: dict[str, str]
) -> None:
    resposta = client.post("/api/v1/pedidos", headers=funcionario, json={"itens": []})
    assert_api_error(resposta, 422)


# --- baixa de estoque ----------------------------------------------------------------------


def test_pedido_baixa_estoque_na_proporcao_da_composicao(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    antes = _saldo(client, admin, cenario_venda["ingredienteId"])
    _registrar(client, funcionario, cenario_venda["produtoId"], 2)
    depois = _saldo(client, admin, cenario_venda["ingredienteId"])
    assert antes - depois == cenario_venda["consumoPorUnidade"] * 2


def test_baixa_automatica_usa_motivo_pedido(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    _registrar(client, funcionario, cenario_venda["produtoId"])
    movimentacoes = client.get(
        "/api/v1/movimentacoes-estoque", headers=admin, params={"tipo": "SAIDA", "size": 100}
    ).json()["data"]
    assert len(movimentacoes) == 1
    assert movimentacoes[0]["motivo"] == "PEDIDO"


def test_baixa_respeita_fefo(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    criar_produto: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    longe = entrada_estoque(ingrediente_id, 500, hoje() + timedelta(days=60))
    perto = entrada_estoque(ingrediente_id, 100, hoje() + timedelta(days=1))
    produto_id = criar_produto(
        composicao=[{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 150}]
    )

    _registrar(client, funcionario, produto_id)

    lotes = {
        m["id"]: m
        for m in client.get(
            "/api/v1/movimentacoes-estoque",
            headers=admin,
            params={"ingredienteId": ingrediente_id, "size": 100},
        ).json()["data"]
    }
    assert Decimal(str(lotes[perto]["quantidadeRestante"])) == 0
    assert Decimal(str(lotes[longe]["quantidadeRestante"])) == 450


def test_estoque_insuficiente_resulta_em_409(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    assert_api_error(_registrar(client, funcionario, cenario_venda["produtoId"], 100), 409)


def test_pedido_nao_consome_lote_vencido(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    criar_produto: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 1000, hoje() - timedelta(days=1))
    produto_id = criar_produto(
        composicao=[{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 10}]
    )
    assert_api_error(_registrar(client, funcionario, produto_id), 409)


# --- transação atômica (P6-21) -----------------------------------------------------------------


def test_falha_por_estoque_nao_deixa_pedido_nem_baixa(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    pedidos_antes = client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"]
    saldo_antes = _saldo(client, admin, cenario_venda["ingredienteId"])
    movimentacoes_antes = client.get(
        "/api/v1/movimentacoes-estoque", headers=admin
    ).json()["paginacao"]["totalElements"]

    assert_api_error(_registrar(client, funcionario, cenario_venda["produtoId"], 100), 409)

    assert (
        client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"]
        == pedidos_antes
    )
    assert _saldo(client, admin, cenario_venda["ingredienteId"]) == saldo_antes
    assert (
        client.get("/api/v1/movimentacoes-estoque", headers=admin).json()["paginacao"][
            "totalElements"
        ]
        == movimentacoes_antes
    )


def test_falha_no_segundo_item_desfaz_a_baixa_do_primeiro(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    criar_produto: Callable[..., int],
) -> None:
    """Rollback integral: o item que caberia no estoque também não é baixado."""
    farto = criar_ingrediente(nome="Farto")
    escasso = criar_ingrediente(nome="Escasso")
    entrada_estoque(farto, 1000)
    entrada_estoque(escasso, 5)
    produto_ok = criar_produto(
        nome="Produto OK", composicao=[{"ingredienteId": farto, "quantidadeUtilizada": 100}]
    )
    produto_falho = criar_produto(
        nome="Produto falho", composicao=[{"ingredienteId": escasso, "quantidadeUtilizada": 100}]
    )

    saldo_farto = _saldo(client, admin, farto)
    resposta = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={
            "itens": [
                {"produtoId": produto_ok, "quantidade": 1},
                {"produtoId": produto_falho, "quantidade": 1},
            ]
        },
    )
    assert_api_error(resposta, 409)
    assert _saldo(client, admin, farto) == saldo_farto
    assert client.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"] == 0


# --- cancelamento -----------------------------------------------------------------------------


def test_cancelamento_registra_status_data_e_usuario(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
    usuario_admin_id: int,
) -> None:
    pedido = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    resposta = client.post(
        f"/api/v1/pedidos/{pedido['id']}/cancelamento",
        headers=admin,
        json={"observacao": "Cliente desistiu."},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "CANCELADO"
    assert corpo["dataCancelamento"] is not None
    assert corpo["usuarioCancelamentoId"] == usuario_admin_id


def test_cancelamento_nao_devolve_estoque(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    pedido = _registrar(client, funcionario, cenario_venda["produtoId"], 2).json()
    saldo_apos_pedido = _saldo(client, admin, cenario_venda["ingredienteId"])
    client.post(f"/api/v1/pedidos/{pedido['id']}/cancelamento", headers=admin, json={})
    assert _saldo(client, admin, cenario_venda["ingredienteId"]) == saldo_apos_pedido


def test_cancelamento_sem_corpo_e_aceito(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    """O contrato declara o corpo como não obrigatório."""
    pedido = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    resposta = client.post(f"/api/v1/pedidos/{pedido['id']}/cancelamento", headers=funcionario)
    assert resposta.status_code == 200


def test_cancelar_duas_vezes_resulta_em_409(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    pedido = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    client.post(f"/api/v1/pedidos/{pedido['id']}/cancelamento", headers=funcionario, json={})
    resposta = client.post(
        f"/api/v1/pedidos/{pedido['id']}/cancelamento", headers=funcionario, json={}
    )
    assert_api_error(resposta, 409, "CONFLICT")


def test_cancelar_pedido_inexistente_resulta_em_404(
    client: TestClient, funcionario: dict[str, str]
) -> None:
    assert_api_error(
        client.post("/api/v1/pedidos/9999/cancelamento", headers=funcionario, json={}), 404
    )


def test_pedido_cancelado_continua_consultavel(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    pedido = _registrar(client, funcionario, cenario_venda["produtoId"]).json()
    client.post(f"/api/v1/pedidos/{pedido['id']}/cancelamento", headers=funcionario, json={})
    resposta = client.get(f"/api/v1/pedidos/{pedido['id']}", headers=funcionario)
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "CANCELADO"


# --- filtros e autorização -----------------------------------------------------------------------


def test_filtros_de_status_cliente_e_periodo(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    cliente_id = client.post(
        "/api/v1/clientes",
        headers=admin,
        json={"nome": "Ana Souza", "contato": "11999990000", "endereco": "Rua A, 1"},
    ).json()["id"]
    com_cliente = _registrar(
        client, funcionario, cenario_venda["produtoId"], clienteId=cliente_id
    ).json()
    _registrar(client, funcionario, cenario_venda["produtoId"])
    client.post(
        f"/api/v1/pedidos/{com_cliente['id']}/cancelamento", headers=funcionario, json={}
    )

    ativos = client.get("/api/v1/pedidos", headers=admin, params={"status": "ATIVO"}).json()
    cancelados = client.get(
        "/api/v1/pedidos", headers=admin, params={"status": "CANCELADO"}
    ).json()
    do_cliente = client.get(
        "/api/v1/pedidos", headers=admin, params={"clienteId": cliente_id}
    ).json()
    hoje_iso = hoje().isoformat()
    no_periodo = client.get(
        "/api/v1/pedidos", headers=admin, params={"dataInicio": hoje_iso, "dataFim": hoje_iso}
    ).json()

    assert ativos["paginacao"]["totalElements"] == 1
    assert cancelados["paginacao"]["totalElements"] == 1
    assert do_cliente["paginacao"]["totalElements"] == 1
    assert no_periodo["paginacao"]["totalElements"] == 2


@pytest.mark.parametrize("papel", ["admin", "funcionario"])
def test_pedidos_aceitam_ambos_os_perfis(
    client: TestClient,
    request: pytest.FixtureRequest,
    papel: str,
    cenario_venda: dict[str, Any],
) -> None:
    headers = request.getfixturevalue(papel)
    assert client.get("/api/v1/pedidos", headers=headers).status_code == 200
    assert _registrar(client, headers, cenario_venda["produtoId"]).status_code == 201


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/api/v1/pedidos"),
        ("POST", "/api/v1/pedidos"),
        ("GET", "/api/v1/pedidos/1"),
        ("POST", "/api/v1/pedidos/1/cancelamento"),
    ],
)
def test_pedidos_exigem_autenticacao(client: TestClient, metodo: str, caminho: str) -> None:
    assert_api_error(client.request(metodo, caminho, json={"itens": []}), 401)
