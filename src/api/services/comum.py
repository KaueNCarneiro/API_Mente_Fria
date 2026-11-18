"""Utilidades compartilhadas pelos services (Fase 5 — P5-01, P5-17, P5-18, P5-19).

Reúne o que todas as consultas de lista precisam: paginação conforme o contrato
(`page`/`size`/`totalElements`/`totalPages`), ordenação `campo,direção` com lista
permitida por recurso e validação de intervalo de datas.

Regras:
- **Nada de SQL interpolado:** `sort` é resolvido contra um mapa de colunas permitidas por
  recurso; campo fora do mapa é recusado, nunca repassado ao banco.
- **Sem filtro global:** cada operação declara os próprios parâmetros; estas funções são
  blocos de montagem, não um filtro aplicado a todos os recursos.
- **Regras de negócio ficam nos services; HTTP fica nos routers.** Este módulo não importa
  nada de `fastapi`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from ..exceptions import RequisicaoInvalidaError
from ..schemas import ApiErrorDetail, PageMetadata

T = TypeVar("T")

# Limites de paginação do contrato (components.parameters Page/Size).
PAGE_MINIMO = 0
PAGE_PADRAO = 0
SIZE_MINIMO = 1
SIZE_MAXIMO = 100
SIZE_PADRAO = 20

_DIRECOES = {"asc", "desc"}


@dataclass(frozen=True, slots=True)
class Pagina[TItem]:
    """Resultado paginado: itens da página e os metadados do contrato."""

    itens: Sequence[TItem]
    paginacao: PageMetadata


def _detalhe(campo: str, mensagem: str, valor: object | None = None) -> list[ApiErrorDetail]:
    return [
        ApiErrorDetail(
            campo=campo,
            mensagem=mensagem,
            valorRejeitado=None if valor is None else str(valor)[:500],
        )
    ]


def aplicar_ordenacao(
    stmt: Select[Any],
    sort: str | None,
    permitidos: Mapping[str, InstrumentedAttribute[Any]],
    *,
    padrao: InstrumentedAttribute[Any],
) -> Select[Any]:
    """Aplica `sort` no formato ``campo,direção``; sem `sort`, ordena por ``padrao``.

    ``permitidos`` mapeia o nome do campo **como aparece no JSON do contrato** para a
    coluna do ORM. Campo desconhecido ou direção inválida resultam em ``400``, porque o
    contrato descreve o status 400 como "parâmetros incompatíveis".
    """
    if not sort or not sort.strip():
        return stmt.order_by(padrao.asc())

    partes = [parte.strip() for parte in sort.split(",")]
    campo = partes[0]
    direcao = (partes[1].lower() if len(partes) > 1 else "asc")

    if len(partes) > 2:
        raise RequisicaoInvalidaError(
            "O parâmetro sort usa o formato campo,direção.",
            detalhes=_detalhe("sort", "Formato esperado: campo,direção.", sort),
        )
    if campo not in permitidos:
        raise RequisicaoInvalidaError(
            "Campo de ordenação não suportado por este recurso.",
            detalhes=_detalhe(
                "sort",
                f"Campos aceitos: {', '.join(sorted(permitidos))}.",
                campo,
            ),
        )
    if direcao not in _DIRECOES:
        raise RequisicaoInvalidaError(
            "Direção de ordenação inválida.",
            detalhes=_detalhe("sort", "Use asc ou desc.", direcao),
        )

    coluna = permitidos[campo]
    return stmt.order_by(coluna.desc() if direcao == "desc" else coluna.asc())


def paginar(db: Session, stmt: Select[tuple[T]], *, page: int, size: int) -> Pagina[T]:
    """Conta o total e devolve a página pedida, com os metadados do contrato.

    A contagem usa a mesma consulta sem ordenação (`order_by(None)`), de modo que filtros
    e junções valham também para `totalElements`.
    """
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    itens = list(db.scalars(stmt.offset(page * size).limit(size)).unique().all())
    return Pagina(
        itens=itens,
        paginacao=PageMetadata(
            page=page,
            size=size,
            totalElements=total,
            totalPages=ceil(total / size) if size else 0,
        ),
    )


def validar_intervalo(data_inicio: date | None, data_fim: date | None) -> None:
    """Recusa ``dataFim`` anterior a ``dataInicio`` com ``400``."""
    if data_inicio is not None and data_fim is not None and data_fim < data_inicio:
        raise RequisicaoInvalidaError(
            "dataFim não pode ser anterior a dataInicio.",
            detalhes=[
                ApiErrorDetail(
                    campo="dataFim",
                    mensagem=f"Deve ser igual ou posterior a dataInicio ({data_inicio.isoformat()}).",
                    valorRejeitado=data_fim.isoformat(),
                )
            ],
        )


def termo_de_busca(q: str | None) -> str | None:
    """Converte `q` no padrão ``LIKE`` correspondente, ou ``None`` quando vazio.

    Escapa os curingas do próprio ``LIKE`` para que `%` e `_` digitados pelo usuário
    sejam tratados como texto literal.
    """
    if q is None:
        return None
    termo = q.strip()
    if not termo:
        return None
    termo = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{termo}%"
