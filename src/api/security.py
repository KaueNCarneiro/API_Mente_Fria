"""Hash de senha, JWT, HTTP Bearer, ``get_current_user``, ``require_role`` e matriz RBAC
(Fase 4 — P4-01 a P4-10).

Decisões **aprovadas na revisão humana** e registradas no PLAN.md:

- **Hash (decisão 2 / P4-01):** Argon2id via ``argon2-cffi`` (``PasswordHasher``), com os
  parâmetros padrão da biblioteca — ver ``PARAMETROS_HASH``. Formato de armazenamento: a
  string PHC completa (``$argon2id$v=19$m=...``), que já embute sal e custos; coluna
  ``usuarios.senha_hash`` (``String(255)``). A senha em texto puro nunca é persistida.
- **Expiração (decisão 3 / P4-04):** vem de ``MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS``
  (obrigatória, sem padrão no código); 3600 s no ``.env.example`` é apenas referência de
  desenvolvimento. ``expiresInSeconds`` do ``AuthToken`` devolve exatamente esse valor.
- **E-mail (decisão 11 da Fase 3, delegada a esta fase):** normalizado para minúsculas e
  sem espaços nas pontas no cadastro e na busca de login, evitando contas duplicadas que
  difiram apenas por caixa. A coluna segue com ``UNIQUE`` exato.

A matriz RBAC (``MATRIZ_RBAC``) é derivada de ``security`` e das descrições de cada
operação do OpenAPI; operações que só exigem Bearer **não** recebem restrição de perfil.
O verificador ``verify_security.py`` compara a matriz com o contrato.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from types import MappingProxyType
from typing import Annotated, Any, Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from fastapi import Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .exceptions import ConflitoError, NaoAutenticadoError, ProibidoError
from .models import UsuarioModel
from .schemas import AuthToken, CreateAdminDTO, CreateFuncionarioDTO, LoginDTO, Usuario

logger = logging.getLogger(__name__)

__all__ = [
    "MATRIZ_RBAC",
    "PERFIL_ADMINISTRADOR",
    "PERFIL_FUNCIONARIO",
    "UsuarioAutenticado",
    "autenticar",
    "cadastrar_funcionario",
    "criar_conta_administrador",
    "criar_token_acesso",
    "decodificar_token",
    "dependencia_de_autorizacao",
    "gerar_hash_senha",
    "get_current_user",
    "montar_auth_token",
    "require_role",
    "somente_administrador",
    "verificar_senha",
]

# Perfis do domínio — exatamente os dois do contrato. Não existe ADMIN nem MEMBER.
PERFIL_ADMINISTRADOR: Final = "ADMINISTRADOR"
PERFIL_FUNCIONARIO: Final = "FUNCIONARIO"
PERFIS: Final = frozenset({PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO})

# ---------------------------------------------------------------------------
# Hash de senha — Argon2id (P4-01, P4-02)
# ---------------------------------------------------------------------------

# Parâmetros padrão do argon2-cffi (RFC 9106). Registrados aqui para auditoria: alterá-los
# exige nova aprovação humana, pois muda o custo de verificação de todas as senhas.
PARAMETROS_HASH: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        "time_cost": 3,
        "memory_cost": 65536,  # 64 MiB
        "parallelism": 4,
        "hash_len": 32,
        "salt_len": 16,
    }
)

# Senha de referência usada só para igualar o tempo de resposta quando o e-mail não existe
# (evita distinguir "e-mail inexistente" de "senha errada" pelo tempo da requisição).
_SENHA_DE_REFERENCIA: Final = "senha-inexistente-para-equalizar-tempo"


@lru_cache
def _hasher() -> PasswordHasher:
    """``PasswordHasher`` único do processo (Argon2id com ``PARAMETROS_HASH``)."""
    return PasswordHasher(**PARAMETROS_HASH)


@lru_cache
def _hash_de_referencia() -> str:
    return _hasher().hash(_SENHA_DE_REFERENCIA)


def gerar_hash_senha(senha: str) -> str:
    """Devolve o hash Argon2id (string PHC) da senha em texto puro."""
    try:
        return _hasher().hash(senha)
    except HashingError:
        # Falha de ambiente (ex.: memória insuficiente). Não vaza a senha.
        logger.exception("falha ao gerar hash de senha")
        raise


def verificar_senha(senha: str, senha_hash: str | None) -> bool:
    """Confere a senha contra o hash. ``False`` para senha errada **ou hash inválido**.

    Hash corrompido, vazio, de outro algoritmo ou ausente não levanta exceção nem expõe o
    motivo: o log registra apenas o tipo de falha, nunca a senha, o hash ou o usuário.
    """
    if not senha_hash:
        return False
    try:
        return _hasher().verify(senha_hash, senha)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        logger.warning("hash de senha armazenado em formato inválido; verificação recusada")
        return False
    except VerificationError:
        logger.warning("falha ao verificar hash de senha")
        return False
    except (ValueError, TypeError):
        # Hash fora do ASCII ou de tipo inesperado: a biblioteca levanta antes de analisar
        # o formato (ex.: UnicodeEncodeError, subclasse de ValueError).
        logger.warning("hash de senha armazenado em formato não suportado; verificação recusada")
        return False


def precisa_rehash(senha_hash: str) -> bool:
    """Indica se o hash foi gerado com parâmetros antigos e deve ser regravado."""
    try:
        return _hasher().check_needs_rehash(senha_hash)
    except (InvalidHashError, VerificationError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT — PyJWT/HS256 (P4-03, P4-04)
# ---------------------------------------------------------------------------

CLAIM_SUBJECT: Final = "sub"
CLAIM_PERFIL: Final = "perfil"
CLAIM_EMISSAO: Final = "iat"
CLAIM_EXPIRACAO: Final = "exp"


def criar_token_acesso(
    usuario: UsuarioModel, settings: Settings | None = None
) -> tuple[str, int]:
    """Emite o token do usuário. Devolve ``(token, expires_in_seconds)``.

    Claims estritamente necessários: ``sub`` (id), ``perfil``, ``iat`` e ``exp``. Nada de
    nome, e-mail, hash ou dados sensíveis dentro do token.
    """
    settings = settings or get_settings()
    expira_em = settings.jwt_access_token_expire_seconds
    emitido_em = datetime.now(UTC)
    payload: dict[str, Any] = {
        CLAIM_SUBJECT: str(usuario.id),
        CLAIM_PERFIL: usuario.perfil,
        CLAIM_EMISSAO: emitido_em,
        CLAIM_EXPIRACAO: emitido_em + timedelta(seconds=expira_em),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, expira_em


def decodificar_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Valida assinatura e expiração e devolve os claims. ``401`` se o token não servir."""
    settings = settings or get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": [CLAIM_SUBJECT, CLAIM_EXPIRACAO]},
        )
    except jwt.ExpiredSignatureError:
        raise NaoAutenticadoError("Token expirado.") from None
    except jwt.InvalidTokenError:
        # Assinatura inválida, algoritmo divergente, claim obrigatório ausente, etc.
        # A causa não é revelada ao cliente.
        raise NaoAutenticadoError() from None


