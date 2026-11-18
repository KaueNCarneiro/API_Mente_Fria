"""Service de saúde (Fase 5 — P5-20).

`GET /api/v1/saude` é público e informa o estado da aplicação e do banco. O contrato
define `status` ∈ {`ok`, `degradado`} e `banco` ∈ {`ok`, `indisponivel`}: quando o banco
não responde, a aplicação está de pé, porém **degradada** — e a operação declara `503`
para esse caso.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..schemas import HealthStatus

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_DEGRADADO = "degradado"
BANCO_OK = "ok"
BANCO_INDISPONIVEL = "indisponivel"


def verificar(db: Session) -> HealthStatus:
    """Consulta trivial ao banco (`SELECT 1`) para distinguir `ok` de `degradado`."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # O motivo fica no log; a resposta pública não expõe detalhe de infraestrutura.
        logger.warning("verificação de saúde: banco indisponível (%s)", type(exc).__name__)
        return HealthStatus(status=STATUS_DEGRADADO, banco=BANCO_INDISPONIVEL)
    return HealthStatus(status=STATUS_OK, banco=BANCO_OK)
