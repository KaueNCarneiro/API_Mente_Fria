"""Testes do envelope `ApiError` (Fase 6 — P6-16).

O formato é o do contrato (`codigo`, `mensagem`, `detalhes`, `timestamp`, `caminho`,
`correlationId`) — nunca `{"detail": ...}` do FastAPI nem RFC 9457.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import SENHA_PADRAO, assert_api_error, campos_do_api_error


def _cenarios_de_erro(
    client: TestClient, admin: dict[str, str], funcionario: dict[str, str]
) -> dict[int, Any]:
    """Uma resposta real da API para cada status de erro contratual."""
    return {
        400: client.get("/api/v1/usuarios", headers=admin, params={"size": 500}),
        401: client.get("/api/v1/usuarios"),
        403: client.get("/api/v1/usuarios", headers=funcionario),
        404: client.get("/api/v1/usuarios/9999", headers=admin),
        409: client.post(
            "/api/v1/auth/administrador",
            json={"nome": "Outro", "email": "outro@mentefria.com", "senha": SENHA_PADRAO},
        ),
        422: client.post(
            "/api/v1/usuarios",
            headers=admin,
            json={"nome": "X", "email": "nao-e-email", "senha": "curta"},
        ),
    }


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_envelope_em_cada_status(
    client: TestClient, admin: dict[str, str], funcionario: dict[str, str], status: int
) -> None:
    resposta = _cenarios_de_erro(client, admin, funcionario)[status]
    assert_api_error(resposta, status)


@pytest.mark.parametrize(
    ("status", "codigo"),
    [
        (400, "BAD_REQUEST"),
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (409, "CONFLICT"),
        (422, "VALIDATION_ERROR"),
    ],
)
def test_codigo_estavel_por_status(
    client: TestClient,
    admin: dict[str, str],
    funcionario: dict[str, str],
    status: int,
    codigo: str,
) -> None:
    resposta = _cenarios_de_erro(client, admin, funcionario)[status]
    assert resposta.json()["codigo"] == codigo


def test_nao_usa_o_formato_do_fastapi_nem_rfc_9457(
    client: TestClient, admin: dict[str, str], funcionario: dict[str, str]
) -> None:
    for resposta in _cenarios_de_erro(client, admin, funcionario).values():
        corpo = resposta.json()
        assert "detail" not in corpo
        assert not {"type", "title", "status", "instance", "invalidParams"} & set(corpo)


def test_timestamp_e_iso_com_fuso(client: TestClient, admin: dict[str, str]) -> None:
    corpo = client.get("/api/v1/usuarios/9999", headers=admin).json()
    momento = datetime.fromisoformat(corpo["timestamp"])
    assert momento.tzinfo is not None


def test_caminho_reflete_a_requisicao(client: TestClient, admin: dict[str, str]) -> None:
    corpo = client.get("/api/v1/usuarios/9999", headers=admin).json()
    assert corpo["caminho"] == "/api/v1/usuarios/9999"


def test_correlation_id_e_unico_por_resposta(
    client: TestClient, admin: dict[str, str]
) -> None:
    primeiro = client.get("/api/v1/usuarios/9999", headers=admin).json()["correlationId"]
    segundo = client.get("/api/v1/usuarios/9999", headers=admin).json()["correlationId"]
    assert primeiro and segundo and primeiro != segundo


def test_detalhes_de_validacao_apontam_os_campos(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "X", "email": "nao-e-email", "senha": "curta"},
    ).json()
    campos = {detalhe["campo"] for detalhe in corpo["detalhes"]}
    assert {"nome", "email", "senha"} <= campos
    for detalhe in corpo["detalhes"]:
        assert set(detalhe) == {"campo", "mensagem", "valorRejeitado"}
        assert detalhe["mensagem"]


def test_valor_rejeitado_omite_campos_sensiveis(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Nome Válido", "email": "a@mentefria.com", "senha": "curta"},
    )
    assert "curta" not in resposta.text
    detalhe = next(d for d in resposta.json()["detalhes"] if d["campo"] == "senha")
    assert detalhe["valorRejeitado"] is None


def test_corpo_ilegivel_resulta_em_400_sem_ecoar_o_conteudo(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/usuarios",
        headers={**admin, "Content-Type": "application/json"},
        content=b"{isso nao e json",
    )
    erro = assert_api_error(resposta, 400, "BAD_REQUEST")
    assert "isso nao e json" not in resposta.text
    assert erro["detalhes"][0]["campo"] == "corpo"


def test_campo_do_corpo_invalido_resulta_em_422(
    client: TestClient, admin: dict[str, str]
) -> None:
    """A operação declara 400 e 422: campo inválido é 422."""
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Nome Válido", "email": "a@mentefria.com", "senha": "curta"},
    )
    assert resposta.status_code == 422


def test_parametro_incompativel_resulta_em_400(
    client: TestClient, admin: dict[str, str]
) -> None:
    """A operação declara 400: parâmetro fora dos limites é 400, não 422."""
    assert client.get("/api/v1/usuarios", headers=admin, params={"page": -1}).status_code == 400


def test_id_de_caminho_invalido_usa_status_declarado(
    client: TestClient, admin: dict[str, str]
) -> None:
    """`consultarUsuario` não declara 400 nem 422; declara 404 (decisão da Fase 4)."""
    assert_api_error(client.get("/api/v1/usuarios/0", headers=admin), 404, "NOT_FOUND")


def test_rota_inexistente_usa_o_envelope(client: TestClient) -> None:
    resposta = client.get("/api/v1/nao-existe")
    assert resposta.status_code == 404
    assert set(resposta.json()) == campos_do_api_error()


def test_auth_me_nao_existe(client: TestClient, admin: dict[str, str]) -> None:
    """Rota de outro projeto: não pertence a este contrato."""
    assert client.get("/api/v1/auth/me", headers=admin).status_code == 404


def test_metodo_nao_permitido_usa_o_envelope(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.request("DELETE", "/api/v1/saude", headers=admin)
    assert resposta.status_code == 405
    assert set(resposta.json()) == campos_do_api_error()


def test_erro_interno_nao_vaza_stack_trace(client: TestClient, admin: dict[str, str], monkeypatch) -> None:
    """500 tratado: envelope `ApiError` e nenhum detalhe interno na resposta."""
    from src.api.services import usuarios as servico

    def _explodir(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("segredo-interno-que-nao-pode-vazar")

    monkeypatch.setattr(servico, "listar", _explodir)
    resposta = client.get("/api/v1/usuarios", headers=admin)
    assert resposta.status_code == 500
    corpo = resposta.json()
    assert set(corpo) == campos_do_api_error()
    assert corpo["codigo"] == "INTERNAL_ERROR"
    assert "segredo-interno" not in resposta.text
    assert "Traceback" not in resposta.text
    assert "RuntimeError" not in resposta.text


@pytest.mark.parametrize(
    "caminho",
    ["/api/v1/usuarios/1", "/api/v1/clientes/1", "/api/v1/produtos/1", "/api/v1/ingredientes/1"],
)
def test_204_nunca_tem_corpo(
    client: TestClient, admin: dict[str, str], caminho: str, cenario_venda: dict[str, Any]
) -> None:
    resposta = client.delete(caminho, headers=admin)
    if resposta.status_code == 204:
        assert resposta.content == b""
        assert "application/json" not in resposta.headers.get("content-type", "")
    else:  # 409 de integridade também é resposta válida do contrato
        assert resposta.status_code in (404, 409)
        assert set(resposta.json()) == campos_do_api_error()
