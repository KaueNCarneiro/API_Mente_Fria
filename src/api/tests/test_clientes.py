"""Testes do domínio de clientes (Fase 6 — P6-07).

No contrato, todas as operações de `/clientes` são liberadas a **ADMINISTRADOR e
FUNCIONARIO** ("Atores autorizados"), e o cliente referenciado por pedido não pode ser
excluído.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import assert_api_error

CLIENTE = {"nome": "Ana Souza", "contato": "11999990000", "endereco": "Rua das Flores, 10"}


def _criar(client: TestClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    corpo = {**CLIENTE, **extra}
    resposta = client.post("/api/v1/clientes", headers=headers, json=corpo)
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())


# --- CRUD ------------------------------------------------------------------------------


def test_cadastrar_cliente_responde_201_com_location(
    client: TestClient, funcionario: dict[str, str]
) -> None:
    resposta = client.post("/api/v1/clientes", headers=funcionario, json=CLIENTE)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert set(corpo) == {"id", "nome", "contato", "endereco"}
    assert resposta.headers["location"] == f"/api/v1/clientes/{corpo['id']}"


def test_consultar_cliente(client: TestClient, admin: dict[str, str]) -> None:
    criado = _criar(client, admin)
    corpo = client.get(f"/api/v1/clientes/{criado['id']}", headers=admin).json()
    assert corpo == criado


def test_consultar_cliente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/clientes/9999", headers=admin), 404, "NOT_FOUND")


def test_atualizar_cliente_substitui_todos_os_campos(
    client: TestClient, admin: dict[str, str]
) -> None:
    criado = _criar(client, admin)
    resposta = client.put(
        f"/api/v1/clientes/{criado['id']}",
        headers=admin,
        json={"nome": "Ana Maria", "contato": "11888887777", "endereco": "Av. Nova, 500"},
    )
    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": criado["id"],
        "nome": "Ana Maria",
        "contato": "11888887777",
        "endereco": "Av. Nova, 500",
    }


def test_atualizar_cliente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(
        client.put("/api/v1/clientes/9999", headers=admin, json=CLIENTE), 404
    )


def test_excluir_cliente_sem_pedido_responde_204_sem_corpo(
    client: TestClient, admin: dict[str, str]
) -> None:
    criado = _criar(client, admin)
    resposta = client.delete(f"/api/v1/clientes/{criado['id']}", headers=admin)
    assert resposta.status_code == 204
    assert resposta.content == b""
    assert client.get(f"/api/v1/clientes/{criado['id']}", headers=admin).status_code == 404


def test_excluir_cliente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.delete("/api/v1/clientes/9999", headers=admin), 404)


# --- validação -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("nome", "A"), ("contato", "ab"), ("endereco", "xy")],
)
def test_cadastro_valida_limites_minimos(
    client: TestClient, admin: dict[str, str], campo: str, valor: str
) -> None:
    corpo = {**CLIENTE, campo: valor}
    erro = assert_api_error(client.post("/api/v1/clientes", headers=admin, json=corpo), 422)
    assert erro["detalhes"][0]["campo"] == campo


def test_cadastro_recusa_campo_fora_do_contrato(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = {**CLIENTE, "cpf": "000.000.000-00"}
    assert_api_error(client.post("/api/v1/clientes", headers=admin, json=corpo), 422)


# --- associação a pedido ---------------------------------------------------------------


def test_cliente_e_opcional_no_pedido(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={"itens": [{"produtoId": cenario_venda["produtoId"], "quantidade": 1}]},
    )
    assert resposta.status_code == 201
    assert resposta.json()["clienteId"] is None


def test_cliente_referenciado_por_pedido_nao_pode_ser_excluido(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    cenario_venda: dict[str, Any],
) -> None:
    criado = _criar(client, admin)
    pedido = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={
            "clienteId": criado["id"],
            "itens": [{"produtoId": cenario_venda["produtoId"], "quantidade": 1}],
        },
    )
    assert pedido.status_code == 201

    assert_api_error(client.delete(f"/api/v1/clientes/{criado['id']}", headers=admin), 409, "CONFLICT")
    # histórico preservado
    assert client.get(f"/api/v1/clientes/{criado['id']}", headers=admin).status_code == 200


def test_pedido_com_cliente_inexistente_resulta_em_404(
    client: TestClient, funcionario: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    resposta = client.post(
        "/api/v1/pedidos",
        headers=funcionario,
        json={
            "clienteId": 9999,
            "itens": [{"produtoId": cenario_venda["produtoId"], "quantidade": 1}],
        },
    )
    assert_api_error(resposta, 404)


# --- busca, paginação e autorização ----------------------------------------------------


def test_busca_cobre_nome_contato_e_endereco(
    client: TestClient, admin: dict[str, str]
) -> None:
    _criar(client, admin)
    _criar(client, admin, nome="Bruno Lima", contato="21777776666", endereco="Rua do Porto, 3")
    for termo, esperado in (("Ana", 1), ("21777776666", 1), ("Porto", 1), ("Rua", 2)):
        pagina = client.get("/api/v1/clientes", headers=admin, params={"q": termo}).json()
        assert pagina["paginacao"]["totalElements"] == esperado, (termo, pagina)


def test_busca_trata_curinga_como_texto_literal(
    client: TestClient, admin: dict[str, str]
) -> None:
    _criar(client, admin)
    pagina = client.get("/api/v1/clientes", headers=admin, params={"q": "%"}).json()
    assert pagina["paginacao"]["totalElements"] == 0


def test_ordenacao_desc(client: TestClient, admin: dict[str, str]) -> None:
    _criar(client, admin, nome="Ana Souza")
    _criar(client, admin, nome="Zeca Silva")
    pagina = client.get("/api/v1/clientes", headers=admin, params={"sort": "nome,desc"}).json()
    assert pagina["data"][0]["nome"] == "Zeca Silva"


@pytest.mark.parametrize("papel", ["admin", "funcionario"])
def test_clientes_aceita_ambos_os_perfis(
    client: TestClient, request: pytest.FixtureRequest, papel: str
) -> None:
    headers = request.getfixturevalue(papel)
    assert client.get("/api/v1/clientes", headers=headers).status_code == 200
    assert client.post("/api/v1/clientes", headers=headers, json=CLIENTE).status_code == 201


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", "/api/v1/clientes"),
        ("post", "/api/v1/clientes"),
        ("get", "/api/v1/clientes/1"),
        ("put", "/api/v1/clientes/1"),
        ("delete", "/api/v1/clientes/1"),
    ],
)
def test_clientes_exige_autenticacao(client: TestClient, metodo: str, caminho: str) -> None:
    assert_api_error(client.request(metodo.upper(), caminho, json=CLIENTE), 401, "UNAUTHORIZED")
