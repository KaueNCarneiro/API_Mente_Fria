"""Testes de ingredientes (Fase 6 — P6-09). Restritos a `ADMINISTRADOR`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.models import hoje

from .conftest import assert_api_error

BASE = {
    "nome": "Açaí",
    "unidadeMedida": "g",
    "custoUnitario": 0.05,
    "porcaoPadrao": 100,
    "quantidadeMinima": 500,
}


def test_cadastro_inicia_com_estoque_zero(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    """SPEC §6.3: o ingrediente nasce zerado; entradas vêm por movimentação."""
    criar_unidade("g", 100)
    resposta = client.post("/api/v1/ingredientes", headers=admin, json=BASE)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["quantidadeEstoque"])) == 0
    assert corpo["precisaReposicao"] is True
    assert resposta.headers["location"] == f"/api/v1/ingredientes/{corpo['id']}"


def test_cadastro_nao_cria_movimentacao(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    pagina = client.get(
        f"/api/v1/ingredientes/{ingrediente_id}/movimentacoes", headers=admin
    ).json()
    assert pagina["paginacao"]["totalElements"] == 0


def test_resposta_tem_os_campos_do_contrato(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    corpo = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()
    assert set(corpo) == {
        "id",
        "nome",
        "unidadeMedida",
        "custoUnitario",
        "porcaoPadrao",
        "quantidadeEstoque",
        "quantidadeMinima",
        "precisaReposicao",
    }


def test_unidade_inexistente_resulta_em_404(client: TestClient, admin: dict[str, str]) -> None:
    corpo = {**BASE, "unidadeMedida": "inexistente"}
    assert_api_error(client.post("/api/v1/ingredientes", headers=admin, json=corpo), 404)


def test_quantidade_minima_e_opcional_no_cadastro(
    client: TestClient, admin: dict[str, str], criar_unidade: Callable[..., str]
) -> None:
    criar_unidade("g", 100)
    corpo = {k: v for k, v in BASE.items() if k != "quantidadeMinima"}
    resposta = client.post("/api/v1/ingredientes", headers=admin, json=corpo)
    assert resposta.status_code == 201
    assert Decimal(str(resposta.json()["quantidadeMinima"])) == 0


def test_consultar_ingrediente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/ingredientes/9999", headers=admin), 404, "NOT_FOUND")


# --- saldo derivado --------------------------------------------------------------------


def test_saldo_deriva_das_entradas(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente(quantidade_minima=500)
    entrada_estoque(ingrediente_id, 300)
    entrada_estoque(ingrediente_id, 450)
    corpo = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()
    assert Decimal(str(corpo["quantidadeEstoque"])) == 750
    assert corpo["precisaReposicao"] is False  # 750 >= 500


def test_atualizacao_nao_altera_saldo(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    """O saldo deriva dos lotes: o `PUT` não tem campo para alterá-lo."""
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100)
    resposta = client.put(
        f"/api/v1/ingredientes/{ingrediente_id}",
        headers=admin,
        json={**BASE, "nome": "Açaí premium", "quantidadeMinima": 10},
    )
    assert resposta.status_code == 200
    assert Decimal(str(resposta.json()["quantidadeEstoque"])) == 100
    assert resposta.json()["nome"] == "Açaí premium"


def test_atualizacao_recusa_campo_de_saldo(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.put(
        f"/api/v1/ingredientes/{ingrediente_id}",
        headers=admin,
        json={**BASE, "quantidadeEstoque": 5000},
    )
    assert_api_error(resposta, 422)


def test_precisa_reposicao_usa_somente_saldo_valido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    """Lote vencido conta em `quantidadeEstoque`, mas não cobre o mínimo."""
    ingrediente_id = criar_ingrediente(quantidade_minima=100)
    entrada_estoque(ingrediente_id, 500, hoje() - timedelta(days=1))
    corpo = client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()
    assert Decimal(str(corpo["quantidadeEstoque"])) == 500
    assert corpo["precisaReposicao"] is True


# --- exclusão e integridade -------------------------------------------------------------


def test_excluir_ingrediente_livre_responde_204(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.delete(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin)
    assert resposta.status_code == 204
    assert resposta.content == b""


def test_ingrediente_com_movimentacao_nao_pode_ser_excluido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 10)
    assert_api_error(
        client.delete(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin), 409, "CONFLICT"
    )


def test_ingrediente_em_composicao_nao_pode_ser_excluido(
    client: TestClient, admin: dict[str, str], cenario_venda: dict[str, Any]
) -> None:
    assert_api_error(
        client.delete(f"/api/v1/ingredientes/{cenario_venda['ingredienteId']}", headers=admin),
        409,
    )


def test_excluir_ingrediente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.delete("/api/v1/ingredientes/9999", headers=admin), 404)


# --- filtros, paginação e ordenação ------------------------------------------------------


def test_filtro_por_unidade_de_medida(
    client: TestClient,
    admin: dict[str, str],
    criar_unidade: Callable[..., str],
    criar_ingrediente: Callable[..., int],
) -> None:
    criar_unidade("ml", 50)
    criar_ingrediente(nome="Açaí", unidade="g")
    criar_ingrediente(nome="Leite", unidade="ml")
    pagina = client.get(
        "/api/v1/ingredientes", headers=admin, params={"unidadeMedida": "ml"}
    ).json()
    assert pagina["paginacao"]["totalElements"] == 1
    assert pagina["data"][0]["nome"] == "Leite"


def test_filtro_precisa_reposicao(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    com_falta = criar_ingrediente(nome="Em falta", quantidade_minima=100)
    abastecido = criar_ingrediente(nome="Abastecido", quantidade_minima=10)
    entrada_estoque(abastecido, 500)

    precisam = client.get(
        "/api/v1/ingredientes", headers=admin, params={"precisaReposicao": True}
    ).json()
    nao_precisam = client.get(
        "/api/v1/ingredientes", headers=admin, params={"precisaReposicao": False}
    ).json()
    assert [i["id"] for i in precisam["data"]] == [com_falta]
    assert [i["id"] for i in nao_precisam["data"]] == [abastecido]


def test_busca_por_nome(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    criar_ingrediente(nome="Açaí")
    criar_ingrediente(nome="Granola")
    pagina = client.get("/api/v1/ingredientes", headers=admin, params={"q": "Gran"}).json()
    assert pagina["paginacao"]["totalElements"] == 1


def test_ordenacao_por_custo(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    criar_ingrediente(nome="Barato", custo_unitario=0.01)
    criar_ingrediente(nome="Caro", custo_unitario=9.99)
    pagina = client.get(
        "/api/v1/ingredientes", headers=admin, params={"sort": "custoUnitario,desc"}
    ).json()
    assert pagina["data"][0]["nome"] == "Caro"


# --- validação e autorização --------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("nome", "A"),
        ("custoUnitario", -1),
        ("porcaoPadrao", 0),
        ("quantidadeMinima", -1),
    ],
)
def test_limites_do_contrato(
    client: TestClient,
    admin: dict[str, str],
    criar_unidade: Callable[..., str],
    campo: str,
    valor: Any,
) -> None:
    criar_unidade("g", 100)
    erro = assert_api_error(
        client.post("/api/v1/ingredientes", headers=admin, json={**BASE, campo: valor}), 422
    )
    assert erro["detalhes"][0]["campo"] == campo


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/api/v1/ingredientes"),
        ("POST", "/api/v1/ingredientes"),
        ("GET", "/api/v1/ingredientes/1"),
        ("PUT", "/api/v1/ingredientes/1"),
        ("DELETE", "/api/v1/ingredientes/1"),
    ],
)
def test_ingredientes_exigem_administrador(
    client: TestClient, funcionario: dict[str, str], metodo: str, caminho: str
) -> None:
    assert_api_error(
        client.request(metodo, caminho, headers=funcionario, json=BASE), 403, "FORBIDDEN"
    )