def montar_auth_token(usuario: UsuarioModel, settings: Settings | None = None) -> AuthToken:
    """Monta o ``AuthToken`` do contrato (``tokenType`` = ``Bearer``)."""
    token, expira_em = criar_token_acesso(usuario, settings)
    return AuthToken(
        accessToken=token,
        tokenType="Bearer",
        expiresInSeconds=expira_em,
        usuario=Usuario.model_validate(usuario),
    )


# ---------------------------------------------------------------------------
# HTTP Bearer e identidade autenticada (P4-05)
# ---------------------------------------------------------------------------

# auto_error=False: o próprio projeto responde 401 no envelope ApiError, em vez do
# 403/{"detail": ...} que o HTTPBearer emitiria por conta própria.
_esquema_bearer = HTTPBearer(
    bearerFormat="JWT",
    description="Token de acesso emitido por /api/v1/auth/login.",
    auto_error=False,
)


def get_current_user(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> UsuarioModel:
    """Usuário autenticado pelo Bearer. ``401`` se o token ou a conta não servirem.

    Valida, em ordem: presença do cabeçalho, assinatura/expiração do token, formato do
    ``sub``, existência do usuário e estado ativo.
    """
    if credenciais is None or not credenciais.credentials:
        raise NaoAutenticadoError()

    claims = decodificar_token(credenciais.credentials)
    subject = claims.get(CLAIM_SUBJECT)
    try:
        usuario_id = int(str(subject))
    except (TypeError, ValueError):
        raise NaoAutenticadoError() from None

    usuario = db.get(UsuarioModel, usuario_id)
    if usuario is None or not usuario.ativo:
        # Conta removida, inexistente ou desativada depois da emissão do token.
        raise NaoAutenticadoError()
    return usuario


UsuarioAutenticado = Annotated[UsuarioModel, Depends(get_current_user)]


def require_role(*perfis: str) -> Callable[[UsuarioModel], UsuarioModel]:
    """Dependência que exige um dos ``perfis``. ``403`` para autenticado sem permissão.

    Use **somente** onde a descrição da operação no OpenAPI restringe o perfil.
    """
    desconhecidos = set(perfis) - PERFIS
    if desconhecidos:
        raise ValueError(f"perfis inexistentes no domínio: {sorted(desconhecidos)}")
    permitidos = frozenset(perfis)

    def _verificar_perfil(usuario: UsuarioAutenticado) -> UsuarioModel:
        if usuario.perfil not in permitidos:
            raise ProibidoError()
        return usuario

    return _verificar_perfil


somente_administrador = require_role(PERFIL_ADMINISTRADOR)
administrador_ou_funcionario = require_role(PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO)


# ---------------------------------------------------------------------------
# Matriz RBAC operação por operação (P4-06, P4-07)
# ---------------------------------------------------------------------------

# Chave: operationId do OpenAPI. Valor: perfis exigidos, ou...
#   ()        -> operação pública (sem Bearer);
#   None      -> exige Bearer, sem restrição de perfil (a descrição não restringe).
# Nenhuma restrição foi inventada: as de perfil vêm da descrição da operação.
MATRIZ_RBAC: Final[MappingProxyType[str, tuple[str, ...] | None]] = MappingProxyType(
    {
        # Públicas (security: [])
        "consultarSaude": (),
        "criarContaAdministrador": (),
        "autenticarUsuario": (),
        # "Restrito ao perfil ADMINISTRADOR" / "somente ADMINISTRADOR"
        "listarUsuarios": (PERFIL_ADMINISTRADOR,),
        "cadastrarFuncionario": (PERFIL_ADMINISTRADOR,),
        "consultarUsuario": (PERFIL_ADMINISTRADOR,),
        "atualizarUsuario": (PERFIL_ADMINISTRADOR,),
        "desativarUsuario": (PERFIL_ADMINISTRADOR,),
        "listarUnidadesMedida": (PERFIL_ADMINISTRADOR,),
        "cadastrarUnidadeMedida": (PERFIL_ADMINISTRADOR,),
        "consultarUnidadeMedida": (PERFIL_ADMINISTRADOR,),
        "atualizarUnidadeMedida": (PERFIL_ADMINISTRADOR,),
        "excluirUnidadeMedida": (PERFIL_ADMINISTRADOR,),
        "listarIngredientes": (PERFIL_ADMINISTRADOR,),
        "cadastrarIngrediente": (PERFIL_ADMINISTRADOR,),
        "consultarIngrediente": (PERFIL_ADMINISTRADOR,),
        "atualizarIngrediente": (PERFIL_ADMINISTRADOR,),
        "excluirIngrediente": (PERFIL_ADMINISTRADOR,),
        "listarProdutos": (PERFIL_ADMINISTRADOR,),
        "cadastrarProduto": (PERFIL_ADMINISTRADOR,),
        "consultarProduto": (PERFIL_ADMINISTRADOR,),
        "atualizarProduto": (PERFIL_ADMINISTRADOR,),
        "desativarProduto": (PERFIL_ADMINISTRADOR,),
        "consultarComposicaoProduto": (PERFIL_ADMINISTRADOR,),
        "substituirComposicaoProduto": (PERFIL_ADMINISTRADOR,),
        "calcularRecomendacaoProducao": (PERFIL_ADMINISTRADOR,),
        "calcularRecomendacaoReposicao": (PERFIL_ADMINISTRADOR,),
        "gerarSugestoesMarketing": (PERFIL_ADMINISTRADOR,),
        "consultarDashboard": (PERFIL_ADMINISTRADOR,),
        "exportarDashboardCsv": (PERFIL_ADMINISTRADOR,),
        # "Atores autorizados: ADMINISTRADOR e FUNCIONARIO"
        "listarClientes": (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO),
        "cadastrarCliente": (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO),
        "consultarCliente": (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO),
        "atualizarCliente": (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO),
        "excluirCliente": (PERFIL_ADMINISTRADOR, PERFIL_FUNCIONARIO),
        # Exigem Bearer; a descrição não restringe perfil -> nenhuma restrição inventada.
        "listarMovimentacoesDoIngrediente": None,
        "listarMovimentacoesEstoque": None,
        "registrarMovimentacaoEstoque": None,
        "listarPedidos": None,
        "registrarPedido": None,
        "consultarPedido": None,
        "cancelarPedido": None,
        "listarAlertasReposicao": None,
        "listarAlertasValidade": None,
    }
)


def dependencia_de_autorizacao(operation_id: str) -> Any:
    """Dependência de autorização da operação, conforme ``MATRIZ_RBAC``.

    Devolve ``None`` para operação pública (o router não adiciona dependência alguma),
    ``Depends(get_current_user)`` quando basta autenticação, ou ``Depends(require_role(...))``
    quando a operação restringe perfis. Usada pelos routers da Fase 5.
    """
    if operation_id not in MATRIZ_RBAC:
        raise KeyError(f"operação fora do contrato: {operation_id!r}")
    perfis = MATRIZ_RBAC[operation_id]
    if perfis == ():
        return None
    if perfis is None:
        return Depends(get_current_user)
    return Depends(require_role(*perfis))


# ---------------------------------------------------------------------------
# Fluxos de autenticação (P4-08, P4-09, P4-10)
#
# Regras de negócio das três operações contratuais de identidade. Nenhuma rota é criada
# aqui: os routers da Fase 5 (auth.py, usuarios.py) chamam estas funções.
# ---------------------------------------------------------------------------

# Mensagem única para qualquer falha de login: não revela se o e-mail existe nem se a
# conta está inativa.
_MSG_CREDENCIAIS: Final = "Credenciais inválidas ou conta inativa."


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def _contar_administradores(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(UsuarioModel)
            .where(UsuarioModel.perfil == PERFIL_ADMINISTRADOR)
        )
        or 0
    )


