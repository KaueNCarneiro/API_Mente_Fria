"""Service de unidades de medida (Fase 5 — P5-02).

Cobre `listarUnidadesMedida`, `cadastrarUnidadeMedida`, `consultarUnidadeMedida`,
`atualizarUnidadeMedida` e `excluirUnidadeMedida`.

Regras do SPEC §6.2: `porcaoPadrao` é sugestão para **novos** ingredientes — atualizá-la
não recalcula os existentes; unidade referenciada por ingrediente não pode ser excluída.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..exceptions import ConflitoError, NaoEncontradoError
from ..models import IngredienteModel, UnidadeMedidaModel
from ..schemas import CreateUnidadeMedidaDTO, UpdateUnidadeMedidaDTO
from .comum import Pagina, aplicar_ordenacao, paginar

ORDENACAO_PERMITIDA = {
    "unidadeMedida": UnidadeMedidaModel.unidadeMedida,
    "porcaoPadrao": UnidadeMedidaModel.porcaoPadrao,
}


def listar(db: Session, *, page: int, size: int, sort: str | None = None) -> Pagina[UnidadeMedidaModel]:
    """Lista unidades. Esta operação não declara o parâmetro `q` no contrato."""
    stmt = aplicar_ordenacao(
        select(UnidadeMedidaModel), sort, ORDENACAO_PERMITIDA, padrao=UnidadeMedidaModel.unidadeMedida
    )
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, unidade_medida: str) -> UnidadeMedidaModel:
    unidade = db.get(UnidadeMedidaModel, unidade_medida)
    if unidade is None:
        raise NaoEncontradoError("Unidade de medida não encontrada.")
    return unidade


def cadastrar(db: Session, dto: CreateUnidadeMedidaDTO) -> UnidadeMedidaModel:
    """Cria a unidade; chave repetida resulta em `409`."""
    if db.get(UnidadeMedidaModel, dto.unidadeMedida) is not None:
        raise ConflitoError("Unidade de medida já cadastrada.")
    unidade = UnidadeMedidaModel(unidadeMedida=dto.unidadeMedida, porcaoPadrao=dto.porcaoPadrao)
    db.add(unidade)
    db.commit()
    db.refresh(unidade)
    return unidade


def atualizar(
    db: Session, unidade_medida: str, dto: UpdateUnidadeMedidaDTO
) -> UnidadeMedidaModel:
    """Atualiza somente `porcaoPadrao`; ingredientes já cadastrados não são recalculados."""
    unidade = obter(db, unidade_medida)
    unidade.porcaoPadrao = dto.porcaoPadrao
    db.commit()
    db.refresh(unidade)
    return unidade


def excluir(db: Session, unidade_medida: str) -> None:
    """Exclui a unidade; `409` quando houver ingrediente vinculado."""
    unidade = obter(db, unidade_medida)
    em_uso = db.scalar(
        select(exists().where(IngredienteModel.unidadeMedida == unidade_medida))
    )
    if em_uso:
        raise ConflitoError("Unidade de medida em uso por ingredientes e não pode ser excluída.")
    db.delete(unidade)
    db.commit()
