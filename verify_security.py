# ruff: noqa: BLE001  -- script auxiliar: exceções amplas são intencionais
"""Verificação prática da Fase 4 (segurança, autenticação e erros) — Mente Fria API.

NÃO é a suíte definitiva da Fase 6 (pytest). Executa, em SQLite em memória, as
conferências de hash de senha, JWT, HTTP Bearer, ``get_current_user``, ``require_role``,
matriz RBAC contra o OpenAPI, fluxos de bootstrap/login/cadastro e handlers do envelope
``ApiError``. Uso, na raiz do repositório:

    python verify_security.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ambiente de teste ANTES de importar a aplicação (nunca toca o banco de desenvolvimento).
for _k in [k for k in os.environ if k.startswith("MENTE_FRIA_")]:
    del os.environ[_k]
os.environ.update(
    MENTE_FRIA_ENV="test",
    MENTE_FRIA_JWT_SECRET_KEY="chave-apenas-para-verificacao",
    MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS="60",
)

import jwt
from fastapi import FastAPI, Query
from fastapi import Path as PathParam
from fastapi.security.http import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from src.api import database as db
from src.api import models as M
from src.api import security as sec
from src.api.config import Settings, get_settings
from src.api.exceptions import (
    ApiException,
    ConflitoError,
    DependenciaIndisponivelError,
    NaoAutenticadoError,
    NaoEncontradoError,
    ProibidoError,
    RequisicaoInvalidaError,
    ValidacaoError,
    registrar_handlers,
    resposta_sem_conteudo,
)
from src.api.main import create_app
from src.api.schemas import ApiError, CreateAdminDTO, CreateFuncionarioDTO, LoginDTO

OK = FAIL = 0
CONTRATO = Path("Mente Fria API.openapi.json")

SENHA = "SenhaForte#2026"


class CorpoDeTeste(BaseModel):
    """Corpo mínimo para exercitar a classificação 400 x 422.

    Definido no escopo do módulo: com ``from __future__ import annotations`` o FastAPI
    resolve as anotações pelos globais do módulo, e uma classe local não seria encontrada.
    """

    preco: float = Field(gt=0)


def check(name: str, cond: bool, detail: str = "") -> None:
    global OK, FAIL
    if cond:
        OK += 1
    else:
        FAIL += 1
        print(f"  FALHOU: {name} {detail}")


def erro_de(exc: type[ApiException], fn) -> ApiException | None:
    """Executa ``fn`` e devolve a exceção de domínio esperada (ou ``None``)."""
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:
        print(f"    (exceção inesperada: {type(e).__name__}: {e})")
        return None
    return None


def fresh() -> Session:
    engine = db.create_db_engine(get_settings())
    db.init_db(engine)
    return db.SessionLocal(bind=engine)


def novo_usuario(s: Session, perfil: str, email: str, *, ativo: bool = True) -> M.UsuarioModel:
    u = M.UsuarioModel(
        nome="Teste",
        email=email,
        senha_hash=sec.gerar_hash_senha(SENHA),
        perfil=perfil,
        ativo=ativo,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def credenciais(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ---------------------------------------------------------------------------


def main() -> int:
    # 1 — hash de senha (P4-01, P4-02) ----------------------------------------------------
    print("[1] hash de senha (Argon2id)")
    h = sec.gerar_hash_senha(SENHA)
    check("hash não é a senha em texto puro", SENHA not in h)
    check("formato PHC argon2id", h.startswith("$argon2id$"), h[:30])
    # Campo 4 da string PHC: "m=65536,t=3,p=4" — confere os custos efetivamente gravados.
    custos = dict(par.split("=", 1) for par in h.split("$")[3].split(","))
    check("custos gravados conferem com PARAMETROS_HASH",
          custos == {"m": str(sec.PARAMETROS_HASH["memory_cost"]),
                     "t": str(sec.PARAMETROS_HASH["time_cost"]),
                     "p": str(sec.PARAMETROS_HASH["parallelism"])},
          str(custos))
    check("versão do Argon2 é 19 (RFC 9106)", h.split("$")[2] == "v=19", h[:30])
    check("senha correta verifica", sec.verificar_senha(SENHA, h) is True)
    check("senha errada não verifica", sec.verificar_senha("outra-senha-123", h) is False)
    check("sal aleatório: dois hashes diferem", sec.gerar_hash_senha(SENHA) != h)
    for rotulo, invalido in (
        ("vazio", ""),
        ("None", None),
        ("lixo", "nao-é-um-hash"),
        ("bcrypt", "$2b$12$abcdefghijklmnopqrstuv"),
        ("argon2 truncado", "$argon2id$v=19$m=65536"),
        ("fora do ASCII", "$argon2id$café"),
        ("bytes em vez de str", b"$argon2id$v=19$m=65536,t=3,p=4$abc$def"),
    ):
        check(
            f"hash inválido ({rotulo}) devolve False sem exceção",
            sec.verificar_senha(SENHA, invalido) is False,
        )
    check("precisa_rehash é False para hash atual", sec.precisa_rehash(h) is False)
    check("precisa_rehash é False (sem exceção) para hash inválido", sec.precisa_rehash("x") is False)

    # 2 — JWT (P4-03, P4-04) --------------------------------------------------------------
    print("[2] emissão e validação de JWT (PyJWT/HS256)")
    s = fresh()
    admin = novo_usuario(s, sec.PERFIL_ADMINISTRADOR, "admin@exemplo.com")
    func = novo_usuario(s, sec.PERFIL_FUNCIONARIO, "func@exemplo.com")
    settings = get_settings()
    segredo = settings.jwt_secret_key.get_secret_value()

    token, expira = sec.criar_token_acesso(admin)
    claims = sec.decodificar_token(token)
    check("expiresInSeconds vem da configuração", expira == settings.jwt_access_token_expire_seconds == 60)
    check("claims mínimos (sub, perfil, iat, exp)", set(claims) == {"sub", "perfil", "iat", "exp"}, str(set(claims)))
    check("sub identifica o usuário", claims["sub"] == str(admin.id))
    check("perfil no token", claims["perfil"] == sec.PERFIL_ADMINISTRADOR)
    check("exp = iat + expiração configurada", claims["exp"] - claims["iat"] == 60)
    check("algoritmo do header é HS256", jwt.get_unverified_header(token)["alg"] == "HS256")
    check("token não embute e-mail nem hash", "exemplo.com" not in token and "argon2" not in token)

    agora = datetime.now(UTC)
    expirado = jwt.encode(
        {"sub": str(admin.id), "perfil": admin.perfil,
         "iat": agora - timedelta(seconds=120), "exp": agora - timedelta(seconds=60)},
        segredo, algorithm="HS256")
    e = erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(expirado))
    check("token expirado -> 401", e is not None and e.status_code == 401)
    check("mensagem de expirado não expõe detalhes internos", e is not None and e.mensagem == "Token expirado.")

    outra_chave = jwt.encode({"sub": "1", "exp": agora + timedelta(seconds=60)}, "chave-errada", algorithm="HS256")
    check("assinatura inválida -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(outra_chave)) is not None)
    hs512 = jwt.encode({"sub": "1", "exp": agora + timedelta(seconds=60)}, segredo, algorithm="HS512")
    check("algoritmo divergente (HS512) -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(hs512)) is not None)
    sem_alg = jwt.encode({"sub": "1", "exp": agora + timedelta(seconds=60)}, None, algorithm="none")
    check("token sem assinatura (alg=none) -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(sem_alg)) is not None)
    sem_exp = jwt.encode({"sub": "1", "perfil": "ADMINISTRADOR"}, segredo, algorithm="HS256")
    check("token sem exp -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(sem_exp)) is not None)
    check("token adulterado -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token(token[:-3] + "abc")) is not None)
    check("texto arbitrário -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.decodificar_token("isso-nao-e-jwt")) is not None)

    # 3 — get_current_user (P4-05) --------------------------------------------------------
    print("[3] get_current_user")
    check("token válido resolve o usuário", sec.get_current_user(credenciais(token), s).id == admin.id)
    check("sem cabeçalho Authorization -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(None, s)) is not None)
    check("credencial vazia -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(credenciais(""), s)) is not None)

    inativo = novo_usuario(s, sec.PERFIL_FUNCIONARIO, "inativo@exemplo.com", ativo=False)
    token_inativo, _ = sec.criar_token_acesso(inativo)
    check("usuário inativo -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(credenciais(token_inativo), s)) is not None)

    fantasma = jwt.encode({"sub": "99999", "perfil": "ADMINISTRADOR", "iat": agora,
                           "exp": agora + timedelta(seconds=60)}, segredo, algorithm="HS256")
    check("usuário inexistente -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(credenciais(fantasma), s)) is not None)
    sub_invalido = jwt.encode({"sub": "nao-numerico", "exp": agora + timedelta(seconds=60)},
                              segredo, algorithm="HS256")
    check("sub não numérico -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(credenciais(sub_invalido), s)) is not None)
    desativado_depois = novo_usuario(s, sec.PERFIL_FUNCIONARIO, "depois@exemplo.com")
    tok_dd, _ = sec.criar_token_acesso(desativado_depois)
    desativado_depois.ativo = False
    s.commit()
    check("conta desativada após a emissão do token -> 401",
          erro_de(NaoAutenticadoError, lambda: sec.get_current_user(credenciais(tok_dd), s)) is not None)

    # 4 — require_role (P4-06) ------------------------------------------------------------
    print("[4] require_role")
    so_admin = sec.require_role(sec.PERFIL_ADMINISTRADOR)
    ambos = sec.require_role(sec.PERFIL_ADMINISTRADOR, sec.PERFIL_FUNCIONARIO)
    check("ADMINISTRADOR passa em restrição de administrador", so_admin(admin).id == admin.id)
    e = erro_de(ProibidoError, lambda: so_admin(func))
    check("FUNCIONARIO em rota de administrador -> 403", e is not None and e.status_code == 403)
    check("403 não revela o perfil exigido", e is not None and "ADMINISTRADOR" not in e.mensagem)
    check("ambos os perfis passam onde o contrato libera os dois",
          ambos(admin).id == admin.id and ambos(func).id == func.id)
    try:
        sec.require_role("ADMIN")
        check("perfil fora do domínio é recusado", False, "ADMIN foi aceito")
    except ValueError:
        check("perfil fora do domínio é recusado (ADMIN/MEMBER não existem)", True)
    check("somente dois perfis no domínio", sec.PERFIS == {"ADMINISTRADOR", "FUNCIONARIO"})

    # 5 — matriz RBAC x OpenAPI (P4-07) ---------------------------------------------------
    print("[5] matriz RBAC contra o contrato OpenAPI")
    spec = json.loads(CONTRATO.read_text(encoding="utf-8"))
    metodos = ("get", "post", "put", "patch", "delete")
    operacoes: dict[str, dict] = {}
    for caminho, item in spec["paths"].items():
        for metodo in metodos:
            op = item.get(metodo)
            if op:
                operacoes[op["operationId"]] = {"caminho": caminho, "metodo": metodo, "op": op}
    check("26 caminhos no contrato", len(spec["paths"]) == 26, str(len(spec["paths"])))
    check("44 operações no contrato", len(operacoes) == 44, str(len(operacoes)))
    check("matriz cobre exatamente as operações do contrato",
          set(sec.MATRIZ_RBAC) == set(operacoes),
          f"faltando={sorted(set(operacoes) - set(sec.MATRIZ_RBAC))} "
          f"sobrando={sorted(set(sec.MATRIZ_RBAC) - set(operacoes))}")

    publicas_contrato = {oid for oid, d in operacoes.items()
                         if d["op"].get("security", spec.get("security")) == []}
    publicas_matriz = {oid for oid, p in sec.MATRIZ_RBAC.items() if p == ()}
    check("operações públicas conferem com security: []",
          publicas_contrato == publicas_matriz,
          f"contrato={sorted(publicas_contrato)} matriz={sorted(publicas_matriz)}")
    check("as 3 públicas são saúde, bootstrap e login",
          publicas_matriz == {"consultarSaude", "criarContaAdministrador", "autenticarUsuario"})

    for oid, dados in operacoes.items():
        desc = f"{dados['op'].get('summary', '')} {dados['op'].get('description', '')}"
        perfis = sec.MATRIZ_RBAC[oid]
        declara_401 = "401" in dados["op"]["responses"]
        declara_403 = "403" in dados["op"]["responses"]
        if perfis == ():
            check(f"{oid}: pública não declara 403", not declara_403)
            continue
        check(f"{oid}: protegida declara Bearer",
              dados["op"].get("security", spec.get("security")) == [{"bearerAuth": []}])
        check(f"{oid}: protegida declara 401 e 403", declara_401 and declara_403)
        # "Atores autorizados: ADMINISTRADOR e FUNCIONARIO" -> ambos
        if "ADMINISTRADOR e FUNCIONARIO" in desc:
            check(f"{oid}: ambos os perfis conforme a descrição",
                  perfis == (sec.PERFIL_ADMINISTRADOR, sec.PERFIL_FUNCIONARIO), str(perfis))
        # "Restrito ao perfil ADMINISTRADOR" / "somente ADMINISTRADOR" -> administrador
        elif "Restrito ao perfil ADMINISTRADOR" in desc or "somente ADMINISTRADOR" in desc:
            check(f"{oid}: somente ADMINISTRADOR conforme a descrição",
                  perfis == (sec.PERFIL_ADMINISTRADOR,), str(perfis))
        elif "ADMINISTRADOR" not in desc and "FUNCIONARIO" not in desc:
            check(f"{oid}: descrição não restringe perfil -> sem restrição inventada",
                  perfis is None, str(perfis))

    # Efeito da decisão sobre parâmetros em operações sem 400/422 declarados: as de
    # caminho caem em 404 (status declarado); sobra o gap residual das de consulta.
    sem_400_422_caminho: list[str] = []
    sem_400_422_consulta: list[str] = []
    for oid, dados in operacoes.items():
        op = dados["op"]
        codigos = set(op.get("responses", {}))
        if {"400", "422"} & codigos:
            continue
        params = spec["paths"][dados["caminho"]].get("parameters", []) + op.get("parameters", [])
        if not params:
            continue
        if any(p.get("in") == "path" for p in params):
            sem_400_422_caminho.append(oid)
            check(f"{oid}: sem 400/422, mas declara 404 para o parâmetro de caminho",
                  "404" in codigos, str(sorted(codigos)))
        else:
            sem_400_422_consulta.append(oid)
    check("13 operações de caminho resolvidas por 404 declarado",
          len(sem_400_422_caminho) == 13, str(sorted(sem_400_422_caminho)))
    check("gap residual limitado a 2 operações de consulta",
          sorted(sem_400_422_consulta) == ["listarAlertasReposicao", "listarUnidadesMedida"],
          str(sorted(sem_400_422_consulta)))

    check("nenhuma operação inventada (sem /auth/me)",
          not any("/auth/me" in c for c in spec["paths"]) and "consultarUsuarioAutenticado" not in sec.MATRIZ_RBAC)
    check("27 operações somente ADMINISTRADOR",
          sum(1 for p in sec.MATRIZ_RBAC.values() if p == (sec.PERFIL_ADMINISTRADOR,)) == 27)
    check("5 operações para ambos os perfis (clientes)",
          sum(1 for p in sec.MATRIZ_RBAC.values()
              if p == (sec.PERFIL_ADMINISTRADOR, sec.PERFIL_FUNCIONARIO)) == 5)
    check("9 operações apenas autenticadas",
          sum(1 for p in sec.MATRIZ_RBAC.values() if p is None) == 9)
    check("dependencia_de_autorizacao: pública sem dependência",
          sec.dependencia_de_autorizacao("autenticarUsuario") is None)
    check("dependencia_de_autorizacao: autenticada e restrita devolvem Depends",
          sec.dependencia_de_autorizacao("listarPedidos") is not None
          and sec.dependencia_de_autorizacao("listarUsuarios") is not None)
    try:
        sec.dependencia_de_autorizacao("listarTarefas")
        check("operação fora do contrato é recusada", False)
    except KeyError:
        check("operação fora do contrato é recusada", True)

    # 6 — bootstrap, login e cadastro (P4-08, P4-09, P4-10) -------------------------------
    print("[6] bootstrap do administrador, login e cadastro de funcionário")
    s2 = fresh()
    check("sem administrador no banco novo", sec.existe_administrador(s2) is False)
    criado = sec.criar_conta_administrador(
        s2, CreateAdminDTO(nome="Dona Maria", email="Maria@Exemplo.com ", senha=SENHA))
    check("bootstrap cria ADMINISTRADOR", criado.perfil == sec.PERFIL_ADMINISTRADOR and criado.ativo is True)
    check("e-mail normalizado para minúsculas", criado.email == "maria@exemplo.com")
    check("senha persistida somente como hash",
          criado.senha_hash.startswith("$argon2id$") and SENHA not in criado.senha_hash)
    check("bootstrap consumido", sec.existe_administrador(s2) is True)

    e = erro_de(ConflitoError, lambda: sec.criar_conta_administrador(
        s2, CreateAdminDTO(nome="Outro Admin", email="outro@exemplo.com", senha=SENHA)))
    check("segundo bootstrap -> 409", e is not None and e.status_code == 409)
    check("ainda existe um único administrador", sec._contar_administradores(s2) == 1)

    f1 = sec.cadastrar_funcionario(
        s2, CreateFuncionarioDTO(nome="João Silva", email="joao@exemplo.com", senha=SENHA))
    check("cadastro comum atribui FUNCIONARIO", f1.perfil == sec.PERFIL_FUNCIONARIO)
    e = erro_de(ConflitoError, lambda: sec.cadastrar_funcionario(
        s2, CreateFuncionarioDTO(nome="Outro Joao", email="JOAO@exemplo.com", senha=SENHA)))
    check("e-mail duplicado (outra caixa) -> 409", e is not None and e.status_code == 409)
    check("sessão utilizável após o rollback do conflito", sec._contar_administradores(s2) == 1)
    try:
        CreateFuncionarioDTO(nome="Hacker", email="h@exemplo.com", senha=SENHA, perfil="ADMINISTRADOR")  # type: ignore[call-arg]
        check("DTO recusa perfil enviado pelo cliente", False, "perfil foi aceito")
    except ValidationError:
        check("DTO recusa perfil enviado pelo cliente (additionalProperties: false)", True)

    logado = sec.autenticar(s2, LoginDTO(email="maria@exemplo.com", senha=SENHA))
    check("login válido devolve o usuário", logado.id == criado.id)
    check("login aceita e-mail em outra caixa",
          sec.autenticar(s2, LoginDTO(email="MARIA@EXEMPLO.COM", senha=SENHA)).id == criado.id)
    e = erro_de(NaoAutenticadoError, lambda: sec.autenticar(
        s2, LoginDTO(email="maria@exemplo.com", senha="SenhaErrada#99")))
    check("senha errada -> 401", e is not None and e.status_code == 401)
    msg_senha_errada = e.mensagem if e else ""
    e = erro_de(NaoAutenticadoError, lambda: sec.autenticar(
        s2, LoginDTO(email="ninguem@exemplo.com", senha=SENHA)))
    check("e-mail inexistente -> 401", e is not None and e.status_code == 401)
    check("mesma mensagem para senha errada e e-mail inexistente",
          e is not None and e.mensagem == msg_senha_errada)

    f1.ativo = False
    s2.commit()
    e = erro_de(NaoAutenticadoError, lambda: sec.autenticar(
        s2, LoginDTO(email="joao@exemplo.com", senha=SENHA)))
    check("conta inativa -> 401 (não 403)", e is not None and e.status_code == 401)
    check("mensagem de conta inativa não revela o motivo",
          e is not None and e.mensagem == msg_senha_errada)

    # Bootstrap concorrente: duas threads, e-mails distintos, banco em ARQUIVO temporário
    # (o banco em memória compartilha uma única conexão e não exercitaria a trava).
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "concorrencia.db"
        cfg = Settings(
            env="test",
            database_url=f"sqlite:///{arquivo.as_posix()}",
            jwt_secret_key="chave-apenas-para-verificacao",
            jwt_access_token_expire_seconds=60,
        )
        engine_arquivo = db.create_db_engine(cfg)
        db.init_db(engine_arquivo, cfg)
        resultados: list[object] = []
        barreira = threading.Barrier(2)

        def tentar_bootstrap(indice: int) -> None:
            sessao = db.SessionLocal(bind=engine_arquivo)
            try:
                barreira.wait(timeout=5)
                resultados.append(sec.criar_conta_administrador(
                    sessao,
                    CreateAdminDTO(nome=f"Admin {indice}", email=f"admin{indice}@exemplo.com",
                                   senha=SENHA)))
            except Exception as exc:  # captura o 409 esperado de uma das threads
                resultados.append(exc)
            finally:
                sessao.close()

        threads = [threading.Thread(target=tentar_bootstrap, args=(i,)) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        sucessos = [r for r in resultados if isinstance(r, M.UsuarioModel)]
        conflitos = [r for r in resultados if isinstance(r, ConflitoError)]
        outros = [r for r in resultados if not isinstance(r, M.UsuarioModel | ConflitoError)]
        check("bootstrap concorrente: exatamente 1 sucesso", len(sucessos) == 1, str(resultados))
        check("bootstrap concorrente: a outra tentativa recebe 409",
              len(conflitos) == 1 and conflitos[0].status_code == 409, str(resultados))
        check("bootstrap concorrente: nenhuma falha inesperada", not outros, str(outros))
        sessao_final = db.SessionLocal(bind=engine_arquivo)
        check("bootstrap concorrente: um único ADMINISTRADOR no banco",
              sec._contar_administradores(sessao_final) == 1)
        sessao_final.close()
        engine_arquivo.dispose()

    auth = sec.montar_auth_token(criado)
    check("AuthToken.tokenType = Bearer", auth.tokenType == "Bearer")
    check("AuthToken.expiresInSeconds = configuração", auth.expiresInSeconds == 60)
    check("AuthToken.usuario sem senha/hash",
          set(auth.usuario.model_dump()) == {"id", "nome", "email", "perfil", "ativo"})
    corpo = auth.model_dump_json()
    check("AuthToken serializado não contém senha nem hash",
          SENHA not in corpo and "argon2" not in corpo, corpo[:80])

    # 7 — handlers do envelope ApiError (P4-12 a P4-17) -----------------------------------
    print("[7] handlers globais do envelope ApiError")

    app = FastAPI()
    registrar_handlers(app)

    @app.get("/erro/{status}", responses={400: {"model": ApiError}, 404: {"model": ApiError}})
    def _erro(status: int):
        mapa: dict[int, ApiException] = {
            400: RequisicaoInvalidaError(),
            401: NaoAutenticadoError(),
            403: ProibidoError(),
            404: NaoEncontradoError(),
            409: ConflitoError(),
            422: ValidacaoError(),
            503: DependenciaIndisponivelError(),
        }
        raise mapa[status]

    @app.post("/val/ambos", responses={400: {"model": ApiError}, 422: {"model": ApiError}})
    def _val_ambos(corpo: CorpoDeTeste):
        return corpo

    @app.post("/val/so422", responses={422: {"model": ApiError}})
    def _val_so422(corpo: CorpoDeTeste):
        return corpo

    @app.get("/val/so400", responses={400: {"model": ApiError}})
    def _val_so400(pagina: int = Query(ge=0)):
        return {"pagina": pagina}

    @app.get("/val/nenhum")
    def _val_nenhum(pagina: int = Query(ge=0)):
        return {"pagina": pagina}

    # Parâmetro de caminho: reproduz as operações do contrato que declaram 404 mas não
    # declaram 400 nem 422 (ex.: GET /api/v1/usuarios/{id} com minimum: 1).
    @app.get("/caminho/so404/{identificador}", responses={404: {"model": ApiError}})
    def _caminho_so404(identificador: int = PathParam(ge=1)):
        return {"id": identificador}

    @app.get(
        "/caminho/com400/{identificador}",
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def _caminho_com400(identificador: int = PathParam(ge=1)):
        return {"id": identificador}

    @app.get("/caminho/nenhum/{identificador}")
    def _caminho_nenhum(identificador: int = PathParam(ge=1)):
        return {"id": identificador}

    @app.get("/caminho/misto/{identificador}", responses={404: {"model": ApiError}})
    def _caminho_misto(identificador: int = PathParam(ge=1), pagina: int = Query(ge=0)):
        return {"id": identificador, "pagina": pagina}

    @app.post("/login-falso", responses={401: {"model": ApiError}, 422: {"model": ApiError}})
    def _login_falso(dto: LoginDTO):
        return {"ok": True}

    @app.delete("/sem-conteudo", status_code=204, responses={204: {"description": "sem corpo"}})
    def _sem_conteudo():
        return resposta_sem_conteudo()

    @app.get("/explode")
    def _explode():
        raise RuntimeError("segredo-interno-que-nao-deve-aparecer")

    cliente = TestClient(app, raise_server_exceptions=False)

    for status in (400, 401, 403, 404, 409, 422, 503):
        r = cliente.get(f"/erro/{status}")
        corpo = r.json()
        check(f"{status}: status HTTP correto", r.status_code == status, str(r.status_code))
        check(f"{status}: envelope ApiError completo",
              set(corpo) == {"codigo", "mensagem", "detalhes", "timestamp", "caminho", "correlationId"},
              str(sorted(corpo)))
        check(f"{status}: não é o formato do FastAPI nem RFC 9457",
              "detail" not in corpo and not {"type", "title", "status", "instance"} & set(corpo))
        check(f"{status}: ApiError valida contra o schema", ApiError.model_validate(corpo) is not None)
        check(f"{status}: caminho e timestamp preenchidos",
              corpo["caminho"] == f"/erro/{status}" and corpo["timestamp"].startswith("20"))
        check(f"{status}: correlationId presente", bool(corpo["correlationId"]))
        check(f"{status}: detalhes é lista", isinstance(corpo["detalhes"], list))

    codigos = {status: cliente.get(f"/erro/{status}").json()["codigo"]
               for status in (400, 401, 403, 404, 409, 422, 503)}
    check("códigos estáveis por status",
          codigos == {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                      409: "CONFLICT", 422: "VALIDATION_ERROR", 503: "SERVICE_UNAVAILABLE"},
          str(codigos))

    r = cliente.post("/val/ambos", json={"preco": 0})
    check("campo do corpo inválido -> 422 (operação declara 400 e 422)", r.status_code == 422, str(r.status_code))
    detalhes = r.json()["detalhes"]
    check("detalhe aponta o campo", detalhes and detalhes[0]["campo"] == "preco", str(detalhes))
    check("detalhe traz mensagem e valorRejeitado",
          detalhes[0]["mensagem"] and detalhes[0]["valorRejeitado"] == "0", str(detalhes))
    check("detalhe valida contra ApiErrorDetail", ApiError.model_validate(r.json()) is not None)

    r = cliente.post("/val/ambos", content=b"{isso nao e json", headers={"Content-Type": "application/json"})
    check("corpo ilegível -> 400 (operação declara 400)", r.status_code == 400, str(r.status_code))
    check("400 de corpo ilegível não ecoa o conteúdo",
          "isso nao e json" not in r.text and r.json()["detalhes"][0]["campo"] == "corpo")

    r = cliente.post("/val/so422", content=b"{quebrado", headers={"Content-Type": "application/json"})
    check("corpo ilegível em operação sem 400 -> 422", r.status_code == 422, str(r.status_code))
    r = cliente.get("/val/so400", params={"pagina": -1})
    check("parâmetro incompatível -> 400 (operação declara 400)", r.status_code == 400, str(r.status_code))
    check("detalhe do parâmetro nomeia o campo", r.json()["detalhes"][0]["campo"] == "pagina", r.text[:120])
    r = cliente.get("/val/nenhum", params={"pagina": -1})
    check("parâmetro de consulta sem 400 nem 422 declarados -> 422 (padrão documentado)",
          r.status_code == 422, str(r.status_code))

    r = cliente.get("/caminho/so404/0")
    check("parâmetro de caminho inválido, operação declara só 404 -> 404 (status declarado)",
          r.status_code == 404, str(r.status_code))
    check("404 por caminho inválido usa ApiError e nomeia o parâmetro",
          r.json()["codigo"] == "NOT_FOUND" and r.json()["detalhes"][0]["campo"] == "identificador",
          r.text[:160])
    r = cliente.get("/caminho/com400/0")
    check("parâmetro de caminho inválido, operação declara 400 -> 400 (mais preciso que 404)",
          r.status_code == 400, str(r.status_code))
    r = cliente.get("/caminho/nenhum/0")
    check("parâmetro de caminho sem 400/404/422 declarados -> 422 (padrão documentado)",
          r.status_code == 422, str(r.status_code))
    r = cliente.get("/caminho/misto/0", params={"pagina": -1})
    check("caminho inválido tem precedência sobre consulta inválida -> 404",
          r.status_code == 404, str(r.status_code))
    r = cliente.get("/caminho/misto/5", params={"pagina": -1})
    check("só a consulta inválida, operação sem 400/422 -> 422",
          r.status_code == 422, str(r.status_code))
    r = cliente.get("/caminho/so404/7")
    check("caminho válido não é afetado", r.status_code == 200, str(r.status_code))
    r = cliente.post("/val/so422", json={"preco": 10})
    check("requisição válida não é afetada pelos handlers", r.status_code == 200, str(r.status_code))

    r = cliente.post("/login-falso", json={"email": "a@b.com", "senha": "curta"})
    check("validação de senha curta -> 422", r.status_code == 422, str(r.status_code))
    check("senha rejeitada NÃO aparece em valorRejeitado",
          "curta" not in r.text, r.text[:200])
    check("campo da senha é identificado", r.json()["detalhes"][0]["campo"] == "senha", r.text[:200])
    r = cliente.post("/login-falso", json={"email": "nao-email", "senha": SENHA})
    check("e-mail inválido -> 422 com campo email", r.status_code == 422 and r.json()["detalhes"][0]["campo"] == "email")
    check("senha enviada não vaza no erro de e-mail", SENHA not in r.text, r.text[:200])

    r = cliente.delete("/sem-conteudo")
    check("204 sem corpo", r.status_code == 204 and r.content == b"", repr(r.content))
    check("204 sem Content-Type de JSON", "application/json" not in r.headers.get("content-type", ""),
          r.headers.get("content-type", ""))

    r = cliente.get("/explode")
    check("exceção não tratada -> 500 no envelope ApiError",
          r.status_code == 500 and r.json()["codigo"] == "INTERNAL_ERROR", str(r.status_code))
    check("500 não expõe stack trace nem a mensagem interna",
          "segredo-interno" not in r.text and "Traceback" not in r.text and "RuntimeError" not in r.text,
          r.text[:200])
    check("500 valida contra ApiError", ApiError.model_validate(r.json()) is not None)

    r = cliente.get("/rota-que-nao-existe")
    check("404 de rota inexistente usa ApiError", r.status_code == 404 and "codigo" in r.json())
    r = cliente.post("/erro/404")
    check("405 método não permitido usa ApiError", r.status_code == 405 and "codigo" in r.json(), str(r.status_code))

    # 8 — aplicação real (P4-12, item 9 do prompt) ----------------------------------------
    print("[8] aplicação real: handlers registrados e nenhuma rota fora do contrato")
    app_real = create_app()
    cliente_real = TestClient(app_real, raise_server_exceptions=False)
    r = cliente_real.get("/api/v1/auth/me")
    check("GET /api/v1/auth/me não existe", r.status_code == 404, str(r.status_code))
    check("404 da aplicação real usa ApiError",
          set(r.json()) == {"codigo", "mensagem", "detalhes", "timestamp", "caminho", "correlationId"},
          str(sorted(r.json())))
    caminhos = {rota.path for rota in app_real.routes if hasattr(rota, "path")}
    negocio = {c for c in caminhos if c.startswith("/api/v1")}
    check("nenhum router de negócio registrado (Fase 5)", negocio == set(), str(negocio))
    check("openapi.json da aplicação responde", cliente_real.get("/openapi.json").status_code == 200)

    print()
    print(f"{OK} verificações OK, {FAIL} falhas")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
