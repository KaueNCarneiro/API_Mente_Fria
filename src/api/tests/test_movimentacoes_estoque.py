"""Testes de estoque: lotes, FEFO, validade e auditoria (Fase 6 — P6-10).

As três operações exigem Bearer, mas o contrato **não** restringe perfil nelas.
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


def _saida(
    client: TestClient,
    headers: dict[str, str],
    ingrediente_id: int,
    quantidade: float,
    motivo: str | None = None,
) -> Any:
    corpo: dict[str, Any] = {
        "ingredienteId": ingrediente_id,
        "tipo": "SAIDA",
        "quantidade": quantidade,
    }
    if motivo is not None:
        corpo["motivo"] = motivo
    return client.post("/api/v1/movimentacoes-estoque", headers=headers, json=corpo)


def _movimentacoes(client: TestClient, headers: dict[str, str], ingrediente_id: int) -> dict:
    pagina = client.get(
        "/api/v1/movimentacoes-estoque",
        headers=headers,
        params={"ingredienteId": ingrediente_id, "size": 100},
    ).json()
    return {m["id"]: m for m in pagina["data"]}


# --- entrada ----------------------------------------------------------------------------


def test_entrada_cria_lote_com_quantidade_restante(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        json={"ingredienteId": ingrediente_id, "tipo": "ENTRADA", "quantidade": 500},
    )
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tipo"] == "ENTRADA"
    assert Decimal(str(corpo["quantidadeRestante"])) == 500
    assert resposta.headers["location"] == f"/api/v1/movimentacoes-estoque/{corpo['id']}"


def test_entrada_aceita_data_de_validade(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    validade = hoje() + timedelta(days=10)
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        json={
            "ingredienteId": ingrediente_id,
            "tipo": "ENTRADA",
            "quantidade": 100,
            "dataValidade": validade.isoformat(),
        },
    )
    assert resposta.json()["dataValidade"] == validade.isoformat()


def test_usuario_id_vem_do_token_e_nao_do_corpo(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    usuario_admin_id: int,
) -> None:
    """Auditoria: o responsável é quem está autenticado."""
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=funcionario,
        json={"ingredienteId": ingrediente_id, "tipo": "ENTRADA", "quantidade": 10},
    )
    assert resposta.status_code == 201
    assert resposta.json()["usuarioId"] != usuario_admin_id


def test_corpo_nao_pode_informar_usuario_id(
    client: TestClient, admin: dict[str, str], criar_ingrediente: Callable[..., int]
) -> None:
    ingrediente_id = criar_ingrediente()
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        json={
            "ingredienteId": ingrediente_id,
            "tipo": "ENTRADA",
            "quantidade": 10,
            "usuarioId": 9999,
        },
    )
    assert_api_error(resposta, 422)


def test_ingrediente_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        json={"ingredienteId": 9999, "tipo": "ENTRADA", "quantidade": 10},
    )
    assert_api_error(resposta, 404, "NOT_FOUND")


# --- saída e FEFO ------------------------------------------------------------------------


def test_saida_nao_cria_lote(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100)
    corpo = _saida(client, admin, ingrediente_id, 10).json()
    assert corpo["tipo"] == "SAIDA"
    assert corpo["quantidadeRestante"] is None
    assert corpo["dataValidade"] is None


def test_saida_consome_lotes_em_ordem_fefo(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    longe = entrada_estoque(ingrediente_id, 1000, hoje() + timedelta(days=30))
    perto = entrada_estoque(ingrediente_id, 300, hoje() + timedelta(days=2))

    assert _saida(client, admin, ingrediente_id, 400).status_code == 201

    lotes = _movimentacoes(client, admin, ingrediente_id)
    assert Decimal(str(lotes[perto]["quantidadeRestante"])) == 0, "o que vence antes sai antes"
    assert Decimal(str(lotes[longe]["quantidadeRestante"])) == 900


def test_lote_sem_validade_e_consumido_por_ultimo(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    sem_validade = entrada_estoque(ingrediente_id, 100)
    com_validade = entrada_estoque(ingrediente_id, 100, hoje() + timedelta(days=5))

    _saida(client, admin, ingrediente_id, 100)

    lotes = _movimentacoes(client, admin, ingrediente_id)
    assert Decimal(str(lotes[com_validade]["quantidadeRestante"])) == 0
    assert Decimal(str(lotes[sem_validade]["quantidadeRestante"])) == 100


def test_lote_que_vence_hoje_ainda_e_valido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 50, hoje())
    assert _saida(client, admin, ingrediente_id, 50).status_code == 201


def test_saida_nunca_consome_lote_vencido(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    vencido = entrada_estoque(ingrediente_id, 500, hoje() - timedelta(days=1))

    resposta = _saida(client, admin, ingrediente_id, 10)
    assert_api_error(resposta, 409, "CONFLICT")

    lotes = _movimentacoes(client, admin, ingrediente_id)
    assert Decimal(str(lotes[vencido]["quantidadeRestante"])) == 500


def test_saida_acima_do_saldo_valido_resulta_em_409(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100)
    assert_api_error(_saida(client, admin, ingrediente_id, 101), 409)


def test_saida_consome_parcialmente_um_lote(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    lote = entrada_estoque(ingrediente_id, 100)
    _saida(client, admin, ingrediente_id, 30)
    lotes = _movimentacoes(client, admin, ingrediente_id)
    assert Decimal(str(lotes[lote]["quantidadeRestante"])) == 70


# --- descarte de vencidos -----------------------------------------------------------------


def test_descarte_abate_somente_lotes_vencidos(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    """Decisão aprovada em 2026-11-18: é a única saída que alcança lote vencido."""
    ingrediente_id = criar_ingrediente()
    valido = entrada_estoque(ingrediente_id, 400, hoje() + timedelta(days=10))
    vencido = entrada_estoque(ingrediente_id, 200, hoje() - timedelta(days=3))

    resposta = _saida(client, admin, ingrediente_id, 200, motivo="DESCARTE_VENCIDO")
    assert resposta.status_code == 201
    assert resposta.json()["motivo"] == "DESCARTE_VENCIDO"

    lotes = _movimentacoes(client, admin, ingrediente_id)
    assert Decimal(str(lotes[vencido]["quantidadeRestante"])) == 0
    assert Decimal(str(lotes[valido]["quantidadeRestante"])) == 400, "lote válido intocado"


def test_descarte_sem_saldo_vencido_resulta_em_409(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 500, hoje() + timedelta(days=10))
    assert_api_error(_saida(client, admin, ingrediente_id, 1, motivo="DESCARTE_VENCIDO"), 409)


def test_descarte_reduz_o_saldo_total(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 200, hoje() - timedelta(days=1))
    antes = Decimal(
        str(client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()["quantidadeEstoque"])
    )
    _saida(client, admin, ingrediente_id, 200, motivo="DESCARTE_VENCIDO")
    depois = Decimal(
        str(client.get(f"/api/v1/ingredientes/{ingrediente_id}", headers=admin).json()["quantidadeEstoque"])
    )
    assert antes - depois == 200


# --- consultas, filtros e autorização ------------------------------------------------------


def test_sub_recurso_de_ingrediente_filtra_por_tipo(
    client: TestClient,
    funcionario: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
    admin: dict[str, str],
) -> None:
    ingrediente_id = criar_ingrediente()
    entrada_estoque(ingrediente_id, 100)
    entrada_estoque(ingrediente_id, 50)
    _saida(client, admin, ingrediente_id, 10)

    entradas = client.get(
        f"/api/v1/ingredientes/{ingrediente_id}/movimentacoes",
        headers=funcionario,
        params={"tipo": "ENTRADA"},
    ).json()
    saidas = client.get(
        f"/api/v1/ingredientes/{ingrediente_id}/movimentacoes",
        headers=funcionario,
        params={"tipo": "SAIDA"},
    ).json()
    assert entradas["paginacao"]["totalElements"] == 2
    assert saidas["paginacao"]["totalElements"] == 1


def test_sub_recurso_de_ingrediente_inexistente_resulta_em_404(
    client: TestClient, funcionario: dict[str, str]
) -> None:
    assert_api_error(
        client.get("/api/v1/ingredientes/9999/movimentacoes", headers=funcionario), 404
    )


def test_livro_filtra_por_ingrediente_e_periodo(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    entrada_estoque: Callable[..., int],
) -> None:
    primeiro = criar_ingrediente(nome="Açaí")
    segundo = criar_ingrediente(nome="Granola")
    entrada_estoque(primeiro, 10)
    entrada_estoque(segundo, 20)

    por_ingrediente = client.get(
        "/api/v1/movimentacoes-estoque", headers=admin, params={"ingredienteId": segundo}
    ).json()
    assert por_ingrediente["paginacao"]["totalElements"] == 1

    hoje_iso = hoje().isoformat()
    no_periodo = client.get(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        params={"dataInicio": hoje_iso, "dataFim": hoje_iso},
    ).json()
    assert no_periodo["paginacao"]["totalElements"] == 2

    fora = client.get(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        params={"dataInicio": (hoje() + timedelta(days=1)).isoformat()},
    ).json()
    assert fora["paginacao"]["totalElements"] == 0


def test_periodo_invertido_resulta_em_400(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get(
        "/api/v1/movimentacoes-estoque",
        headers=admin,
        params={
            "dataInicio": hoje().isoformat(),
            "dataFim": (hoje() - timedelta(days=1)).isoformat(),
        },
    )
    assert_api_error(resposta, 400, "BAD_REQUEST")


@pytest.mark.parametrize("papel", ["admin", "funcionario"])
def test_estoque_aceita_ambos_os_perfis(
    client: TestClient,
    request: pytest.FixtureRequest,
    papel: str,
    criar_ingrediente: Callable[..., int],
) -> None:
    """A descrição do contrato não restringe perfil nestas operações."""
    headers = request.getfixturevalue(papel)
    ingrediente_id = criar_ingrediente(nome=f"Ingrediente {papel}")
    assert client.get("/api/v1/movimentacoes-estoque", headers=headers).status_code == 200
    resposta = client.post(
        "/api/v1/movimentacoes-estoque",
        headers=headers,
        json={"ingredienteId": ingrediente_id, "tipo": "ENTRADA", "quantidade": 1},
    )
    assert resposta.status_code == 201


def test_estoque_exige_autenticacao(client: TestClient) -> None:
    assert_api_error(client.get("/api/v1/movimentacoes-estoque"), 401)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("tipo", "TRANSFERENCIA"), ("quantidade", 0), ("motivo", "PERDA")],
)
def test_enums_e_limites_do_contrato(
    client: TestClient,
    admin: dict[str, str],
    criar_ingrediente: Callable[..., int],
    campo: str,
    valor: Any,
) -> None:
    ingrediente_id = criar_ingrediente()
    corpo = {"ingredienteId": ingrediente_id, "tipo": "ENTRADA", "quantidade": 10, campo: valor}
    assert_api_error(
        client.post("/api/v1/movimentacoes-estoque", headers=admin, json=corpo), 422
    )