def existe_administrador(db: Session) -> bool:
    """Indica se o bootstrap do primeiro administrador já foi consumido."""
    return _contar_administradores(db) > 0


def criar_conta_administrador(db: Session, dto: CreateAdminDTO) -> UsuarioModel:
    """Bootstrap público do primeiro ``ADMINISTRADOR`` (``criarContaAdministrador``).

    Permitido somente enquanto não existir administrador; qualquer tentativa posterior
    resulta em ``409``. A verificação e a inserção ocorrem na mesma transação: após o
    ``flush`` (que toma a trava de escrita do SQLite) a contagem é refeita, de modo que
    duas tentativas concorrentes nunca produzam dois administradores.
    """
    if existe_administrador(db):
        raise ConflitoError("Já existe uma conta de administrador.")

    usuario = UsuarioModel(
        nome=dto.nome.strip(),
        email=_normalizar_email(dto.email),
        senha_hash=gerar_hash_senha(dto.senha),
        perfil=PERFIL_ADMINISTRADOR,
        ativo=True,
    )
    db.add(usuario)
    try:
        db.flush()
        if _contar_administradores(db) != 1:
            db.rollback()
            raise ConflitoError("Já existe uma conta de administrador.")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflitoError("E-mail já cadastrado.") from None
    db.refresh(usuario)
    logger.info("bootstrap de administrador concluído (id=%s)", usuario.id)
    return usuario


