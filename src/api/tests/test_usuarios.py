"""Testes do domínio de usuários (Fase 6 — P6-06, parte de P6-18 e P6-19).

Todas as operações de `/usuarios` são restritas a `ADMINISTRADOR` no contrato.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import EMAIL_ADMIN, SENHA_PADRAO, assert_api_error


def _id_do_funcionario(client: TestClient, admin: dict[str, str]) -> int:
    pagina = client.get("/api/v1/usuarios", headers=admin).json()
    return int(next(u["id"] for u in pagina["data"] if u["perfil"] == "FUNCIONARIO"))


# --- listagem e consulta --------------------------------------------------------------


def test_listar_usuarios_devolve_pagina_do_contrato(
    client: TestClient, admin: dict[str, str]
) -> None:
    corpo = client.get("/api/v1/usuarios", headers=admin).json()
    assert set(corpo) == {"data", "paginacao"}
    assert set(corpo["paginacao"]) == {"page", "size", "totalElements", "totalPages"}
    assert corpo["paginacao"]["size"] == 20  # padrão do contrato
    assert corpo["paginacao"]["page"] == 0


def test_usuario_nunca_expoe_senha_nem_hash(client: TestClient, admin: dict[str, str]) -> None:
    resposta = client.get("/api/v1/usuarios", headers=admin)
    assert "senha" not in resposta.text
    assert "argon2" not in resposta.text
    for usuario in resposta.json()["data"]:
        assert set(usuario) == {"id", "nome", "email", "perfil", "ativo"}


def test_consultar_usuario_por_id(
    client: TestClient, admin: dict[str, str], usuario_admin_id: int
) -> None:
    corpo = client.get(f"/api/v1/usuarios/{usuario_admin_id}", headers=admin).json()
    assert corpo["id"] == usuario_admin_id
    assert corpo["email"] == EMAIL_ADMIN


def test_consultar_usuario_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/usuarios/9999", headers=admin), 404, "NOT_FOUND")


# --- cadastro -------------------------------------------------------------------------


def test_cadastro_comum_atribui_sempre_funcionario(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Novo Colaborador", "email": "novo@mentefria.com", "senha": SENHA_PADRAO},
    )
    assert resposta.status_code == 201
    assert resposta.json()["perfil"] == "FUNCIONARIO"
    assert resposta.headers["location"] == f"/api/v1/usuarios/{resposta.json()['id']}"


def test_cadastro_recusa_perfil_enviado_pelo_cliente(
    client: TestClient, admin: dict[str, str]
) -> None:
    """`additionalProperties: false`: o cliente não escolhe o próprio perfil."""
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={
            "nome": "Esperto",
            "email": "esperto@mentefria.com",
            "senha": SENHA_PADRAO,
            "perfil": "ADMINISTRADOR",
        },
    )
    assert_api_error(resposta, 422, "VALIDATION_ERROR")


def test_cadastro_com_email_duplicado_resulta_em_409(
    client: TestClient, admin: dict[str, str]
) -> None:
    client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Primeiro", "email": "repetido@mentefria.com", "senha": SENHA_PADRAO},
    )
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Segundo", "email": "repetido@mentefria.com", "senha": SENHA_PADRAO},
    )
    assert_api_error(resposta, 409, "CONFLICT")


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("nome", "A"), ("email", "nao-e-email"), ("senha", "curta")],
)
def test_cadastro_valida_limites_do_contrato(
    client: TestClient, admin: dict[str, str], campo: str, valor: str
) -> None:
    corpo = {"nome": "Nome Válido", "email": "valido@mentefria.com", "senha": SENHA_PADRAO}
    corpo[campo] = valor
    resposta = client.post("/api/v1/usuarios", headers=admin, json=corpo)
    erro = assert_api_error(resposta, 422)
    assert erro["detalhes"][0]["campo"] == campo


def test_senha_rejeitada_nao_aparece_na_resposta(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Nome Válido", "email": "x@mentefria.com", "senha": "curta"},
    )
    assert resposta.status_code == 422
    assert "curta" not in resposta.text


# --- atualização ----------------------------------------------------------------------


def test_atualizar_nome_e_email(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    resposta = client.patch(
        f"/api/v1/usuarios/{funcionario_id}",
        headers=admin,
        json={"nome": "Caio Atualizado", "email": "caio.novo@mentefria.com"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Caio Atualizado"
    assert resposta.json()["email"] == "caio.novo@mentefria.com"


def test_atualizacao_parcial_preserva_campos_omitidos(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    antes = client.get(f"/api/v1/usuarios/{funcionario_id}", headers=admin).json()
    depois = client.patch(
        f"/api/v1/usuarios/{funcionario_id}", headers=admin, json={"nome": "Só o nome"}
    ).json()
    assert depois["email"] == antes["email"]
    assert depois["ativo"] == antes["ativo"]


def test_atualizacao_nao_altera_perfil(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    resposta = client.patch(
        f"/api/v1/usuarios/{funcionario_id}", headers=admin, json={"perfil": "ADMINISTRADOR"}
    )
    assert_api_error(resposta, 422)
    assert (
        client.get(f"/api/v1/usuarios/{funcionario_id}", headers=admin).json()["perfil"]
        == "FUNCIONARIO"
    )


def test_atualizar_para_email_ja_usado_resulta_em_409(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    resposta = client.patch(
        f"/api/v1/usuarios/{funcionario_id}", headers=admin, json={"email": EMAIL_ADMIN}
    )
    assert_api_error(resposta, 409)


def test_atualizar_usuario_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(
        client.patch("/api/v1/usuarios/9999", headers=admin, json={"nome": "Fantasma"}), 404
    )


# --- desativação lógica ---------------------------------------------------------------


def test_desativar_usuario_responde_204_sem_corpo(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    resposta = client.delete(f"/api/v1/usuarios/{funcionario_id}", headers=admin)
    assert resposta.status_code == 204
    assert resposta.content == b""
    assert "application/json" not in resposta.headers.get("content-type", "")


def test_desativacao_e_logica_e_preserva_o_registro(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    funcionario_id = _id_do_funcionario(client, admin)
    client.delete(f"/api/v1/usuarios/{funcionario_id}", headers=admin)
    corpo = client.get(f"/api/v1/usuarios/{funcionario_id}", headers=admin).json()
    assert corpo["ativo"] is False


def test_desativar_usuario_inexistente_resulta_em_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.delete("/api/v1/usuarios/9999", headers=admin), 404)


# --- paginação, busca e ordenação -----------------------------------------------------


def test_paginacao_respeita_page_e_size(client: TestClient, admin: dict[str, str]) -> None:
    for i in range(4):
        client.post(
            "/api/v1/usuarios",
            headers=admin,
            json={"nome": f"Pessoa {i}", "email": f"p{i}@mentefria.com", "senha": SENHA_PADRAO},
        )
    primeira = client.get("/api/v1/usuarios", headers=admin, params={"page": 0, "size": 2}).json()
    segunda = client.get("/api/v1/usuarios", headers=admin, params={"page": 1, "size": 2}).json()
    assert primeira["paginacao"]["totalElements"] == 5  # 1 admin + 4 criados
    assert primeira["paginacao"]["totalPages"] == 3
    assert len(primeira["data"]) == 2
    assert {u["id"] for u in primeira["data"]} & {u["id"] for u in segunda["data"]} == set()


def test_busca_textual_filtra_por_nome_ou_email(
    client: TestClient, admin: dict[str, str]
) -> None:
    client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Zuleica Souza", "email": "zuleica@mentefria.com", "senha": SENHA_PADRAO},
    )
    por_nome = client.get("/api/v1/usuarios", headers=admin, params={"q": "Zuleica"}).json()
    por_email = client.get("/api/v1/usuarios", headers=admin, params={"q": "zuleica@"}).json()
    assert por_nome["paginacao"]["totalElements"] == 1
    assert por_email["paginacao"]["totalElements"] == 1


def test_ordenacao_por_campo_permitido(client: TestClient, admin: dict[str, str]) -> None:
    client.post(
        "/api/v1/usuarios",
        headers=admin,
        json={"nome": "Ana Primeira", "email": "ana@mentefria.com", "senha": SENHA_PADRAO},
    )
    nomes = [
        u["nome"]
        for u in client.get(
            "/api/v1/usuarios", headers=admin, params={"sort": "nome,asc"}
        ).json()["data"]
    ]
    assert nomes == sorted(nomes)


def test_ordenacao_por_campo_invalido_resulta_em_400(
    client: TestClient, admin: dict[str, str]
) -> None:
    resposta = client.get("/api/v1/usuarios", headers=admin, params={"sort": "senha_hash,asc"})
    erro = assert_api_error(resposta, 400, "BAD_REQUEST")
    assert erro["detalhes"][0]["campo"] == "sort"


def test_size_acima_do_maximo_resulta_em_400(
    client: TestClient, admin: dict[str, str]
) -> None:
    assert_api_error(client.get("/api/v1/usuarios", headers=admin, params={"size": 101}), 400)


# --- autorização ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", "/api/v1/usuarios"),
        ("post", "/api/v1/usuarios"),
        ("get", "/api/v1/usuarios/1"),
        ("patch", "/api/v1/usuarios/1"),
        ("delete", "/api/v1/usuarios/1"),
    ],
)
def test_usuarios_exige_administrador(
    client: TestClient, funcionario: dict[str, str], metodo: str, caminho: str
) -> None:
    resposta = client.request(metodo.upper(), caminho, headers=funcionario, json={})
    assert_api_error(resposta, 403, "FORBIDDEN")


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", "/api/v1/usuarios"),
        ("post", "/api/v1/usuarios"),
        ("get", "/api/v1/usuarios/1"),
    ],
)
def test_usuarios_exige_autenticacao(client: TestClient, metodo: str, caminho: str) -> None:
    assert_api_error(client.request(metodo.upper(), caminho, json={}), 401)
