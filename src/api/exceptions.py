"""Exceções de domínio e handlers globais do envelope ``ApiError`` (Fase 4 — P4-11 a P4-17).

O formato de erro é **próprio do contrato** (``components.schemas.ApiError``):
``codigo``, ``mensagem``, ``detalhes``, ``timestamp``, ``caminho`` e ``correlationId``.
Não é RFC 9457/Problem Details e não é o ``{"detail": "..."}`` padrão do FastAPI.

Decisões registradas no PLAN.md (Fase 4):

- **Códigos (``codigo``):** o contrato define ``codigo`` como string livre (até 80) e só
  exemplifica ``VALIDATION_ERROR``. Adotamos um código estável por status, nomeado como o
  componente de resposta correspondente do OpenAPI (``BadRequest`` → ``BAD_REQUEST``, etc.).
- **400 x 422:** o contrato distingue *requisição malformada ou parâmetros incompatíveis*
  (400) de *dados compreendidos que violam validação* (422). A classificação é feita pela
  origem do erro (corpo ilegível / parâmetro / campo do corpo) e o status final só é usado
  se a operação o declarar — nunca se converte tudo em 400 nem tudo em 422.
- **Sigilo:** nenhuma mensagem, detalhe ou log carrega senha, hash, token, segredo, SQL ou
  stack trace. ``valorRejeitado`` só aparece para valores escalares de campos não sensíveis.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from http import HTTPStatus
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import redact
from .models import agora
from .schemas import ApiError, ApiErrorDetail

logger = logging.getLogger(__name__)

__all__ = [
    "ApiException",
    "ConflitoError",
    "DependenciaIndisponivelError",
    "NaoAutenticadoError",
    "NaoEncontradoError",
    "ProibidoError",
    "RequisicaoInvalidaError",
    "ValidacaoError",
    "construir_api_error",
    "registrar_handlers",
    "resposta_sem_conteudo",
]

# ---------------------------------------------------------------------------
# Limites do schema ApiError / ApiErrorDetail (OpenAPI)
# ---------------------------------------------------------------------------

MAX_CODIGO: Final = 80
MAX_MENSAGEM: Final = 500
MAX_CAMINHO: Final = 300
MAX_CAMPO: Final = 100
MAX_VALOR_REJEITADO: Final = 500
MAX_CORRELATION_ID: Final = 100

# Códigos estáveis, um por componente de resposta do contrato.
CODIGO_BAD_REQUEST: Final = "BAD_REQUEST"
CODIGO_UNAUTHORIZED: Final = "UNAUTHORIZED"
CODIGO_FORBIDDEN: Final = "FORBIDDEN"
CODIGO_NOT_FOUND: Final = "NOT_FOUND"
CODIGO_CONFLICT: Final = "CONFLICT"
CODIGO_VALIDATION_ERROR: Final = "VALIDATION_ERROR"
CODIGO_INTERNAL_ERROR: Final = "INTERNAL_ERROR"
CODIGO_SERVICE_UNAVAILABLE: Final = "SERVICE_UNAVAILABLE"

# Mensagens padrão espelhando `description` de components.responses do OpenAPI.
_MENSAGEM_PADRAO: Final[dict[int, str]] = {
    400: "Requisição malformada ou parâmetros incompatíveis.",
    401: "Autenticação ausente, inválida ou expirada.",
    403: "Usuário autenticado sem permissão para a operação.",
    404: "Recurso não encontrado.",
    409: "Conflito com o estado atual ou restrição de integridade referencial.",
    422: "Os dados foram compreendidos, mas violam uma regra de validação.",
    500: "Erro interno inesperado.",
    503: "Serviço de otimização ou dependência temporariamente indisponível.",
}

_CODIGO_PADRAO: Final[dict[int, str]] = {
    400: CODIGO_BAD_REQUEST,
    401: CODIGO_UNAUTHORIZED,
    403: CODIGO_FORBIDDEN,
    404: CODIGO_NOT_FOUND,
    409: CODIGO_CONFLICT,
    422: CODIGO_VALIDATION_ERROR,
    500: CODIGO_INTERNAL_ERROR,
    503: CODIGO_SERVICE_UNAVAILABLE,
}

# Nomes de campo cujo valor nunca é ecoado em `valorRejeitado`.
_CAMPOS_SENSIVEIS: Final = (
    "senha",
    "senha_hash",
    "password",
    "passwd",
    "token",
    "accesstoken",
    "access_token",
    "secret",
    "authorization",
    "hash",
)


def _truncar(texto: str, limite: int) -> str:
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _campo_sensivel(campo: str) -> bool:
    alvo = campo.lower()
    return any(chave in alvo for chave in _CAMPOS_SENSIVEIS)


# ---------------------------------------------------------------------------
# Exceções de domínio (P4-11)
# ---------------------------------------------------------------------------


class ApiException(Exception):
    """Base das exceções de domínio: carrega status, ``codigo`` e ``detalhes`` do contrato.

    Serializada pelo handler global no envelope ``ApiError``. As subclasses existem para
    os status declarados no OpenAPI; nenhuma inventa status novo.
    """

    status_code: int = 500
    codigo: str = CODIGO_INTERNAL_ERROR

    def __init__(
        self,
        mensagem: str | None = None,
        *,
        detalhes: Sequence[ApiErrorDetail] | None = None,
        codigo: str | None = None,
    ) -> None:
        self.mensagem = _truncar(
            mensagem or _MENSAGEM_PADRAO.get(self.status_code, "Erro interno inesperado."),
            MAX_MENSAGEM,
        )
        self.detalhes: list[ApiErrorDetail] = list(detalhes or ())
        if codigo is not None:
            self.codigo = _truncar(codigo, MAX_CODIGO)
        super().__init__(self.mensagem)


class RequisicaoInvalidaError(ApiException):
    """400 — requisição malformada ou parâmetros incompatíveis."""

    status_code = 400
    codigo = CODIGO_BAD_REQUEST


class NaoAutenticadoError(ApiException):
    """401 — autenticação ausente, inválida ou expirada (inclui conta inativa no login)."""

    status_code = 401
    codigo = CODIGO_UNAUTHORIZED


class ProibidoError(ApiException):
    """403 — autenticado, porém sem o perfil exigido pela operação."""

    status_code = 403
    codigo = CODIGO_FORBIDDEN


class NaoEncontradoError(ApiException):
    """404 — recurso inexistente."""

    status_code = 404
    codigo = CODIGO_NOT_FOUND


class ConflitoError(ApiException):
    """409 — conflito de estado ou integridade referencial (ex.: e-mail já cadastrado)."""

    status_code = 409
    codigo = CODIGO_CONFLICT


class ValidacaoError(ApiException):
    """422 — dados compreendidos que violam regra de validação de negócio."""

    status_code = 422
    codigo = CODIGO_VALIDATION_ERROR


class DependenciaIndisponivelError(ApiException):
    """503 — indisponibilidade temporária de dependência (ex.: solver de otimização)."""

    status_code = 503
    codigo = CODIGO_SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Construção do envelope (P4-16)
# ---------------------------------------------------------------------------


def construir_api_error(
    *,
    status_code: int,
    caminho: str,
    codigo: str | None = None,
    mensagem: str | None = None,
    detalhes: Iterable[ApiErrorDetail] | None = None,
    correlation_id: str | None = None,
) -> ApiError:
    """Monta um ``ApiError`` válido para o contrato, com ``timestamp`` e ``caminho``."""
    return ApiError(
        codigo=_truncar(codigo or _CODIGO_PADRAO.get(status_code, CODIGO_INTERNAL_ERROR), MAX_CODIGO),
        mensagem=_truncar(
            mensagem or _MENSAGEM_PADRAO.get(status_code, "Erro interno inesperado."),
            MAX_MENSAGEM,
        ),
        detalhes=list(detalhes or ()),
        timestamp=agora(),
        caminho=_truncar(caminho, MAX_CAMINHO),
        correlationId=_truncar(correlation_id or str(uuid.uuid4()), MAX_CORRELATION_ID),
    )


def _resposta_erro(request: Request, erro: ApiError, status_code: int) -> JSONResponse:
    """Serializa o envelope. ``204`` nunca passa por aqui (P4-17)."""
    return JSONResponse(status_code=status_code, content=erro.model_dump(mode="json"))


def resposta_sem_conteudo() -> Response:
    """Resposta ``204`` sem corpo e sem schema JSON (P4-17).

    Usada pelas operações que declaram 204 (``desativarUsuario``, ``excluirCliente``,
    ``excluirUnidadeMedida``, ``excluirIngrediente``, ``desativarProduto``). Devolve
    ``Response`` cru: nada é serializado e nenhum ``Content-Type`` de JSON é emitido.
    """
    return Response(status_code=HTTPStatus.NO_CONTENT)


def _caminho(request: Request) -> str:
    return request.url.path


# ---------------------------------------------------------------------------
# Classificação 400 x 422 (P4-13, P4-14)
# ---------------------------------------------------------------------------

_ORIGEM_CORPO_MALFORMADO: Final = "corpo_malformado"
_ORIGEM_PARAMETRO_DE_CAMINHO: Final = "parametro_de_caminho"
_ORIGEM_PARAMETRO_DE_CONSULTA: Final = "parametro_de_consulta"
_ORIGEM_CAMPO_DO_CORPO: Final = "campo_do_corpo"

# Status candidatos por origem, em ordem de precisão. Usa-se o PRIMEIRO que a operação
# declarar; nenhum status é emitido por preferência estética.
#
# `parametro_de_caminho` admite 404 como terceira opção: um identificador que viola o
# próprio contrato (ex.: `id=0` contra `minimum: 1`) não pode designar recurso algum, e
# "Recurso não encontrado" é a resposta declarada nas 13 operações de leitura/exclusão por
# id que não declaram 400 nem 422. Preferir um status declarado a emitir um status fora do
# contrato — ver "Decisão sobre parâmetros sem 400/422" no PLAN.md.
_CANDIDATOS: Final[dict[str, tuple[int, ...]]] = {
    _ORIGEM_CORPO_MALFORMADO: (400, 422),
    _ORIGEM_PARAMETRO_DE_CAMINHO: (400, 404, 422),
    _ORIGEM_PARAMETRO_DE_CONSULTA: (400, 422),
    _ORIGEM_CAMPO_DO_CORPO: (422, 400),
}

# Status usado quando a operação não declara nenhum dos candidatos (gap de contrato).
_STATUS_PADRAO_DE_VALIDACAO: Final = 422

_LOCAIS_DE_PARAMETRO: Final = frozenset({"query", "path", "header", "cookie"})
_TIPOS_CORPO_ILEGIVEL: Final = frozenset(
    {"json_invalid", "json_type", "model_attributes_type", "dataclass_type"}
)


def _statuses_declarados(request: Request) -> frozenset[int]:
    """Status declarados pela operação correspondente (rota do FastAPI).

    Na Fase 4 ainda não há routers; sem rota casada, devolve conjunto vazio e a
    classificação cai no padrão documentado.
    """
    rota = request.scope.get("route")
    if rota is None:
        return frozenset()
    declarados: set[int] = set()
    principal = getattr(rota, "status_code", None)
    if isinstance(principal, int):
        declarados.add(principal)
    for chave in getattr(rota, "responses", {}) or {}:
        try:
            declarados.add(int(chave))
        except (TypeError, ValueError):
            continue
    return frozenset(declarados)


def _classificar_origem(erros: Sequence[dict[str, Any]]) -> str:
    """Origem predominante: corpo ilegível > caminho > consulta > campo do corpo.

    O parâmetro de caminho vem antes do de consulta porque identifica o recurso: se ele é
    inválido, nada mais na requisição importa.
    """
    tem_caminho = False
    tem_consulta = False
    for erro in erros:
        loc = tuple(erro.get("loc") or ())
        tipo = str(erro.get("type") or "")
        if tipo in _TIPOS_CORPO_ILEGIVEL:
            return _ORIGEM_CORPO_MALFORMADO
        if loc == ("body",) and tipo == "missing":
            return _ORIGEM_CORPO_MALFORMADO
        if not loc:
            continue
        local = str(loc[0])
        if local == "path":
            tem_caminho = True
        elif local in _LOCAIS_DE_PARAMETRO:
            tem_consulta = True
    if tem_caminho:
        return _ORIGEM_PARAMETRO_DE_CAMINHO
    return _ORIGEM_PARAMETRO_DE_CONSULTA if tem_consulta else _ORIGEM_CAMPO_DO_CORPO


def _status_de_validacao(request: Request, origem: str) -> int:
    """Status final conforme a origem e o que a operação declara (P4-14).

    Percorre os candidatos da origem em ordem de precisão e devolve o primeiro que a
    operação declarar. Se nenhum for declarado, usa 422 e registra o gap em log.
    """
    declarados = _statuses_declarados(request)
    for candidato in _CANDIDATOS[origem]:
        if candidato in declarados:
            return candidato
    if declarados:
        logger.warning(
            "operação %s %s não declara nenhum status para erro de validação de origem=%s "
            "(candidatos: %s); usando %d — divergência registrada no PLAN.md",
            request.method,
            _caminho(request),
            origem,
            _CANDIDATOS[origem],
            _STATUS_PADRAO_DE_VALIDACAO,
        )
    return _STATUS_PADRAO_DE_VALIDACAO


def _detalhe_de_erro(erro: dict[str, Any]) -> ApiErrorDetail:
    """Converte um erro do Pydantic/FastAPI em ``ApiErrorDetail`` sem vazar dados."""
    loc = tuple(erro.get("loc") or ())
    partes = [str(parte) for parte in (loc[1:] if len(loc) > 1 else loc)]
    campo = _truncar(".".join(partes) or "requisição", MAX_CAMPO)

    mensagem = _truncar(redact(str(erro.get("msg") or "Valor inválido.")), MAX_MENSAGEM)

    valor_rejeitado: str | None = None
    entrada = erro.get("input")
    # Só valores escalares e campos não sensíveis: um dict/list poderia conter a senha.
    if not _campo_sensivel(campo) and isinstance(entrada, str | int | float | bool):
        valor_rejeitado = _truncar(redact(str(entrada)), MAX_VALOR_REJEITADO)

    return ApiErrorDetail(campo=campo, mensagem=mensagem, valorRejeitado=valor_rejeitado)


# ---------------------------------------------------------------------------
# Handlers globais (P4-12)
# ---------------------------------------------------------------------------


async def api_exception_handler(request: Request, exc: ApiException) -> Response:
    """Exceções de domínio → ``ApiError`` com o status da própria exceção."""
    erro = construir_api_error(
        status_code=exc.status_code,
        caminho=_caminho(request),
        codigo=exc.codigo,
        mensagem=exc.mensagem,
        detalhes=exc.detalhes,
    )
    logger.info(
        "%s %s -> %d %s (correlationId=%s)",
        request.method,
        erro.caminho,
        exc.status_code,
        erro.codigo,
        erro.correlationId,
    )
    return _resposta_erro(request, erro, exc.status_code)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Validação do FastAPI/Pydantic → ``ApiError`` 422 (ou 400, conforme a operação)."""
    erros = list(exc.errors())
    origem = _classificar_origem(erros)
    status_code = _status_de_validacao(request, origem)

    if origem == _ORIGEM_CORPO_MALFORMADO:
        detalhes = [
            ApiErrorDetail(
                campo="corpo",
                mensagem="Corpo da requisição ausente ou ilegível; envie JSON válido.",
            )
        ]
    else:
        detalhes = [_detalhe_de_erro(erro) for erro in erros]

    erro = construir_api_error(
        status_code=status_code, caminho=_caminho(request), detalhes=detalhes
    )
    logger.info(
        "%s %s -> %d %s origem=%s campos=%s (correlationId=%s)",
        request.method,
        erro.caminho,
        status_code,
        erro.codigo,
        origem,
        [detalhe.campo for detalhe in detalhes],
        erro.correlationId,
    )
    return _resposta_erro(request, erro, status_code)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """``HTTPException`` do framework (404 de rota, 405, etc.) → ``ApiError``."""
    status_code = exc.status_code
    if status_code == HTTPStatus.NO_CONTENT:  # 204 nunca tem corpo (P4-17)
        return Response(status_code=status_code)

    detalhe = exc.detail
    mensagem = _MENSAGEM_PADRAO.get(status_code)
    if isinstance(detalhe, str) and detalhe and detalhe != HTTPStatus(status_code).phrase:
        mensagem = redact(detalhe)

    erro = construir_api_error(
        status_code=status_code, caminho=_caminho(request), mensagem=mensagem
    )
    logger.info(
        "%s %s -> %d %s (correlationId=%s)",
        request.method,
        erro.caminho,
        status_code,
        erro.codigo,
        erro.correlationId,
    )
    return _resposta_erro(request, erro, status_code)


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Qualquer exceção não tratada → 500 ``ApiError``, sem stack trace na resposta.

    O diagnóstico vai para o log (com ``correlationId``) já filtrado por
    ``RedactingFilter``; o cliente recebe apenas a mensagem genérica do contrato.
    """
    erro = construir_api_error(status_code=500, caminho=_caminho(request))
    logger.exception(
        "erro não tratado em %s %s (correlationId=%s)",
        request.method,
        erro.caminho,
        erro.correlationId,
    )
    return _resposta_erro(request, erro, 500)


def registrar_handlers(app: FastAPI) -> None:
    """Registra os handlers globais na aplicação (chamado por ``main.create_app``)."""
    # Os handlers declaram o tipo concreto que tratam; a assinatura esperada pelo
    # Starlette é (Request, Exception), daí os ignores de tipo.
    app.add_exception_handler(ApiException, api_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(ResponseValidationError, unhandled_exception_handler)
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