def cadastrar_funcionario(db: Session, dto: CreateFuncionarioDTO) -> UsuarioModel:
    """Cadastro comum (``cadastrarFuncionario``): o perfil é **sempre** ``FUNCIONARIO``.

    O DTO do contrato não possui campo de perfil; o servidor o define e nunca aceita
    perfil escolhido pelo cliente.
    """
    usuario = UsuarioModel(
        nome=dto.nome.strip(),
        email=_normalizar_email(dto.email),
        senha_hash=gerar_hash_senha(dto.senha),
        perfil=PERFIL_FUNCIONARIO,
        ativo=True,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflitoError("E-mail já cadastrado.") from None
    db.refresh(usuario)
    return usuario


def autenticar(db: Session, dto: LoginDTO) -> UsuarioModel:
    """Login público (``autenticarUsuario``): valida credenciais e conta ativa.

    ``401`` com a mesma mensagem para e-mail inexistente, senha errada ou conta inativa.
    Quando o e-mail não existe, uma verificação de referência é executada para que o
    tempo de resposta não revele a ausência do cadastro.
    """
    usuario = db.scalar(
        select(UsuarioModel).where(UsuarioModel.email == _normalizar_email(dto.email))
    )
    if usuario is None:
        verificar_senha(dto.senha, _hash_de_referencia())
        raise NaoAutenticadoError(_MSG_CREDENCIAIS)

    if not verificar_senha(dto.senha, usuario.senha_hash):
        raise NaoAutenticadoError(_MSG_CREDENCIAIS)

    if not usuario.ativo:
        raise NaoAutenticadoError(_MSG_CREDENCIAIS)

    if precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = gerar_hash_senha(dto.senha)
        db.commit()
        db.refresh(usuario)

    return usuario
