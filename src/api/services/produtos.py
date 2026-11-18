"""Service de produtos e composição (Fase 5 — P5-02).

Cobre `listarProdutos`, `cadastrarProduto`, `consultarProduto`, `atualizarProduto`,
`desativarProduto`, `consultarComposicaoProduto` e `substituirComposicaoProduto`.

Regras do SPEC §6.4: a composição exige ao menos um ingrediente existente com quantidade
positiva; a atualização comercial **não** reescreve preços já registrados em pedidos;
`DELETE` é desativação lógica; a substituição de composição é integral.

Carregamento: a composição é retornada junto do produto em todas as respostas, então as
consultas usam `selectinload` até o ingrediente — `ComposicaoProdutoItem` expõe
`nomeIngrediente` e `unidadeMedida`, que vêm dele (P5-19, sem N+1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from ..exceptions import NaoEncontradoError, ValidacaoError
from ..models import (
    ComposicaoProdutoModel,
    IngredienteModel,
    PedidoItemModel,
    ProdutoModel,
)
from ..schemas import (
    ApiErrorDetail,
    ComposicaoProdutoItemDTO,
    CreateProdutoDTO,
    SubstituirComposicaoDTO,
    UpdateProdutoDTO,
)
from .comum import Pagina, aplicar_ordenacao, paginar, termo_de_busca

ORDENACAO_PERMITIDA = {
    "id": ProdutoModel.id,
    "nome": ProdutoModel.nome,
    "precoVenda": ProdutoModel.precoVenda,
    "ativo": ProdutoModel.ativo,
}


def _com_composicao(stmt: Select[tuple[ProdutoModel]]) -> Select[tuple[ProdutoModel]]:
    """Carrega composição e ingrediente em lote (evita N+1 ao serializar `Produto`)."""
    return stmt.options(
        selectinload(ProdutoModel.composicao).joinedload(ComposicaoProdutoModel.ingrediente)
    )


def _validar_itens(
    db: Session, itens: Sequence[ComposicaoProdutoItemDTO]
) -> list[ComposicaoProdutoModel]:
    """Valida a composição recebida e devolve as linhas do ORM correspondentes.

    - composição vazia -> `422` (o produto exige ao menos um ingrediente);
    - ingrediente repetido -> `422` (a chave composta do modelo também o impede);
    - ingrediente inexistente -> `404` (status declarado nestas operações).

    As quantidades positivas já são garantidas pelo schema (`minimum: 0.001`).
    """
    if not itens:
        raise ValidacaoError(
            "A composição deve conter ao menos um ingrediente.",
            detalhes=[ApiErrorDetail(campo="composicao", mensagem="Informe ao menos um item.")],
        )

    contagem = Counter(item.ingredienteId for item in itens)
    duplicados = sorted(ingrediente_id for ingrediente_id, n in contagem.items() if n > 1)
    if duplicados:
        raise ValidacaoError(
            "A composição não pode repetir o mesmo ingrediente.",
            detalhes=[
                ApiErrorDetail(
                    campo="composicao",
                    mensagem="Ingrediente repetido na composição.",
                    valorRejeitado=str(ingrediente_id),
                )
                for ingrediente_id in duplicados
            ],
        )

    linhas: list[ComposicaoProdutoModel] = []
    for item in itens:
        if db.get(IngredienteModel, item.ingredienteId) is None:
            raise NaoEncontradoError(f"Ingrediente {item.ingredienteId} não encontrado.")
        linhas.append(
            ComposicaoProdutoModel(
                ingredienteId=item.ingredienteId, quantidadeUtilizada=item.quantidadeUtilizada
            )
        )
    return linhas


def listar(
    db: Session,
    *,
    page: int,
    size: int,
    sort: str | None = None,
    q: str | None = None,
    ativo: bool | None = None,
) -> Pagina[ProdutoModel]:
    stmt = _com_composicao(select(ProdutoModel))
    termo = termo_de_busca(q)
    if termo is not None:
        stmt = stmt.where(ProdutoModel.nome.ilike(termo, escape="\\"))
    if ativo is not None:
        stmt = stmt.where(ProdutoModel.ativo.is_(ativo))
    stmt = aplicar_ordenacao(stmt, sort, ORDENACAO_PERMITIDA, padrao=ProdutoModel.id)
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, produto_id: int) -> ProdutoModel:
    produto = db.scalar(_com_composicao(select(ProdutoModel).where(ProdutoModel.id == produto_id)))
    if produto is None:
        raise NaoEncontradoError("Produto não encontrado.")
    return produto


def cadastrar(db: Session, dto: CreateProdutoDTO) -> ProdutoModel:
    """Cria o produto junto da composição, em uma única transação."""
    linhas = _validar_itens(db, dto.composicao)
    produto = ProdutoModel(
        nome=dto.nome.strip(),
        precoVenda=dto.precoVenda,
        ativo=dto.ativo if dto.ativo is not None else True,
    )
    produto.composicao = linhas
    db.add(produto)
    db.commit()
    return obter(db, produto.id)


def atualizar(db: Session, produto_id: int, dto: UpdateProdutoDTO) -> ProdutoModel:
    """Atualiza nome, preço e disponibilidade — nunca a composição nem preços históricos."""
    produto = obter(db, produto_id)
    produto.nome = dto.nome.strip()
    produto.precoVenda = dto.precoVenda
    produto.ativo = dto.ativo
    db.commit()
    return obter(db, produto_id)


def desativar(db: Session, produto_id: int) -> None:
    """Desativação lógica (`ativo=false`); o produto não é apagado. Idempotente."""
    produto = obter(db, produto_id)
    if produto.ativo:
        produto.ativo = False
        db.commit()


def obter_composicao(db: Session, produto_id: int) -> ProdutoModel:
    """Produto com a composição carregada (resposta `ComposicaoProduto`)."""
    return obter(db, produto_id)


def substituir_composicao(
    db: Session, produto_id: int, dto: SubstituirComposicaoDTO
) -> ProdutoModel:
    """Substitui a composição integralmente (as linhas antigas são removidas)."""
    produto = obter(db, produto_id)
    linhas = _validar_itens(db, dto.itens)
    produto.composicao = linhas  # delete-orphan remove o que saiu
    db.commit()
    return obter(db, produto_id)


def tem_itens_de_pedido(db: Session, produto_id: int) -> bool:
    """Indica se o produto já figura em algum pedido (histórico a preservar)."""
    return bool(
        db.scalar(select(PedidoItemModel.id).where(PedidoItemModel.produtoId == produto_id).limit(1))
    )


__all__ = [
    "ORDENACAO_PERMITIDA",
    "atualizar",
    "cadastrar",
    "desativar",
    "listar",
    "obter",
    "obter_composicao",
    "substituir_composicao",
    "tem_itens_de_pedido",
]
