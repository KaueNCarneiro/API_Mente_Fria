"""Testes de autenticação: bootstrap, login, hash e JWT (Fase 6 — P6-05)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.models import UsuarioModel
from src.api.security import PARAMETROS_HASH, verificar_senha

from .conftest import EMAIL_ADMIN, EMAIL_FUNCIONARIO, SENHA_PADRAO, assert_api_error

SEGREDO = "segredo-exclusivo-da-suite-de-testes"


def _bootstrap(client: TestClient, email: str = EMAIL_ADMIN) -> dict:
    return client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": email, "senha": SENHA_PADRAO},
    ).json()


# --- bootstrap ------------------------------------------------------------------------


def test_bootstrap_cria_primeiro_administrador(client: TestClient) -> None:
    resposta = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    )
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["perfil"] == "ADMINISTRADOR"
    assert corpo["ativo"] is True
    assert set(corpo) == {"id", "nome", "email", "perfil", "ativo"}


def test_bootstrap_devolve_location(client: TestClient) -> None:
    resposta = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    )
    assert resposta.headers["location"] == f"/api/v1/usuarios/{resposta.json()['id']}"


def test_bootstrap_e_publico(client: TestClient) -> None:
    """Sem token: a operação é pública no contrato."""
    assert client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    ).status_code == 201


def test_segundo_bootstrap_resulta_em_conflito(client: TestClient) -> None:
    _bootstrap(client)
    resposta = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Outro", "email": "outro@mentefria.com", "senha": SENHA_PADRAO},
    )
    assert_api_error(resposta, 409, "CONFLICT")


def test_bootstrap_nao_cria_segundo_administrador_no_banco(
    client: TestClient, db: Session
) -> None:
    _bootstrap(client)
    client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Outro", "email": "outro@mentefria.com", "senha": SENHA_PADRAO},
    )
    administradores = db.scalars(
        select(UsuarioModel).where(UsuarioModel.perfil == "ADMINISTRADOR")
    ).all()
    assert len(administradores) == 1


def test_bootstrap_com_email_duplicado_resulta_em_conflito(client: TestClient) -> None:
    _bootstrap(client)
    resposta = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Mesma pessoa", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    )
    assert_api_error(resposta, 409)


# --- hash de senha --------------------------------------------------------------------


def test_senha_e_persistida_apenas_como_hash_argon2id(client: TestClient, db: Session) -> None:
    _bootstrap(client)
    usuario = db.scalar(select(UsuarioModel).where(UsuarioModel.email == EMAIL_ADMIN))
    assert usuario is not None
    assert usuario.senha_hash.startswith("$argon2id$")
    assert SENHA_PADRAO not in usuario.senha_hash
    assert verificar_senha(SENHA_PADRAO, usuario.senha_hash) is True


def test_hash_usa_os_parametros_aprovados(client: TestClient, db: Session) -> None:
    _bootstrap(client)
    usuario = db.scalar(select(UsuarioModel).where(UsuarioModel.email == EMAIL_ADMIN))
    assert usuario is not None
    custos = dict(par.split("=", 1) for par in usuario.senha_hash.split("$")[3].split(","))
    assert custos == {
        "m": str(PARAMETROS_HASH["memory_cost"]),
        "t": str(PARAMETROS_HASH["time_cost"]),
        "p": str(PARAMETROS_HASH["parallelism"]),
    }


def test_respostas_de_autenticacao_nao_expoem_senha_nem_hash(client: TestClient) -> None:
    criacao = client.post(
        "/api/v1/auth/administrador",
        json={"nome": "Marina Admin", "email": EMAIL_ADMIN, "senha": SENHA_PADRAO},
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN, "senha": SENHA_PADRAO}
    )
    for resposta in (criacao, login):
        assert SENHA_PADRAO not in resposta.text
        assert "argon2" not in resposta.text
        assert "senha" not in resposta.json()


# --- login ----------------------------------------------------------------------------


def test_login_bem_sucedido_devolve_authtoken(client: TestClient) -> None:
    _bootstrap(client)
    resposta = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN, "senha": SENHA_PADRAO}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"accessToken", "tokenType", "expiresInSeconds", "usuario"}
    assert corpo["tokenType"] == "Bearer"
    assert corpo["expiresInSeconds"] == 3600
    assert corpo["usuario"]["email"] == EMAIL_ADMIN


def test_login_aceita_email_em_outra_caixa(client: TestClient) -> None:
    _bootstrap(client)
    resposta = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN.upper(), "senha": SENHA_PADRAO}
    )
    assert resposta.status_code == 200


@pytest.mark.parametrize(
    ("email", "senha", "caso"),
    [
        (EMAIL_ADMIN, "SenhaErrada#2026", "senha errada"),
        ("ninguem@mentefria.com", SENHA_PADRAO, "e-mail inexistente"),
    ],
)
def test_login_invalido_resulta_em_401(
    client: TestClient, email: str, senha: str, caso: str
) -> None:
    _bootstrap(client)
    resposta = client.post("/api/v1/auth/login", json={"email": email, "senha": senha})
    assert_api_error(resposta, 401, "UNAUTHORIZED"), caso


def test_login_de_conta_inativa_resulta_em_401(
    client: TestClient, admin: dict[str, str], funcionario_token: str
) -> None:
    pagina = client.get("/api/v1/usuarios", headers=admin).json()
    funcionario_id = next(u["id"] for u in pagina["data"] if u["perfil"] == "FUNCIONARIO")
    assert client.delete(f"/api/v1/usuarios/{funcionario_id}", headers=admin).status_code == 204

    resposta = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_FUNCIONARIO, "senha": SENHA_PADRAO}
    )
    assert_api_error(resposta, 401)


def test_mensagem_de_401_nao_distingue_os_casos(client: TestClient) -> None:
    """Não revelar se a conta existe: as mensagens precisam ser iguais."""
    _bootstrap(client)
    senha_errada = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN, "senha": "SenhaErrada#2026"}
    ).json()["mensagem"]
    inexistente = client.post(
        "/api/v1/auth/login", json={"email": "ninguem@mentefria.com", "senha": SENHA_PADRAO}
    ).json()["mensagem"]
    assert senha_errada == inexistente


# --- token --------------------------------------------------------------------------


def test_token_ausente_resulta_em_401(client: TestClient) -> None:
    assert_api_error(client.get("/api/v1/usuarios"), 401, "UNAUTHORIZED")


def test_token_invalido_resulta_em_401(client: TestClient) -> None:
    resposta = client.get(
        "/api/v1/usuarios", headers={"Authorization": "Bearer isso-nao-e-um-jwt"}
    )
    assert_api_error(resposta, 401)


def test_token_expirado_resulta_em_401(client: TestClient, usuario_admin_id: int) -> None:
    agora = datetime.now(UTC)
    expirado = jwt.encode(
        {
            "sub": str(usuario_admin_id),
            "perfil": "ADMINISTRADOR",
            "iat": agora - timedelta(hours=2),
            "exp": agora - timedelta(hours=1),
        },
        SEGREDO,
        algorithm="HS256",
    )
    resposta = client.get("/api/v1/usuarios", headers={"Authorization": f"Bearer {expirado}"})
    assert_api_error(resposta, 401)


def test_token_assinado_com_outra_chave_resulta_em_401(
    client: TestClient, usuario_admin_id: int
) -> None:
    token = jwt.encode(
        {
            "sub": str(usuario_admin_id),
            "perfil": "ADMINISTRADOR",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        "outra-chave-qualquer",
        algorithm="HS256",
    )
    assert_api_error(
        client.get("/api/v1/usuarios", headers={"Authorization": f"Bearer {token}"}), 401
    )


def test_token_sem_assinatura_resulta_em_401(
    client: TestClient, usuario_admin_id: int
) -> None:
    token = jwt.encode(
        {"sub": str(usuario_admin_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        None,
        algorithm="none",
    )
    assert_api_error(
        client.get("/api/v1/usuarios", headers={"Authorization": f"Bearer {token}"}), 401
    )


def test_token_de_usuario_inexistente_resulta_em_401(client: TestClient, admin) -> None:
    token = jwt.encode(
        {
            "sub": "99999",
            "perfil": "ADMINISTRADOR",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        SEGREDO,
        algorithm="HS256",
    )
    assert_api_error(
        client.get("/api/v1/usuarios", headers={"Authorization": f"Bearer {token}"}), 401
    )


def test_token_continua_recusado_apos_desativacao(
    client: TestClient, admin: dict[str, str], funcionario: dict[str, str]
) -> None:
    """O token segue válido na assinatura, mas a conta foi desativada: 401."""
    pagina = client.get("/api/v1/usuarios", headers=admin).json()
    funcionario_id = next(u["id"] for u in pagina["data"] if u["perfil"] == "FUNCIONARIO")
    client.delete(f"/api/v1/usuarios/{funcionario_id}", headers=admin)
    assert_api_error(client.get("/api/v1/clientes", headers=funcionario), 401)


def test_token_nao_carrega_dados_sensiveis(client: TestClient) -> None:
    _bootstrap(client)
    token = client.post(
        "/api/v1/auth/login", json={"email": EMAIL_ADMIN, "senha": SENHA_PADRAO}
    ).json()["accessToken"]
    claims = jwt.decode(token, SEGREDO, algorithms=["HS256"])
    assert set(claims) == {"sub", "perfil", "iat", "exp"}
    assert EMAIL_ADMIN not in token
