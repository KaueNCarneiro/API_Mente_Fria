"""Configurações tipadas por ambiente e convenções de logging (Fase 1).

Cobre P1-09 (configuração tipada), P1-10 (``.env`` só em desenvolvimento),
P1-11 (obrigatoriedade/validação), P1-12 (SQLite local x testes), P1-14 (CORS por
ambiente) e P1-16 (logging com ocultação de dados sensíveis).

Regras:
- Nenhum segredo possui valor padrão. ``jwt_secret_key`` e a expiração do token são
  sempre obrigatórios (o contrato não fixa duração de token).
- O arquivo ``.env`` é lido apenas quando ``MENTE_FRIA_ENV`` é ``local`` (ou ausente).
  Em ``production`` os valores vêm do ambiente de execução / secret manager.
- Qualquer ambiente implantado usa ``production``; não há origens de produção
  presumidas.
"""

from __future__ import annotations

import logging
import os
import re
from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_VAR_NAME = "MENTE_FRIA_ENV"
ENV_PREFIX = "MENTE_FRIA_"
DOTENV_FILE = ".env"

LOCAL_DATABASE_URL = "sqlite:///./mente_fria.db"
TEST_DATABASE_URL = "sqlite:///:memory:"

MIN_PRODUCTION_SECRET_LENGTH = 32
_PLACEHOLDER_SECRET_PREFIXES = ("change_me", "changeme", "troque", "secret", "senha")
_VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class Environment(StrEnum):
    """Ambientes de execução reconhecidos."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Configuração da aplicação, lida de variáveis ``MENTE_FRIA_*``."""

    # hide_input_in_errors evita que valores inválidos (ex.: segredo curto) apareçam
    # em mensagens de ValidationError/logs.
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=None,
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    env: Environment = Environment.LOCAL
    # Resolvido por `_resolve_and_validate`: local -> arquivo SQLite, test -> memória,
    # production -> obrigatório.
    database_url: str = ""
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_expire_seconds: int = Field(ge=1)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    log_level: str = "INFO"

    @field_validator("jwt_secret_key")
    @classmethod
    def _secret_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("o segredo JWT não pode ser vazio")
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"nível de log inválido; use um de {sorted(_VALID_LOG_LEVELS)}")
        return level

    @model_validator(mode="after")
    def _resolve_and_validate(self) -> Self:
        self.database_url = self.database_url.strip()

        if not self.database_url:
            if self.env is Environment.LOCAL:
                self.database_url = LOCAL_DATABASE_URL
            elif self.env is Environment.TEST:
                self.database_url = TEST_DATABASE_URL
            else:
                raise ValueError(
                    f"{ENV_PREFIX}DATABASE_URL é obrigatório quando "
                    f"{ENV_VAR_NAME}={self.env.value}"
                )

        if self.env is Environment.TEST and self.database_url == LOCAL_DATABASE_URL:
            raise ValueError(
                "o ambiente de testes não pode usar o banco de desenvolvimento "
                f"({LOCAL_DATABASE_URL}); use memória ou arquivo temporário"
            )

        if self.env is Environment.PRODUCTION:
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret) < MIN_PRODUCTION_SECRET_LENGTH:
                raise ValueError(
                    f"o segredo JWT deve ter ao menos {MIN_PRODUCTION_SECRET_LENGTH} "
                    "caracteres em production"
                )
            if secret.lower().startswith(_PLACEHOLDER_SECRET_PREFIXES):
                raise ValueError("o segredo JWT em production não pode ser um placeholder")
            if "*" in self.cors_allowed_origins:
                raise ValueError("CORS com origem '*' não é permitido em production")

        return self


@lru_cache
def get_settings() -> Settings:
    """Carrega (uma vez) a configuração do processo.

    O ``.env`` é considerado somente em desenvolvimento local; nos demais ambientes
    a configuração vem exclusivamente das variáveis de ambiente.
    """
    env_name = os.environ.get(ENV_VAR_NAME, Environment.LOCAL.value).strip().lower()
    env_file = DOTENV_FILE if env_name == Environment.LOCAL.value else None
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Logging (P1-16)
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = (
    "senha_hash",
    "senha",
    "password",
    "passwd",
    "secret_key",
    "secret",
    "access_token",
    "accesstoken",
    "token",
    "authorization",
    "hash",
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_KEY_VALUE_RE = re.compile(
    r"""(?ix)
    (?<![\w])
    (?P<key>["']?(?:"""
    + "|".join(_SENSITIVE_KEYS)
    + r""")["']?)
    (?P<sep>\s*[=:]\s*)
    (?P<value>"[^"]*"|'[^']*'|[^\s,;}&]+)
    """
)
_REDACTED = "***"
_HANDLER_MARK = "_mente_fria_handler"


def redact(text: str) -> str:
    """Mascara senhas, tokens, segredos e hashes presentes em ``text``."""
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    return _KEY_VALUE_RE.sub(lambda m: f'{m.group("key")}{m.group("sep")}"{_REDACTED}"', text)


class RedactingFilter(logging.Filter):
    """Filtro que oculta credenciais e dados sensíveis das mensagens de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configura o logger raiz com formato único e filtro de ocultação.

    Idempotente: reaplica o nível e substitui apenas o handler instalado por esta
    função, preservando handlers de terceiros (ex.: ferramentas de teste).
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
