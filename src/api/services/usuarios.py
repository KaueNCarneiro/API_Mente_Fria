"""Service de usuários (Fase 5 — P5-02).

Cobre `listarUsuarios`, `consultarUsuario`, `atualizarUsuario` e `desativarUsuario`.
O cadastro de funcionário e o bootstrap do administrador vivem em ``security.py``
(P4-08/P4-10) e são apenas reaproveitados pelos routers.

Regras do SPEC §6.1: a atualização altera somente `nome`, `email` e `ativo` — nunca
perfil ou credenciais; a exclusão é desativação lógica, preservando o histórico.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..exceptions import ConflitoError, NaoEncontradoError
from ..models import UsuarioModel
from ..schemas import UpdateUsuarioDTO
from .comum import Pagina, aplicar_ordenacao, paginar, termo_de_busca

ORDENACAO_PERMITIDA = {
    "id": UsuarioModel.id,
    "nome": UsuarioModel.nome,
    "email": UsuarioModel.email,
    "perfil": UsuarioModel.perfil,
    "ativo": UsuarioModel.ativo,
}


def listar(
    db: Session, *, page: int, size: int, sort: str | None = None, q: str | None = None
) -> Pagina[UsuarioModel]:
    """Lista usuários; `q` busca por nome ou e-mail."""
    stmt = select(UsuarioModel)
    termo = termo_de_busca(q)
    if termo is not None:
        stmt = stmt.where(
            UsuarioModel.nome.ilike(termo, escape="\\")
            | UsuarioModel.email.ilike(termo, escape="\\")
        )
    stmt = aplicar_ordenacao(stmt, sort, ORDENACAO_PERMITIDA, padrao=UsuarioModel.id)
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, usuario_id: int) -> UsuarioModel:
    """Usuário por id, ou ``404``."""
    usuario = db.get(UsuarioModel, usuario_id)
    if usuario is None:
        raise NaoEncontradoError("Usuário não encontrado.")
    return usuario


def atualizar(db: Session, usuario_id: int, dto: UpdateUsuarioDTO) -> UsuarioModel:
    """Atualiza nome, e-mail e/ou ativo. Campos ausentes no DTO não são tocados.

    E-mail já usado por outra conta resulta em ``409``.
    """
    usuario = obter(db, usuario_id)
    dados = dto.model_dump(exclude_unset=True)

    if "nome" in dados and dados["nome"] is not None:
        usuario.nome = dados["nome"].strip()
    if "email" in dados and dados["email"] is not None:
        usuario.email = dados["email"].strip().lower()
    if "ativo" in dados and dados["ativo"] is not None:
        usuario.ativo = dados["ativo"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflitoError("E-mail já cadastrado.") from None
    db.refresh(usuario)
    return usuario


def desativar(db: Session, usuario_id: int) -> None:
    """Desativação lógica (`ativo=false`); preserva pedidos e movimentações.

    Idempotente: desativar quem já está inativo não é conflito.
    """
    usuario = obter(db, usuario_id)
    if usuario.ativo:
        usuario.ativo = False
        db.commit()
