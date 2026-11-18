"""Router de usuários (Fase 5 — P5-23 a P5-27).

Todas as operações são restritas a `ADMINISTRADOR` (descrições do contrato), aplicado
pela dependência `somente_administrador` no próprio router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import resposta_sem_conteudo
from ..schemas import (
    CreateFuncionarioDTO,
    PageMetadata,
    PaginatedUsuarios,
    UpdateUsuarioDTO,
    Usuario,
)
from ..security import cadastrar_funcionario, somente_administrador
from ..services import usuarios as servico
from .comum import (
    BuscaQuery,
    IdPath,
    PageQuery,
    SizeQuery,
    SortQuery,
    location,
    resposta_criado,
    respostas,
)

router = APIRouter(
    prefix="/usuarios",
    tags=["Usuários"],
    dependencies=[Depends(somente_administrador)],
)


@router.get(
    "",
    operation_id="listarUsuarios",
    summary="Listar usuários",
    response_model=PaginatedUsuarios,
    responses={200: {"description": "Página de usuários."}, **respostas(400, 401, 403)},
)
def listar_usuarios(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    q: BuscaQuery = None,
) -> PaginatedUsuarios:
    pagina = servico.listar(db, page=page, size=size, sort=sort, q=q)
    return PaginatedUsuarios(
        data=[Usuario.model_validate(u) for u in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="cadastrarFuncionario",
    summary="Cadastrar funcionário",
    status_code=status.HTTP_201_CREATED,
    response_model=Usuario,
    responses={
        201: resposta_criado("Funcionário criado.", "/api/v1/usuarios/12"),
        **respostas(400, 401, 403, 409, 422),
    },
)
def cadastrar_funcionario_endpoint(
    dto: CreateFuncionarioDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Usuario:
    """O perfil é definido pelo servidor como FUNCIONARIO (nunca vem do cliente)."""
    usuario = cadastrar_funcionario(db, dto)
    location(response, f"/api/v1/usuarios/{usuario.id}")
    return Usuario.model_validate(usuario)


@router.get(
    "/{id}",
    operation_id="consultarUsuario",
    summary="Consultar usuário por ID",
    response_model=Usuario,
    responses={200: {"description": "Usuário encontrado."}, **respostas(401, 403, 404)},
)
def consultar_usuario(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Usuario:
    return Usuario.model_validate(servico.obter(db, id))


@router.patch(
    "/{id}",
    operation_id="atualizarUsuario",
    summary="Atualizar usuário",
    response_model=Usuario,
    responses={
        200: {"description": "Usuário atualizado."},
        **respostas(400, 401, 403, 404, 409, 422),
    },
)
def atualizar_usuario(
    id: IdPath, dto: UpdateUsuarioDTO, db: Annotated[Session, Depends(get_db)]
) -> Usuario:
    """Atualiza nome, e-mail e/ou ativo. Perfil e credenciais não são alteráveis."""
    return Usuario.model_validate(servico.atualizar(db, id, dto))


@router.delete(
    "/{id}",
    operation_id="desativarUsuario",
    summary="Desativar usuário",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Usuário desativado."},
        **respostas(401, 403, 404, 409),
    },
)
def desativar_usuario(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Desativação lógica: preserva pedidos e movimentações do usuário."""
    servico.desativar(db, id)
    return resposta_sem_conteudo()
