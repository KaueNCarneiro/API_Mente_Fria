"""Testes de produtos e composição (Fase 6 — P6-11). Restritos a `ADMINISTRADOR`."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import assert_api_error


def _produto(ingrediente_id: int, **extra: Any) -> dict[str, Any]:
    base = {
        "nome": "Açaí 300ml",
        "precoVenda": 15.00,
        "ativo": True,
        "composicao": [{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 200}],
    }
    return {**base, **extra}


# --- cadastro e consulta ------------------------------------------------------------------


def test_cadastrar_produto_com_composicao(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post("/api/v1/produtos", headers=admin, json=_produto(ingrediente_id))
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert set(corpo) == {"id", "nome", "precoVenda", "ativo", "composicao"}
    assert resposta.headers["location"] == f"/api/v1/produtos/{corpo['id']}"


def test_composicao_traz_nome_e_unidade_do_ingrediente(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente(nome="Açaí", unidade="g")
    corpo = client.post("/api/v1/produtos", headers=admin, json=_produto(ingrediente_id)).json()
    item = corpo["composicao"][0]
    assert set(item) == {"ingredienteId", "nomeIngrediente", "unidadeMedida", "quantidadeUtilizada"}
    assert item["nomeIngrediente"] == "Açaí"
    assert item["unidadeMedida"] == "g"


def test_composicao_vazia_resulta_em_422(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/produtos", headers=admin, json=_produto(ingrediente_id, composicao=[])
    )
    erro = assert_api_error(resposta, 422, "VALIDATION_ERROR")
    assert erro["detalhes"][0]["campo"] == "composicao"


def test_composicao_com_ingrediente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post("/api/v1/produtos", headers=admin, json=_produto(9999))
    assert_api_error(resposta, 404, "NOT_FOUND")


def test_composicao_com_ingrediente_repetido_resulta_em_422(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/produtos",
        headers=admin,
        json=_produto(
            ingrediente_id,
            composicao=[
                {"ingredienteId": ingrediente_id, "quantidadeUtilizada": 100},
                {"ingredienteId": ingrediente_id, "quantidadeUtilizada": 50},
            ],
        ),
    )
    assert_api_error(resposta, 422)


def test_quantidade_utilizada_precisa_ser_positiva(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/produtos",
        headers=admin,
        json=_produto(
            ingrediente_id,
            composicao=[{"ingredienteId": ingrediente_id, "quantidadeUtilizada": 0}],
        ),
    )
    assert_api_error(resposta, 422)


def test_consultar_produto_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/produtos/9999", headers=admin), 404)


# --- atualização comercial ------------------------------------------------------------------


def test_atualizar_dados_comerciais(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    produto_id = cenario_venda["produtoId"]
    resposta = client.put(
        f"/api/v1/produtos/{produto_id}",
        headers=admin,
        json={"nome": "Açaí 500ml", "precoVenda": 22.50, "ativo": True},
    )
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Açaí 500ml"
    assert Decimal(str(resposta.json()["precoVenda"])) == Decimal("22.50")


def test_atualizacao_comercial_nao_altera_a_composicao(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    produto_id = cenario_venda["produtoId"]
    antes = client.get(f"/api/v1/produtos/{produto_id}", headers=admin).json()["composicao"]
    client.put(
        f"/api/v1/produtos/{produto_id}",
        headers=admin,
        json={"nome": "Outro nome", "precoVenda": 30.00, "ativo": True},
    )
    depois = client.get(f"/api/v1/produtos/{produto_id}", headers=admin).json()["composicao"]
    assert depois == antes


def test_preco_historico_de_pedido_nao_muda_com_atualizacao(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    """SPEC §6.4: alterar o produto não reescreve o preço já registrado em pedidos."""
    produto_id = cenario_venda["produtoId"]
    pedido = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={"itens": [{"produtoId": produto_id, "quantidade": 1}]},
    ).json()
    assert Decimal(str(pedido["itens"][0]["precoUnitarioRegistrado"])) == Decimal("15.00")

    client.put(
        f"/api/v1/produtos/{produto_id}",
        headers=admin,
        json={"nome": "Açaí 300ml", "precoVenda": 99.90, "ativo": True},
    )

    depois = client.get(f"/api/v1/pedidos/{pedido['id']}", headers=admin).json()
    assert Decimal(str(depois["itens"][0]["precoUnitarioRegistrado"])) == Decimal("15.00")
    assert Decimal(str(depois["valorTotal"])) == Decimal("15.00")


def test_atualizar_produto_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.put(
        "/api/v1/produtos/9999",
        headers=admin,
        json={"nome": "Fantasma", "precoVenda": 1.00, "ativo": True},
    )
    assert_api_error(resposta, 404)


# --- desativação lógica ----------------------------------------------------------------------


def test_desativar_produto_responde_204_sem_corpo(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.delete(f"/api/v1/produtos/{cenario_venda['produtoId']}", headers=admin)
    assert resposta.status_code == 204
    assert resposta.content == b""


def test_desativacao_e_logica(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    produto_id = cenario_venda["produtoId"]
    client.delete(f"/api/v1/produtos/{produto_id}", headers=admin)
    corpo = client.get(f"/api/v1/produtos/{produto_id}", headers=admin).json()
    assert corpo["ativo"] is False


def test_desativar_produto_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.delete("/api/v1/produtos/9999", headers=admin), 404)


# --- composição como sub-recurso ---------------------------------------------------------------


def test_consultar_composicao(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    produto_id = cenario_venda["produtoId"]
    corpo = client.get(f"/api/v1/produtos/{produto_id}/composicao", headers=admin).json()
    assert set(corpo) == {"produtoId", "itens"}
    assert corpo["produtoId"] == produto_id
    assert corpo["itens"][0]["ingredienteId"] == cenario_venda["ingredienteId"]


def test_substituicao_de_composicao_e_integral(
    client: TestClient,
    admin: dict[str, str],
    cenario_venda: dict[str, Any],
    criar_ingrediente: Callable[..., int],
) -> None:
    produto_id = cenario_venda["produtoId"]
    novo_ingrediente = criar_ingrediente(nome="Granola")
    resposta = client.put(
        f"/api/v1/produtos/{produto_id}/composicao",
        headers=admin,
        json={"itens": [{"ingredienteId": novo_ingrediente, "quantidadeUtilizada": 50}]},
    )
    assert resposta.status_code == 200
    composicao = resposta.json()["composicao"]
    assert [item["ingredienteId"] for item in composicao] == [novo_ingrediente]


def test_substituicao_valida_ingredientes(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.put(
        f"/api/v1/produtos/{cenario_venda['produtoId']}/composicao",
        headers=admin,
        json={"itens": [{"ingredienteId": 9999, "quantidadeUtilizada": 10}]},
    )
    assert_api_error(resposta, 404)


def test_substituicao_recusa_lista_vazia(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.put(
        f"/api/v1/produtos/{cenario_venda['produtoId']}/composicao",
        headers=admin,
        json={"itens": []},
    )
    assert_api_error(resposta, 422)


def test_composicao_de_produto_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/produtos/9999/composicao", headers=admin), 404)


# --- filtros e autorização -----------------------------------------------------------------------


def test_filtro_por_ativo(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    client.delete(f"/api/v1/produtos/{cenario_venda['produtoId']}", headers=admin)
    ativos = client.get("/api/v1/produtos", headers=admin, params={"ativo": True}).json()
    inativos = client.get("/api/v1/produtos", headers=admin, params={"ativo": False}).json()
    assert ativos["paginacao"]["totalElements"] == 0
    assert inativos["paginacao"]["totalElements"] == 1


def test_busca_e_ordenacao(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    primeiro = client.post(
        "/api/v1/produtos", headers=admin, json=_produto(ingrediente_id, nome="Açaí")
    )
    segundo = client.post(
        "/api/v1/produtos",
        headers=admin,
        json=_produto(ingrediente_id, nome="Vitamina", precoVenda=9.00),
    )
    assert (primeiro.status_code, segundo.status_code) == (201, 201), segundo.text
    busca = client.get("/api/v1/produtos", headers=admin, params={"q": "Vita"}).json()
    assert busca["paginacao"]["totalElements"] == 1
    ordenado = client.get(
        "/api/v1/produtos", headers=admin, params={"sort": "precoVenda,asc"}
    ).json()
    assert ordenado["data"][0]["nome"] == "Vitamina"


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/api/v1/produtos"),
        ("POST", "/api/v1/produtos"),
        ("GET", "/api/v1/produtos/1"),
        ("PUT", "/api/v1/produtos/1"),
        ("DELETE", "/api/v1/produtos/1"),
        ("GET", "/api/v1/produtos/1/composicao"),
        ("PUT", "/api/v1/produtos/1/composicao"),
    ],
)
def test_produtos_exigem_administrador(
    client: TestClient, funcionario: dict[str, str], metodo: str, caminho: str
) -> None:
    assert_api_error(
        client.request(metodo, caminho, headers=funcionario, json={}), 403, "FORBIDDEN"
    )
