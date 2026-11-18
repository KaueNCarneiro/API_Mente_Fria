"""Service de ingredientes (Fase 5 — P5-02).

Cobre `listarIngredientes`, `cadastrarIngrediente`, `consultarIngrediente`,
`atualizarIngrediente` e `excluirIngrediente`.

Regras do SPEC §6.3: o ingrediente nasce com **estoque zero** (nenhuma movimentação é
criada no cadastro); o saldo é derivado dos lotes e **não** é editável pelo `PUT`;
ingrediente com composição ou histórico de movimentação não pode ser excluído.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..exceptions import ConflitoError, NaoEncontradoError
from ..models import (
    ComposicaoProdutoModel,
    IngredienteModel,
    MovimentacaoEstoqueModel,
    UnidadeMedidaModel,
)
from ..schemas import CreateIngredienteDTO, UpdateIngredienteDTO
from .comum import Pagina, aplicar_ordenacao, paginar, termo_de_busca

ORDENACAO_PERMITIDA = {
    "id": IngredienteModel.id,
    "nome": IngredienteModel.nome,
    "unidadeMedida": IngredienteModel.unidadeMedida,
    "custoUnitario": IngredienteModel.custoUnitario,
    "porcaoPadrao": IngredienteModel.porcaoPadrao,
    "quantidadeMinima": IngredienteModel.quantidadeMinima,
}


def _exigir_unidade(db: Session, unidade_medida: str) -> None:
    """Unidade inexistente resulta em `404` (status declarado no cadastro/atualização)."""
    if db.get(UnidadeMedidaModel, unidade_medida) is None:
        raise NaoEncontradoError("Unidade de medida não encontrada.")


def listar(
    db: Session,
    *,
    page: int,
    size: int,
    sort: str | None = None,
    q: str | None = None,
    unidade_medida: str | None = None,
    precisa_reposicao: bool | None = None,
) -> Pagina[IngredienteModel]:
    """Lista ingredientes com os filtros declarados nesta operação.

    `precisaReposicao` é derivado (saldo válido abaixo do mínimo), então o filtro é
    aplicado na própria consulta pela expressão `saldoValido`, sem carregar tudo.
    """
    stmt = select(IngredienteModel)
    termo = termo_de_busca(q)
    if termo is not None:
        stmt = stmt.where(IngredienteModel.nome.ilike(termo, escape="\\"))
    if unidade_medida is not None:
        stmt = stmt.where(IngredienteModel.unidadeMedida == unidade_medida)
    if precisa_reposicao is not None:
        condicao = IngredienteModel.saldoValido < IngredienteModel.quantidadeMinima
        stmt = stmt.where(condicao if precisa_reposicao else ~condicao)
    stmt = aplicar_ordenacao(stmt, sort, ORDENACAO_PERMITIDA, padrao=IngredienteModel.id)
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, ingrediente_id: int) -> IngredienteModel:
    ingrediente = db.get(IngredienteModel, ingrediente_id)
    if ingrediente is None:
        raise NaoEncontradoError("Ingrediente não encontrado.")
    return ingrediente


def cadastrar(db: Session, dto: CreateIngredienteDTO) -> IngredienteModel:
    """Cadastra o ingrediente com estoque zero (sem movimentação inicial)."""
    _exigir_unidade(db, dto.unidadeMedida)
    ingrediente = IngredienteModel(
        nome=dto.nome.strip(),
        unidadeMedida=dto.unidadeMedida,
        custoUnitario=dto.custoUnitario,
        porcaoPadrao=dto.porcaoPadrao,
        quantidadeMinima=dto.quantidadeMinima if dto.quantidadeMinima is not None else Decimal(0),
    )
    db.add(ingrediente)
    db.commit()
    db.refresh(ingrediente)
    return ingrediente


def atualizar(db: Session, ingrediente_id: int, dto: UpdateIngredienteDTO) -> IngredienteModel:
    """Atualiza os dados cadastrais. O saldo **não** é tocado: ele deriva dos lotes."""
    ingrediente = obter(db, ingrediente_id)
    _exigir_unidade(db, dto.unidadeMedida)
    ingrediente.nome = dto.nome.strip()
    ingrediente.unidadeMedida = dto.unidadeMedida
    ingrediente.custoUnitario = dto.custoUnitario
    ingrediente.porcaoPadrao = dto.porcaoPadrao
    ingrediente.quantidadeMinima = dto.quantidadeMinima
    db.commit()
    db.refresh(ingrediente)
    return ingrediente


def excluir(db: Session, ingrediente_id: int) -> None:
    """Exclui o ingrediente; `409` se houver composição ou histórico de movimentação."""
    ingrediente = obter(db, ingrediente_id)
    em_composicao = db.scalar(
        select(exists().where(ComposicaoProdutoModel.ingredienteId == ingrediente_id))
    )
    if em_composicao:
        raise ConflitoError("Ingrediente faz parte da composição de produtos.")
    tem_movimentacao = db.scalar(
        select(exists().where(MovimentacaoEstoqueModel.ingredienteId == ingrediente_id))
    )
    if tem_movimentacao:
        raise ConflitoError("Ingrediente possui histórico de movimentações de estoque.")
    db.delete(ingrediente)
    db.commit()
