"""Router de autenticação (Fase 5 — P5-21, P5-22).

Duas operações **públicas** do contrato: bootstrap do primeiro administrador e login.
A lógica vive em `security.py` (P4-08/P4-09); aqui fica só a camada HTTP.

Não existe `GET /api/v1/auth/me` no contrato — e não é implementada.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AuthToken, CreateAdminDTO, LoginDTO, Usuario
from ..security import autenticar, criar_conta_administrador, montar_auth_token
from .comum import location, resposta_criado, respostas

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/administrador",
    operation_id="criarContaAdministrador",
    summary="Criar conta de administrador",
    status_code=status.HTTP_201_CREATED,
    response_model=Usuario,
    responses={
        201: resposta_criado("Conta Administrador criada.", "/api/v1/usuarios/1"),
        **respostas(400, 409, 422),
    },
)
def criar_conta_administrador_endpoint(
    dto: CreateAdminDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Usuario:
    """Bootstrap público: só conclui enquanto não existir um ADMINISTRADOR."""
    usuario = criar_conta_administrador(db, dto)
    location(response, f"/api/v1/usuarios/{usuario.id}")
    return Usuario.model_validate(usuario)


@router.post(
    "/login",
    operation_id="autenticarUsuario",
    summary="Autenticar usuário",
    response_model=AuthToken,
    responses={200: {"description": "Autenticação realizada."}, **respostas(400, 401, 422)},
)
def autenticar_usuario(dto: LoginDTO, db: Annotated[Session, Depends(get_db)]) -> AuthToken:
    """Valida credenciais e conta ativa e emite o token Bearer."""
    usuario = autenticar(db, dto)
    return montar_auth_token(usuario)
