# PLAN.md — Implementação da Mente Fria API

> **Status (2026-11-17):** Fases 1 e 2 concluídas. **Fase 3: 20 de 22 tarefas** — P3-14 fechada com a aprovação da decisão 6; P3-19 (migrações) e P3-20 (seed) seguem **abertas**, bloqueadas pelas decisões 4 e 5. **Fase 4 executada: 18 de 18 tarefas verificadas** (decisões 2 e 3 aprovadas na revisão humana de 2026-11-17). Fases 5 e 6 **não iniciadas**. Execução interrompida para **revisão humana**.
> **Verificação contra o contrato real:** `python verify_schemas.py --openapi "Mente Fria API.openapi.json"` executado em 2026-11-15 sobre o repositório publicado (commit `327c783`): 5 976 verificações, todas OK (inclui descrições e exemplos).

## Premissas e governança

- **Fonte normativa do contrato HTTP:** `Mente Fria API.openapi.json` (OpenAPI 3.0.1). `SPEC.md` e `STYLEGUIDE.md` orientam a implementação sem redefinir o contrato.
- **Inventário confirmado:** 26 caminhos (`paths`), 44 operações HTTP e 54 `components.schemas`; há também 8 `components.responses`, 6 parâmetros compartilhados e o esquema `bearerAuth`.
- **Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0+, PyJWT, SQLite local e pytest/TestClient/httpx.
- **Regra SDD:** nenhuma implementação em `src/` antes de existir tarefa correspondente neste plano e solicitação explícita. Não criar endpoints, schemas, campos, enums, filtros, permissões ou respostas fora do contrato.
- **Dependências:** cada tarefa lista IDs predecessores. Uma tarefa só pode começar quando suas dependências estiverem verificadas.
- **Concluído:** marcar `[x]` somente após execução e evidência verificável. Planejamento, por si só, não conta como execução.

## Resumo de arquitetura planejada

- `src/api/main.py`: aplicação FastAPI, lifespan, CORS, handlers e inclusão dos routers sob `/api/v1`.
- `config.py`: configurações tipadas por ambiente e segredos; `schemas.py`: os 54 schemas Pydantic v2 e aliases JSON.
- `models.py`/`database.py`: ORM SQLAlchemy 2.0, relacionamentos, integridade, Engine, SessionLocal e dependência `get_db`.
- `security.py`/`exceptions.py`: hash de senha, JWT Bearer, dependências RBAC e envelope `ApiError`.
- `services/`: regras de negócio, especialmente estoque/FEFO, pedidos/transações, recomendações e dashboard.
- `integrations/optimizer.py`: integração isolada do solver de Programação Linear Inteira.
- `routers/`: módulos por domínio; `tests/`: suíte pytest isolada em SQLite.

## Dependências entre fases

1. Fase 1 estabelece estrutura, ambiente e configuração-base.
2. Fase 2 depende da estrutura-base da Fase 1 e fecha o contrato de dados antes do ORM/HTTP.
3. Fase 3 depende da estrutura e dos schemas para modelar persistência coerente.
4. Fase 4 depende de configuração, schemas, usuários ORM e banco.
5. Fase 5 depende de schemas, ORM e segurança; as operações só são concluídas após services e autorização estarem disponíveis.
6. Fase 6 valida o conjunto integrado das fases anteriores.

## Fase 1 — Estrutura do projeto e dependências

**Total de tarefas: 17** — **concluídas e verificadas: 17**

### Checklist sequencial

- [x] **P1-01** Registrar Python 3.12+ como versão mínima e definir a forma reproduzível de execução local.  
  - Dependências: —.  
  - Evidência: `src/api/requirements.txt` (cabeçalho) e *Comandos de referência* abaixo; ambiente de verificação em Python 3.12.3.
- [x] **P1-02** Definir a árvore de diretórios conforme STYLEGUIDE.md: `src/api/`, `routers/`, `services/`, `integrations/` e `tests/`.  
  - Dependências: P1-01.  
  - Evidência: Árvore criada: 45 arquivos em `src/api/` (conferida por listagem).
- [x] **P1-03** Planejar os arquivos-base `src/api/__init__.py`, `main.py`, `config.py`, `schemas.py`, `models.py`, `database.py`, `security.py` e `exceptions.py`.  
  - Dependências: P1-02.  
  - Evidência: Os 8 arquivos existem; `models.py`, `database.py`, `security.py` e `exceptions.py` são apenas stubs com docstring (Fases 3 e 4).
- [x] **P1-04** Planejar os pacotes `routers/`, `services/` e `integrations/`, incluindo seus `__init__.py`.  
  - Dependências: P1-02.  
  - Evidência: 3 pacotes com `__init__.py`; 13 routers, 4 services e `optimizer.py` como stubs vazios.
- [x] **P1-05** Planejar a localização de `tests/__init__.py`, `tests/conftest.py` e dos 13 módulos de teste definidos no STYLEGUIDE.md.  
  - Dependências: P1-02.  
  - Evidência: `tests/__init__.py`, `conftest.py` e 13 `test_*.py` criados como stubs (sem testes; `pytest` retorna *no tests ran*).
- [x] **P1-06** Definir `requirements.txt` com FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2.0, PyJWT, biblioteca de hash de senha, driver SQLite e dependências de teste (`pytest`, `httpx`).  
  - Dependências: P1-01.  
  - Evidência: Instalação limpa em venv novo (Python 3.12.3) resolveu todas as dependências. Driver SQLite = módulo `sqlite3` da biblioteca padrão. Biblioteca de hash (`argon2-cffi`) é **proposta**, pendente de aprovação (decisão 2).
- [x] **P1-07** Avaliar e registrar a dependência de migrações de schema (por exemplo, Alembic), sem adotar ferramenta não aprovada silenciosamente.  
  - Dependências: P1-06.  
  - Evidência: Registrado no `requirements.txt` como *não adotado* (decisão 4 pendente); nenhuma ferramenta de migração foi instalada.
- [x] **P1-08** Definir estratégia de versões/compatibilidade e registrar versões mínimas ou faixas reproduzíveis das dependências no `requirements.txt`.  
  - Dependências: P1-06.  
  - Evidência: Faixas `>=versão verificada,<próxima major`; versões instaladas: fastapi 0.163.1, pydantic 2.14.3, pydantic-settings 2.16.3, SQLAlchemy 2.1.8, PyJWT 2.15.1, argon2-cffi 25.1.0, pytest 9.2.0, httpx 0.28.1.
- [x] **P1-09** Definir `config.py` com configurações tipadas por ambiente: URL do banco, segredo JWT, algoritmo e expiração configurável, sem fixar prazo não definido pelo contrato.  
  - Dependências: P1-03.  
  - Evidência: `Settings` (pydantic-settings); segredo e expiração obrigatórios e sem valor padrão (verificado).
- [x] **P1-10** Definir carregamento de `.env` apenas para desenvolvimento e política de fornecimento de segredos por ambiente/secret manager em implantação.  
  - Dependências: P1-09.  
  - Evidência: Teste em subprocesso: `.env` carregado com `MENTE_FRIA_ENV=local` e ignorado em `production`; `.env.example` sem segredo real; `.env` no `.gitignore`.
- [x] **P1-11** Definir valores obrigatórios, validação de configuração ausente e proteção para impedir segredo JWT inseguro em ambientes não locais.  
  - Dependências: P1-09; P1-10.  
  - Evidência: Em `production`: segredo ≥ 32 caracteres e não-placeholder, banco obrigatório, CORS `*` recusado; segredo não aparece nas mensagens de erro (verificado).
- [x] **P1-12** Definir configuração SQLite local `sqlite:///./mente_fria.db` e separação explícita das configurações de teste.  
  - Dependências: P1-09.  
  - Evidência: `local` → arquivo; `test` → `sqlite:///:memory:` e recusa o arquivo de desenvolvimento (verificado). Engine/sessão ficam para a Fase 3.
- [x] **P1-13** Planejar a fábrica/configuração inicial do FastAPI, metadados da API e ciclo de vida (`lifespan`) conforme o STYLEGUIDE.md.  
  - Dependências: P1-03; P1-09.  
  - Evidência: `create_app()` com título/versão/descrição/contato/tags copiados de `info` do contrato; `lifespan` registra início/fim; uvicorn sobe e serve `/docs` e `/openapi.json`.
- [x] **P1-14** Definir política de CORS por ambiente sem presumir origens de produção.  
  - Dependências: P1-13.  
  - Evidência: CORS desabilitado por padrão; só com `MENTE_FRIA_CORS_ALLOWED_ORIGINS` explícito (verificado).
- [x] **P1-15** Definir ponto de entrada executável `main.py`, prefixo contratual `/api/v1` e registro centralizado futuro dos routers.  
  - Dependências: P1-13.  
  - Evidência: `register_routers()` monta `APIRouter(prefix="/api/v1")` vazio; nenhuma rota registrada (OpenAPI do app tem 0 paths); `python -m src.api.main` e `uvicorn --factory` documentados.
- [x] **P1-16** Definir convenções de logging, configuração de nível e ocultação de credenciais/dados sensíveis.  
  - Dependências: P1-09; P1-13.  
  - Evidência: `configure_logging` idempotente + `RedactingFilter`: senha, token, Bearer, segredo e hash mascarados, inclusive via `%s` (verificado).
- [x] **P1-17** Documentar comandos planejados para instalar dependências, iniciar API e executar testes, sem implementar código nesta etapa.  
  - Dependências: P1-06; P1-15.  
  - Evidência: Seção *Comandos de referência* abaixo; comandos executados com sucesso (exceto `pytest`, que ainda não tem testes).

### Comandos de referência

Execute a partir da **raiz do repositório** (o `.env` é lido do diretório corrente):

```bash
python3.12 -m venv .venv && source .venv/bin/activate     # Python 3.12+
pip install -r src/api/requirements.txt                   # instalar dependências
cp .env.example .env                                      # somente desenvolvimento local; trocar o segredo
uvicorn --factory src.api.main:create_app --reload        # iniciar a API (http://127.0.0.1:8000/docs)
python -m pytest src/api/tests                            # testes (sem testes até a Fase 6: "no tests ran")
python verify_schemas.py                                  # verificação dos schemas Pydantic (Fase 2)
python verify_schemas.py --openapi "Mente Fria API.openapi.json"   # idem, comparando direto com o contrato
python verify_models.py                                   # verificação prática do ORM/banco (Fase 3; SQLite em memória)
```

Em `test`/`production` não há `.env`: forneça `MENTE_FRIA_ENV`, `MENTE_FRIA_DATABASE_URL` (obrigatório em `production`), `MENTE_FRIA_JWT_SECRET_KEY` e `MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS` pelo ambiente de execução.

### Critérios de aceite

- [x] Árvore de diretórios e arquivos definida conforme STYLEGUIDE.md.
- [x] Dependências e versões mínimas registradas e instaláveis em ambiente Python 3.12+.
- [x] Configuração por ambiente e política de segredos documentadas, sem segredo real versionado.
- [x] Ponto de entrada FastAPI planejado com ciclo de vida, prefixo `/api/v1` e registro central de routers.

## Fase 2 — Schemas Pydantic v2

**Total de tarefas: 64** — **concluídas e verificadas: 64**

### Checklist sequencial

- [x] **P2-01** Implementar o schema Pydantic v2 `ApiErrorDetail` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-02** Implementar o schema Pydantic v2 `ApiError` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-03** Implementar o schema Pydantic v2 `PageMetadata` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-04** Implementar o schema Pydantic v2 `CreateAdminDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-05** Implementar o schema Pydantic v2 `CreateFuncionarioDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-06** Implementar o schema Pydantic v2 `UpdateUsuarioDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-07** Implementar o schema Pydantic v2 `Usuario` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-08** Implementar o schema Pydantic v2 `LoginDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-09** Implementar o schema Pydantic v2 `AuthToken` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.  
  - Evidência: `tokenType` mantém o default `"Bearer"` do contrato; o schema de serialização o marca como obrigatório (ver *Decisões da Fase 2*).
- [x] **P2-10** Implementar o schema Pydantic v2 `CreateClienteDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-11** Implementar o schema Pydantic v2 `UpdateClienteDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-12** Implementar o schema Pydantic v2 `Cliente` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-13** Implementar o schema Pydantic v2 `UnidadeMedida` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-14** Implementar o schema Pydantic v2 `CreateUnidadeMedidaDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-15** Implementar o schema Pydantic v2 `UpdateUnidadeMedidaDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-16** Implementar o schema Pydantic v2 `CreateIngredienteDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-17** Implementar o schema Pydantic v2 `UpdateIngredienteDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-18** Implementar o schema Pydantic v2 `Ingrediente` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-19** Implementar o schema Pydantic v2 `ComposicaoProdutoItemDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-20** Implementar o schema Pydantic v2 `ComposicaoProdutoItem` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-21** Implementar o schema Pydantic v2 `CreateProdutoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-22** Implementar o schema Pydantic v2 `UpdateProdutoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-23** Implementar o schema Pydantic v2 `Produto` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-24** Implementar o schema Pydantic v2 `CreateMovimentacaoEstoqueDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-25** Implementar o schema Pydantic v2 `MovimentacaoEstoque` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-26** Implementar o schema Pydantic v2 `PedidoItemDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-27** Implementar o schema Pydantic v2 `CreatePedidoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-28** Implementar o schema Pydantic v2 `PedidoItem` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-29** Implementar o schema Pydantic v2 `Pedido` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-30** Implementar o schema Pydantic v2 `CancelamentoPedidoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-31** Implementar o schema Pydantic v2 `ProducaoRecomendacaoItem` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-32** Implementar o schema Pydantic v2 `ProducaoRecomendacao` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-33** Implementar o schema Pydantic v2 `CreateReposicaoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-34** Implementar o schema Pydantic v2 `ReposicaoRecomendacaoItem` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-35** Implementar o schema Pydantic v2 `ReposicaoRecomendacao` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-36** Implementar o schema Pydantic v2 `AlertaReposicao` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-37** Implementar o schema Pydantic v2 `AlertaValidade` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-38** Implementar o schema Pydantic v2 `SugestaoMarketing` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-39** Implementar o schema Pydantic v2 `Dashboard` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-40** Implementar o schema Pydantic v2 `ProdutoMaisVendido` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.  
  - Evidência: declarado antes de `Dashboard` (ordem topológica; no contrato vem depois).
- [x] **P2-41** Implementar o schema Pydantic v2 `HealthStatus` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-42** Implementar o schema Pydantic v2 `PaginatedUsuarios` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-43** Implementar o schema Pydantic v2 `PaginatedClientes` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-44** Implementar o schema Pydantic v2 `PaginatedUnidadesMedida` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-45** Implementar o schema Pydantic v2 `PaginatedIngredientes` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-46** Implementar o schema Pydantic v2 `PaginatedProdutos` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-47** Implementar o schema Pydantic v2 `PaginatedMovimentacoesEstoque` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-48** Implementar o schema Pydantic v2 `PaginatedPedidos` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-49** Implementar o schema Pydantic v2 `ComposicaoProduto` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-50** Implementar o schema Pydantic v2 `SubstituirComposicaoDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-51** Implementar o schema Pydantic v2 `VazioDTO` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-52** Implementar o schema Pydantic v2 `ListaAlertasReposicao` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-53** Implementar o schema Pydantic v2 `ListaAlertasValidade` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.
- [x] **P2-54** Implementar o schema Pydantic v2 `CsvFile` fiel ao `components.schemas` do OpenAPI: required, opcionais, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties`.  
  - Dependências: P1-03.  
  - Evidência: alias `CsvFile = Annotated[str, Field(..., format binary)]`; não é envelope JSON.
- [x] **P2-55** Definir configuração Pydantic compartilhada (`ConfigDict`) e política consistente de objetos fechados quando `additionalProperties: false`.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: `_ContractModel`: `extra="forbid"`, `from_attributes=True`; todos os 53 modelos herdam dela (verificado).
- [x] **P2-56** Definir aliases explícitos para preservar nomes JSON do contrato (incluindo camelCase/português), com validação e serialização usando a configuração apropriada do Pydantic v2.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: Nomes JSON preservados **sem aliases**: os atributos Python já são o camelCase do contrato (instrução do usuário: sem aliases desnecessários). Verificado: nenhum campo com alias e chaves serializadas idênticas às do contrato nos 53 modelos.
- [x] **P2-57** Organizar DTOs de entrada, schemas de saída, schemas auxiliares, paginação e erros no módulo `src/api/schemas.py`, sem duplicar contratos inline nos routers.  
  - Dependências: P2-01 a P2-56.  
  - Evidência: Módulo único com `__all__` de 54 nomes; tipos reutilizáveis (`Id`, `Email`, `Qtd3*`, `Reais*`) e enums como `Literal` (nenhum schema extra criado).
- [x] **P2-58** Verificar especificamente os seis schemas de autenticação/usuário: `CreateAdminDTO`, `CreateFuncionarioDTO`, `LoginDTO`, `UpdateUsuarioDTO`, `Usuario` e `AuthToken`.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: Limites de nome/e-mail/senha, e-mail inválido/longo, enum de perfil, `ativo`, `null` rejeitado em `UpdateUsuarioDTO`, `Usuario` sem senha/hash (via `from_attributes` com objeto contendo `senha_hash`), `senha` fora do `repr`.
- [x] **P2-59** Verificar `ApiError` e `ApiErrorDetail`, incluindo limites, `timestamp` date-time e `correlationId` opcional.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: Limites 80/500/300/100, `timestamp` com offset, `correlationId` e `valorRejeitado` nuláveis (verificado).
- [x] **P2-60** Verificar `PageMetadata` e os seis formatos paginados, preservando `data` e `paginacao` com `page`, `size`, `totalElements` e `totalPages`.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: Sete envelopes (`Paginated*`) verificados, `size` 1–100, `page` ≥ 0.
- [x] **P2-61** Mapear `CsvFile` como resposta binária/texto `text/csv`, sem modelá-lo como envelope JSON.  
  - Dependências: P2-01 a P2-54.  
  - Evidência: `CsvFile` não é `BaseModel`; `format: binary` e descrição preservados.
- [x] **P2-62** Planejar testes unitários de cada schema: campos obrigatórios/opcionais, limites, formatos, enums, arrays, valores nulos e rejeição de propriedades extras conforme o OpenAPI.  
  - Dependências: P2-01 a P2-61.  
  - Evidência: `verify_schemas.py` (raiz) gera e executa os casos por campo: 4 824 verificações passaram. Testes pytest definitivos ficam em P6-17.
- [x] **P2-63** Planejar teste de round-trip/serialização para confirmar aliases e nomes JSON exatos.  
  - Dependências: P2-56; P2-62.  
  - Evidência: Round-trip JSON em todos os modelos; `Decimal` serializado como número JSON (não string); chaves exatas (verificado).
- [x] **P2-64** Planejar comparação automatizada entre os 54 schemas Pydantic e `components.schemas` para detectar divergências de contrato.  
  - Dependências: P2-01 a P2-63.  
  - Evidência: `python verify_schemas.py --openapi "Mente Fria API.openapi.json"` → 54 schemas, 5 976 verificações OK (tipos, limites, enums, nullability, required, `additionalProperties`, descrições e exemplos). O comparador também detecta divergência proposital (autoteste).

### Critérios de aceite

- [x] Os 54 nomes de `components.schemas` estão cobertos sem schema omitido ou inventado.
- [x] Campos, required, tipos, formatos, enums, limites, exemplos, nullability e `additionalProperties` conferidos contra OpenAPI. *(comparação direta com o arquivo real — ver P2-64)*
- [x] Aliases preservam os nomes JSON; paginação usa `data`/`paginacao`; erros usam `ApiError`; CSV não é JSON. *(nomes preservados sem aliases — ver P2-56)*
- [x] Testes de validação e serialização planejados para todos os schemas.

### Decisões da Fase 2 a validar na revisão humana

1. **`date-time` → `datetime`** (aceita datas sem fuso). `AwareDatetime` seria mais estrito, mas exigiria timezone nos valores vindos do SQLite (Fase 3).
2. **`format: int32`** → `le=2147483647` nos IDs e inteiros int32 (o contrato não traz `maximum`).
3. **Modo *lax* do Pydantic:** aceita string numérica (`"12.5"`) em campos numéricos no JSON; o rigor estrito não é exigido pelo contrato.
4. **`AuthToken.tokenType`:** obrigatório *e* com default no contrato; mantido o default `"Bearer"` (validação não o exige na entrada; a serialização o declara obrigatório).
5. **Opcionais não-nuláveis** (`UpdateUsuarioDTO.*`, `ProducaoRecomendacao.observacao`): `default=None` rejeitando `null` explícito; o JSON Schema do FastAPI mostrará `default: null`. Em services, usar `model_dump(exclude_unset=True)`.
6. **Enums inline** representados por `Literal` (sem criar schemas fora dos 54).
7. **`senha`** com `repr=False` (higiene de logs; não altera o contrato).
8. **Descrições e exemplos** copiados do contrato e conferidos automaticamente contra o arquivo real (P2-64).

## Fase 3 — Modelagem ORM e banco de dados

**Total de tarefas: 22** — **concluídas e verificadas: 20** (P3-14 fechada em 2026-11-17 com a aprovação da decisão 6; abertas: P3-19 e P3-20 — aguardam as decisões 4 e 5)

### Checklist sequencial

- [x] **P3-01** Definir `DeclarativeBase` e convenções SQLAlchemy 2.0 para `Mapped`, `mapped_column`, `relationship`, `ForeignKey` e `select()`.  
  - Dependências: P1-03; P2-57.  
  - Evidência: `Base(DeclarativeBase)` com `MetaData(naming_convention)`; apenas `Mapped`/`mapped_column`/`relationship`/`ForeignKey` (sem API legada). Convenção `select()` fica para services (Fase 5).
- [x] **P3-02** Modelar `usuarios`: ID, nome, e-mail único, hash de senha, perfil limitado a `ADMINISTRADOR`/`FUNCIONARIO` e ativo.  
  - Dependências: P3-01.  
  - Evidência: `UsuarioModel`: e-mail `UNIQUE`, `senha_hash` (nunca senha), `CHECK perfil IN ('ADMINISTRADOR','FUNCIONARIO')`, `ativo`. Verificado: e-mail duplicado, `ADMIN`/`MEMBER` recusados.
- [x] **P3-03** Modelar `clientes`: ID, nome, contato e endereço; permitir associação opcional a pedidos.  
  - Dependências: P3-01.  
  - Evidência: `ClienteModel` (nome/contato/endereço nos limites do contrato); `PedidoModel.clienteId` anulável.
- [x] **P3-04** Modelar `unidades_medida`: chave textual `unidadeMedida` e `porcaoPadrao`, com comprimento contratual.  
  - Dependências: P3-01.  
  - Evidência: `UnidadeMedidaModel`: PK textual `unidade_medida` String(20), `porcaoPadrao` `Numeric(10,3)` com `CHECK >= 0.001`.
- [x] **P3-05** Modelar `ingredientes`: unidade referenciada, custo unitário, porção padrão e quantidade mínima; não persistir saldo editável como fonte de verdade.  
  - Dependências: P3-01; P3-04.  
  - Evidência: `IngredienteModel` sem coluna de saldo (verificado por introspecção); `quantidadeMinima` omitida assume 0.
- [x] **P3-06** Modelar `movimentacoes_estoque`/lotes: ingrediente, usuário, tipo, quantidade, data, validade, quantidade restante, observação e motivo.  
  - Dependências: P3-01; P3-02; P3-05.  
  - Evidência: `MovimentacaoEstoqueModel` com `CHECK` de coerência de lote (ENTRADA: restante entre 0 e quantidade; SAIDA: sem restante nem validade), tipo/motivo; índice de lotes por ingrediente/tipo/validade.
- [x] **P3-07** Modelar `produtos`: nome, preço de venda e estado ativo.  
  - Dependências: P3-01.  
  - Evidência: `ProdutoModel`: `precoVenda` `Numeric(10,2)` com `CHECK >= 0.01`, `ativo`.
- [x] **P3-08** Modelar `composicoes_produto` como associação produto–ingrediente com `quantidadeUtilizada`.  
  - Dependências: P3-01; P3-05; P3-07.  
  - Evidência: `ComposicaoProdutoModel` (`quantidadeUtilizada` `Numeric(10,3)`, `CHECK >= 0.001`); `nomeIngrediente`/`unidadeMedida` derivados do ingrediente.
- [x] **P3-09** Definir chave composta ou restrição única para impedir ingrediente duplicado na composição do mesmo produto.  
  - Dependências: P3-08.  
  - Evidência: Chave primária composta `(produto_id, ingrediente_id)`; duplicação recusada (`IntegrityError` verificado).
- [x] **P3-10** Modelar `pedidos`: usuário criador, cliente opcional, data, total, status e dados de cancelamento.  
  - Dependências: P3-01; P3-02; P3-03.  
  - Evidência: `PedidoModel` com `CHECK` de status e de coerência do cancelamento; `observacaoCancelamento` persistida (justificativa do `CancelamentoPedidoDTO`).
- [x] **P3-11** Modelar `itens_pedido`: produto, quantidade, nome/preço unitário registrado e subtotal para preservar histórico comercial.  
  - Dependências: P3-01; P3-07; P3-10.  
  - Evidência: `PedidoItemModel` com snapshot (`nomeProduto`, `precoUnitarioRegistrado`, `subtotal`); verificado que permanece igual após alterar/desativar o produto.
- [x] **P3-12** Definir todas as `ForeignKey`, `relationship`, cardinalidades e estratégias `ondelete`/cascata sem apagar histórico referenciado.  
  - Dependências: P3-02 a P3-11.  
  - Evidência: 10 FKs verificadas: todas `RESTRICT`, exceto `composicoes_produto.produto_id` (`CASCADE`, não é histórico); coleções com `passive_deletes="all"`; todos os relacionamentos resolvem em `configure_mappers()`.
- [x] **P3-13** Definir restrições de unicidade e integridade referencial: e-mail, unidade em uso, cliente com pedido, ingrediente com composição/histórico e produto com itens históricos.  
  - Dependências: P3-02 a P3-12.  
  - Evidência: Verificado com `PRAGMA foreign_keys=ON`: unidade em uso, cliente com pedido, ingrediente com composição, ingrediente com movimentações, produto com itens, usuário com pedidos/movimentações e pedido com itens **não** podem ser excluídos.
- [x] **P3-14** Definir `Numeric` com precisão/escala adequada e conversão `Decimal` para dinheiro e quantidades decimais; não usar `float` em cálculos financeiros.  
  - Dependências: P3-05 a P3-11.  
  - Evidência: **decisão 6 aprovada na revisão humana de 2026-11-17**, confirmando a proposta já implementada: dinheiro `Numeric(10,2)`, quantidades `Numeric(10,3)`, totais/subtotais de pedido `Numeric(15,2)`. Verificado: valores nos limites do contrato (`99999999.99`, `9999999.999`) e `valorTotal` de 12 dígitos inteiros voltam sem perda; sem `float` nos modelos; nenhum aviso do SQLAlchemy (`verify_models.py`, 122 verificações OK).
- [x] **P3-15** Definir semântica de `date` e `datetime` com timezone quando aplicável, alinhada aos formatos OpenAPI.  
  - Dependências: P3-06; P3-10.  
  - Evidência: `TimestampTZ`: grava UTC, devolve `America/Sao_Paulo` (-03:00); `datetime` sem fuso é recusado; validade é `date` (verificado).
- [x] **P3-16** Planejar consultas de saldo derivado a partir de lotes/entradas disponíveis, sem coluna de saldo editável como autoridade.  
  - Dependências: P3-06; P3-14.  
  - Evidência: `quantidadeEstoque` (soma de `quantidadeRestante` das ENTRADAS, como no contrato) e `saldoValido` (exclui lotes com validade < hoje em SP) são `column_property` somente leitura; `precisaReposicao` derivado. Verificado com lotes vencido/válido/vence-hoje.
- [x] **P3-17** Planejar preservação de histórico de pedidos, itens e movimentações mesmo após desativação lógica de usuários/produtos.  
  - Dependências: P3-02; P3-06; P3-07; P3-10; P3-11; P3-12.  
  - Evidência: Verificado: alterar/desativar produto, desativar usuário e tentativa de excluir pai preservam pedidos, itens e movimentações.
- [x] **P3-18** Definir `database.py` com `Engine`, `SessionLocal`, `get_db`, configuração de conexão SQLite e tratamento de ciclo de sessão.  
  - Dependências: P1-12; P3-01.  
  - Evidência: `database.py`: `create_db_engine`/`get_engine` (lazy), `SessionLocal`, `get_db` (gerador que sempre fecha a sessão), SQLite com `check_same_thread=False`, `StaticPool` em memória e `PRAGMA foreign_keys=ON`. Verificado, inclusive uso em outra thread e fechamento em exceção.
- [ ] **P3-19** Definir inicialização de schema e integração com a estratégia de migrações aprovada.  
  - Situação: **parcial — bloqueado pela decisão 4 (migrações)**. Existe `init_db()` explícita (`metadata.create_all`) restrita a `local`/`test`, recusada em `production` (verificado) e não chamada automaticamente; nenhuma ferramenta de migração foi adotada. A integração com a estratégia aprovada fica pendente.  
  - Dependências: P1-07; P3-12; P3-18.
- [ ] **P3-20** Definir seed inicial somente para dados de referência aprovados/necessários; não criar administrador automaticamente nem contornar `/auth/administrador`.  
  - Situação: **estrutura pronta, aguardando a decisão 5 (lista de dados de referência)**. `seed_reference_data()` é idempotente (verificado: 1ª execução cria, 2ª não duplica, não sobrescreve edições) e `UNIDADES_MEDIDA_REFERENCIA` está **vazia** de propósito: não há lista aprovada, então nada é inserido. Não cria usuários/administrador, nem `aluno@fatec.sp.gov.br`, nem perfis `ADMIN`/`MEMBER`.  
  - Dependências: P3-18; P3-19.
- [x] **P3-21** Definir banco SQLite isolado para testes (memória ou arquivo temporário), sem compartilhar o banco de desenvolvimento.  
  - Dependências: P3-18.  
  - Evidência: Teste usa `sqlite:///:memory:` (recusa o arquivo de dev); dois engines de teste independentes; `mente_fria.db` não é criado.
- [x] **P3-22** Planejar testes de modelos, relacionamentos, constraints, integridade referencial e preservação de histórico.  
  - Dependências: P3-02 a P3-21.  
  - Evidência: `verify_models.py` (raiz): 122 verificações OK, sem substituir a suíte pytest da Fase 6 (P6-20 e correlatas).

### Critérios de aceite

- [x] Nove grupos de entidades do domínio estão modelados e relacionados com SQLAlchemy 2.0.
- [x] Constraints e FKs preservam integridade e histórico; exclusões seguem regras de conflito/desativação.
- [x] Valores monetários/decimais usam Decimal/Numeric e saldo de estoque é derivado. *(saldo derivado e `Decimal` verificados; precisão física aprovada em 2026-11-17 — P3-14/decisão 6)*
- [ ] Engine, SessionLocal, get_db, inicialização, seed compatível com bootstrap e banco isolado de testes estão definidos. *(Engine, SessionLocal, `get_db` e banco de testes verificados; inicialização depende da decisão 4 e o seed, da decisão 5 — P3-19/P3-20)*

### Decisões da Fase 3 a validar na revisão humana

1. **Nomes físicos:** tabelas conforme SPEC §4.1 (`usuarios`, `clientes`, `unidades_medida`, `ingredientes`, `movimentacoes_estoque`, `produtos`, `composicoes_produto`, `pedidos`, `itens_pedido`); colunas em `snake_case`; **atributos Python dos campos do contrato em camelCase** (iguais ao JSON), para que os schemas com `from_attributes=True` e sem aliases (P2-56) leiam o ORM diretamente. `senha_hash` é atributo interno e não existe em nenhum schema.
2. **`Numeric`** (decisão 6): `(10,2)` dinheiro, `(10,3)` quantidades, `(15,2)` total/subtotal. O SQLite guarda `Numeric` como número de ponto flutuante; os valores verificados voltam exatos como `Decimal`, mas valores com mais de ~15 dígitos significativos perderiam precisão — por isso o teto de 15 dígitos em totais.
3. **`ON DELETE`:** `RESTRICT` em todas as FKs de dado histórico/referenciado (inclui `pedidos.cliente_id`, que **nunca** vira `SET NULL`); única cascata destrutiva: `composicoes_produto.produto_id` (`CASCADE` + `delete-orphan`), pois a composição não é histórico e a substituição é integral.
4. **`PedidoItemModel` com PK substituta** (`id`, interna): o contrato não proíbe o mesmo produto em mais de uma linha, então não foi imposta unicidade `(pedido, produto)`.
5. **Saldo:** `quantidadeEstoque` = soma de `quantidadeRestante` das ENTRADAS (descrição do contrato); `saldoValido` exclui lotes vencidos e alimenta `precisaReposicao`. **Premissa a confirmar na Fase 5:** lote com validade == hoje (data de São Paulo) ainda é válido; vencido = validade < hoje. Ambos refletem o banco: após escritas, a sessão precisa reler o ingrediente (o `commit` já expira os objetos).
6. **Datas:** `TimestampTZ` grava UTC e devolve `America/Sao_Paulo`; recusa `datetime` sem fuso (Decisão 1 da Fase 2 aceitava datas sem fuso na entrada; services devem sempre gravar com fuso, ex.: `models.agora()`). Em Windows, `zoneinfo` exige o pacote `tzdata` (adicionado ao `requirements.txt` só para `win32`).
7. **`CHECK`s de domínio** além do contrato HTTP (defesa em profundidade): perfil, tipo/motivo, status, limites mínimos, coerência de lote (ENTRADA/SAÍDA) e de cancelamento (dados de cancelamento só em `CANCELADO`).
8. **`dataValidade` anulável no banco** (o DTO a exige em ENTRADA, mas a SPEC §6.3 a chama de opcional; a regra fica nos services/Fase 5). Lotes sem validade contam como válidos.
9. **`quantidadeMinima`** omitida no cadastro assume `0` (o contrato a torna opcional no DTO, mas obrigatória na resposta).
10. **`observacaoCancelamento`** é persistida (campo do `CancelamentoPedidoDTO`), mas não faz parte do schema `Pedido`.
11. **E-mail:** `UNIQUE` exato (sensível a maiúsculas/minúsculas); normalização (ex.: minúsculas) é decisão de service na Fase 4. → **Resolvida na Fase 4** (decisão 4 da Fase 4): normalização para minúsculas no cadastro e na busca de login.
12. **Engine preguiçosa e sem `create_all` automático:** `database.py` não cria nada ao ser importado e `init_db()` só roda quando chamada (e não em `production`). **Não foi ligada ao `lifespan` do `main.py`** (fora do escopo desta fase).

## Fase 4 — Segurança, autenticação e tratamento de erros

**Total de tarefas: 18** — **concluídas e verificadas: 18** (decisões 2 e 3 aprovadas na revisão humana de 2026-11-17)

### Checklist sequencial

- [x] **P4-01** Selecionar e registrar algoritmo de hash de senha resistente (preferencialmente Argon2id), parâmetros e formato de armazenamento; nunca armazenar senha em texto puro.  
  - Dependências: P1-06; P1-09.  
  - Evidência: **decisão 2 aprovada em 2026-11-17** — Argon2id via `argon2-cffi` 25.1.0 (`PasswordHasher`). Parâmetros registrados em `security.PARAMETROS_HASH`: `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`. Formato de armazenamento: string PHC completa (`$argon2id$v=19$m=65536,t=3,p=4$...`), que já embute sal e custos, em `usuarios.senha_hash` (`String(255)`). Verificado: hash não contém a senha, custos gravados conferem com `PARAMETROS_HASH`, versão `v=19`, sal aleatório (dois hashes da mesma senha diferem).
- [x] **P4-02** Definir funções de hash e verificação de senha, incluindo tratamento seguro de hash inválido.  
  - Dependências: P4-01.  
  - Evidência: `gerar_hash_senha` e `verificar_senha` em `security.py`. `verificar_senha` devolve `False` — sem exceção e sem revelar o motivo ao cliente — para senha errada e para hash vazio, `None`, lixo, formato bcrypt, argon2 truncado, **fora do ASCII** e `bytes`. Os dois últimos casos surgiram da verificação: `argon2-cffi` levanta `UnicodeEncodeError`/`TypeError` antes de analisar o formato, e o tratamento foi ampliado para `(ValueError, TypeError)`. `precisa_rehash` também é tolerante a hash inválido.
- [x] **P4-03** Implementar emissão e validação JWT com PyJWT, `HS256` conforme SPEC.md e claims estritamente necessários à identidade/perfil.  
  - Dependências: P1-09; P4-02.  
  - Evidência: `criar_token_acesso`/`decodificar_token` com PyJWT 2.15.1 e `HS256` lido de `config.jwt_algorithm` (`Literal["HS256"]`). Claims exatamente `sub` (id), `perfil`, `iat` e `exp` — verificado que o conjunto é só esse e que o token não embute e-mail nem hash. Recusados com `401`: expirado, assinatura de outra chave, `HS512`, `alg=none` (token sem assinatura), `exp` ausente, token adulterado e texto arbitrário.
- [x] **P4-04** Definir expiração JWT configurável por ambiente sem inventar prazo público fixo; garantir retorno coerente de `expiresInSeconds`.  
  - Dependências: P1-09; P4-03.  
  - Evidência: **decisão 3 aprovada em 2026-11-17** — 3600 s em desenvolvimento, sempre vindo de `MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS` (obrigatória, sem padrão no código; `Field(ge=1)`). Nenhum prazo fixo foi escrito no código. Verificado com 60 s: `exp - iat == 60` e `AuthToken.expiresInSeconds == 60` (`montar_auth_token`).
- [x] **P4-05** Configurar esquema HTTP Bearer e dependência `get_current_user` para validar assinatura, expiração e usuário ativo.  
  - Dependências: P4-03; P3-02; P3-18.  
  - Evidência: `HTTPBearer(bearerFormat="JWT", auto_error=False)` — `auto_error=False` para que a resposta seja `401` no envelope `ApiError`, e não o `403`/`{"detail": ...}` que o próprio `HTTPBearer` emitiria. `get_current_user` valida, em ordem: cabeçalho presente, assinatura/expiração, `sub` numérico, usuário existente e `ativo`. Verificado `401` para: sem cabeçalho, credencial vazia, `sub` não numérico, usuário inexistente, conta inativa e conta desativada **depois** da emissão do token.
- [x] **P4-06** Implementar mecanismo `require_role`/restrição de perfil apenas onde a descrição da operação exige perfil específico.  
  - Dependências: P4-05.  
  - Evidência: `require_role(*perfis)` devolve dependência que exige um dos perfis e levanta `403` caso contrário; recusa perfis fora do domínio com `ValueError` (verificado com `ADMIN`). Atalhos `somente_administrador` e `administrador_ou_funcionario`. Verificado: `ADMINISTRADOR` passa, `FUNCIONARIO` recebe `403` em rota administrativa, a mensagem do `403` não revela o perfil exigido, e ambos passam onde o contrato libera os dois.
- [x] **P4-07** Traduzir a matriz RBAC operação por operação a partir de `security` e descrições OpenAPI; operações apenas autenticadas não recebem restrição de papel inventada.  
  - Dependências: P4-06.  
  - Evidência: `security.MATRIZ_RBAC` cobre as **44 operações** dos **26 caminhos**, por `operationId`: **3 públicas** (`security: []`), **27 somente `ADMINISTRADOR`**, **5 para ambos os perfis** (clientes) e **9 apenas autenticadas** (`None`, sem restrição inventada): movimentações de estoque (3), pedidos (4) e alertas (2). `verify_security.py` compara a matriz com o contrato operação por operação: públicas × `security: []`, protegidas × `bearerAuth` + `401`/`403` declarados, e a restrição de perfil × a descrição de cada operação. `dependencia_de_autorizacao(operationId)` é o ponto de uso dos routers da Fase 5 e recusa operação fora do contrato.
  - Atenção: `cadastrarFuncionario` é **somente `ADMINISTRADOR`** — a descrição cita `FUNCIONARIO` apenas como o perfil *atribuído* pelo servidor ("o perfil é definido pelo servidor como FUNCIONARIO; somente ADMINISTRADOR pode cadastrar funcionários"). A tabela §5.2 do SPEC.md já dizia isso ("/usuarios — ADMINISTRADOR"); busca por palavra-chave na descrição produz falso positivo.
- [x] **P4-08** Implementar bootstrap transacional do primeiro administrador: público, permitido somente quando não existir administrador e conflito `409` após bootstrap.  
  - Dependências: P3-02; P4-02; P4-07.  
  - Evidência: `criar_conta_administrador` verifica a ausência de administrador, insere e **reconta na mesma transação** após o `flush` (que toma a trava de escrita do SQLite); se a contagem não for 1, faz `rollback` e levanta `409`. `IntegrityError` de e-mail duplicado também vira `409`, com `rollback`. Verificado: 1º bootstrap cria `ADMINISTRADOR` ativo com senha só em hash; 2º bootstrap (outro e-mail) recebe `409` e o banco segue com **um único** administrador. **Concorrência real verificada**: duas threads, e-mails distintos, banco SQLite em arquivo temporário (o banco em memória compartilha uma só conexão e não exercitaria a trava) → exatamente 1 sucesso, 1 `409`, 1 administrador; estável em 4 execuções consecutivas.
- [x] **P4-09** Implementar login público: verificar credenciais e estado ativo; retornar `401` para credenciais inválidas ou conta inativa.  
  - Dependências: P2-58; P3-02; P4-02; P4-03.  
  - Evidência: `autenticar(db, LoginDTO)` busca por e-mail normalizado, verifica a senha e então o estado ativo. `401` com **a mesma mensagem** ("Credenciais inválidas ou conta inativa.") para senha errada, e-mail inexistente e conta inativa — verificado que as três mensagens são idênticas, de modo a não revelar a existência da conta. Quando o e-mail não existe, uma verificação contra hash de referência é executada para que o tempo de resposta não denuncie a ausência do cadastro. `montar_auth_token` devolve `AuthToken` com `tokenType="Bearer"` e `usuario` sem senha/hash (verificado no JSON serializado).
- [x] **P4-10** Garantir cadastro comum de usuário com perfil `FUNCIONARIO` definido no servidor; nunca aceitar perfil arbitrário do DTO.  
  - Dependências: P2-58; P3-02; P4-07.  
  - Evidência: `cadastrar_funcionario` fixa `perfil=FUNCIONARIO` no servidor; `CreateFuncionarioDTO` não possui campo de perfil e, por `additionalProperties: false` (`extra="forbid"`), **recusa** `perfil` enviado pelo cliente (verificado com `ValidationError`). E-mail duplicado — inclusive em outra caixa — resulta em `409` com `rollback`, e a sessão segue utilizável.
- [x] **P4-11** Definir exceções de domínio para não encontrado, conflito, validação, não autorizado, proibido e indisponibilidade de dependência.  
  - Dependências: P2-59.  
  - Evidência: `exceptions.py` define `ApiException` (base, com `status_code`, `codigo` e `detalhes`) e as subclasses `RequisicaoInvalidaError` (400), `NaoAutenticadoError` (401), `ProibidoError` (403), `NaoEncontradoError` (404), `ConflitoError` (409), `ValidacaoError` (422) e `DependenciaIndisponivelError` (503). Nenhum status fora dos declarados no contrato.
- [x] **P4-12** Implementar handlers globais para erros HTTP e exceções, serializando o envelope `ApiError`/`ApiErrorDetail`.  
  - Dependências: P4-11; P2-59.  
  - Evidência: `registrar_handlers(app)` registra handlers para `ApiException`, `RequestValidationError`, `ResponseValidationError`, `StarletteHTTPException` e `Exception`; chamado por `main.create_app` (6 handlers na aplicação real). Verificado para 400, 401, 403, 404, 409, 422 e 503: status correto, envelope com **exatamente** `codigo`, `mensagem`, `detalhes`, `timestamp`, `caminho` e `correlationId`, validando contra o schema `ApiError`, **sem** `detail` do FastAPI e **sem** `type`/`title`/`status`/`instance` de RFC 9457. `404` de rota inexistente e `405` de método não permitido também saem como `ApiError`. Códigos estáveis por status: `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`.
- [x] **P4-13** Converter erros de validação do FastAPI/Pydantic em `ApiError` com detalhes úteis por campo e status contratual `422`.  
  - Dependências: P4-12; P2-59.  
  - Evidência: `validation_exception_handler` converte cada erro do Pydantic em `ApiErrorDetail` com `campo` (caminho do campo, sem o prefixo `body`/`query`), `mensagem` e `valorRejeitado`. Verificado: corpo com campo inválido → `422` com `campo="preco"` e `valorRejeitado="0"`. **Sigilo verificado**: o valor de campo sensível (`senha`) **não** aparece em `valorRejeitado` — senha curta gera `422` com `campo="senha"` e a senha não consta da resposta; valores não escalares (dict/list) nunca são ecoados, para que um corpo inteiro com senha não vaze.
- [x] **P4-14** Mapear erros de requisição malformada para `400` somente nas operações que declaram esse status, sem converter indiscriminadamente erros de validação.  
  - Dependências: P4-12.  
  - Evidência: o handler classifica a origem (corpo ilegível > parâmetro de caminho > parâmetro de consulta > campo do corpo) e usa o **primeiro status que a operação declara**, consultando `route.responses` + `route.status_code` (`_CANDIDATOS` em `exceptions.py`). Verificado: campo do corpo inválido em operação que declara 400 **e** 422 → `422`; corpo ilegível em operação que declara 400 → `400`, sem ecoar o conteúdo enviado; corpo ilegível em operação que declara só 422 → `422`; parâmetro de consulta incompatível em operação que declara 400 → `400` com o nome do parâmetro no detalhe; parâmetro de caminho inválido em operação que declara só 404 → `404`; o mesmo caso em operação que declara 400 → `400`; caminho inválido tem precedência sobre consulta inválida; sem nenhum candidato declarado → `422` (padrão documentado, com aviso em log). Requisição válida não é afetada.
- [x] **P4-15** Mapear `401`, `403`, `404`, `409` e `503` para `ApiError`, respeitando a resposta declarada em cada operação.  
  - Dependências: P4-12; P4-07.  
  - Evidência: cada exceção de domínio carrega o próprio status e as mensagens padrão espelham as `description` de `components.responses` do contrato (`BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `ValidationError`, `InternalError`, `ServiceUnavailable`). Verificado status a status na seção [7] de `verify_security.py`.
- [x] **P4-16** Planejar `correlationId`, timestamp e caminho da requisição no envelope de erro, sem expor segredos ou dados internos.  
  - Dependências: P4-12.  
  - Evidência: `construir_api_error` preenche `timestamp` com `models.agora()` (ISO 8601 com `-03:00`), `caminho` com `request.url.path` (sem query string, truncado em 300) e `correlationId` com UUID4, repetido no log para rastreio. Todos os limites do schema são respeitados por truncagem (`codigo` 80, `mensagem` 500, `campo` 100, `valorRejeitado` 500). Exceção não tratada → `500` `INTERNAL_ERROR`: verificado que a resposta **não** contém a mensagem interna, `Traceback` nem o nome da exceção (o diagnóstico vai só para o log, já filtrado por `RedactingFilter`). Mensagens e detalhes passam por `config.redact`.
- [x] **P4-17** Garantir que respostas `204` sejam emitidas sem corpo e sem serialização de schema JSON.  
  - Dependências: P4-12.  
  - Evidência: `resposta_sem_conteudo()` devolve `Response(status_code=204)` cru, para uso pelas cinco operações que declaram 204 na Fase 5; o handler de `HTTPException` também devolve `204` sem corpo. Verificado: `content == b""` e nenhum `Content-Type` de JSON na resposta.
- [x] **P4-18** Planejar testes de hash, JWT válido/inválido/expirado, conta inativa, bootstrap concorrente e matriz RBAC.  
  - Dependências: P4-01 a P4-17.  
  - Evidência: `verify_security.py` (raiz) — **305 verificações OK, 0 falhas**, em 8 blocos: hash, JWT, `get_current_user`, `require_role`, matriz RBAC × OpenAPI, bootstrap/login/cadastro (inclusive concorrência real com threads), handlers do `ApiError` e aplicação real. **Não substitui** a suíte pytest da Fase 6: os casos aqui são o roteiro a transcrever em `test_auth.py` e `test_errors.py` (P6).

### Critérios de aceite

- [x] Hash seguro, JWT PyJWT/HS256 e HTTP Bearer estão definidos com segredo/expiração configuráveis.
- [x] Bootstrap cria somente o primeiro administrador; login valida conta ativa; cadastro comum atribui FUNCIONARIO.
- [x] RBAC reproduz a matriz de cada operação, sem restrição adicional não documentada.
- [x] Handlers retornam ApiError para os status contratados; 204 não contém corpo.

### Decisões da Fase 4 a validar na revisão humana

1. **Códigos de erro (`codigo`):** o contrato define `codigo` como string livre (até 80) e só exemplifica `VALIDATION_ERROR`. Adotado um código estável por status, nomeado como o componente de resposta correspondente do OpenAPI: `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `INTERNAL_ERROR` e `SERVICE_UNAVAILABLE`.
2. **Classificação 400 × 422 × 404:** o contrato distingue *requisição malformada ou parâmetros incompatíveis* (400) de *dados compreendidos que violam validação* (422), mas não diz qual usar em cada tipo de falha, e 15 operações não declaram nenhum dos dois. Regra adotada: o handler usa o **primeiro status que a própria operação declara**, percorrendo candidatos em ordem de precisão por origem do erro — corpo ilegível `400→422`; parâmetro de caminho `400→404→422`; parâmetro de consulta `400→422`; campo do corpo `422→400`. Detalhada em "Decisão sobre parâmetros sem `400`/`422` declarados", adiante.
3. **`valorRejeitado` só para escalares de campos não sensíveis:** campos cujo nome contenha `senha`, `token`, `secret`, `hash` etc. nunca têm o valor ecoado, e valores não escalares (dict/list) também não — um corpo inteiro poderia conter a senha.
4. **Normalização de e-mail (resolve a decisão 11 da Fase 3):** e-mail gravado e consultado em **minúsculas**, sem espaços nas pontas, no bootstrap, no cadastro e na busca de login. A coluna segue com `UNIQUE` exato; a normalização evita contas duplicadas que difiram apenas por caixa.
5. **Mensagem única no `401` de login:** senha errada, e-mail inexistente e conta inativa devolvem a mesma mensagem, e o caso de e-mail inexistente executa uma verificação de hash de referência para igualar o tempo de resposta. Consequência aceita: o cliente não distingue "conta inativa" de "senha errada".
6. **`precisa_rehash` no login:** se o hash foi gerado com parâmetros antigos, ele é regravado no login bem-sucedido. Nenhum efeito sobre o contrato.
7. **Localização dos fluxos de autenticação:** `criar_conta_administrador`, `autenticar` e `cadastrar_funcionario` ficaram em `security.py`, não em `services/`, porque P4-08/P4-09/P4-10 pertencem a esta fase e `services/usuarios.py` só é previsto em P5-02. Na Fase 5 podem ser movidos para o service de usuários/autenticação sem mudança de comportamento.
8. **Sem cabeçalho `WWW-Authenticate` no `401`:** a resposta `Unauthorized` do contrato não declara cabeçalho algum, então nenhum foi acrescentado, embora seja o usual em HTTP Bearer. Reverter é trivial se a revisão preferir o cabeçalho.

### Decisão sobre parâmetros sem `400`/`422` declarados (divergência de contrato resolvida sem alterar o OpenAPI)

**O gap.** **15 operações declaram parâmetros (path/query) mas não declaram nem `400` nem `422`**, de modo que o contrato não diz o que responder quando o parâmetro é incompatível — por exemplo `GET /api/v1/usuarios/{id}` com `id=0`, abaixo do `minimum: 1` definido pelo próprio contrato.

**Decisão adotada em 2026-11-17 (autorizada na revisão humana):** usar **somente status que a operação já declara**, sem tocar no `Mente Fria API.openapi.json`.

| Origem do erro | Status, em ordem de precisão |
|---|---|
| Corpo ilegível/ausente | `400` → `422` |
| **Parâmetro de caminho** | `400` → **`404`** → `422` |
| Parâmetro de consulta/cabeçalho | `400` → `422` |
| Campo do corpo | `422` → `400` |

Vale o **primeiro status que a operação declarar**. O `404` entra como opção para parâmetro de caminho porque um identificador que viola o contrato não pode designar recurso algum, e "Recurso não encontrado" é resposta declarada nas 13 operações de leitura/exclusão por id que compõem o gap. Parâmetro de caminho tem precedência sobre o de consulta: se o recurso não é identificável, o resto da requisição não importa.

**Efeito medido no contrato real** (verificado em `verify_security.py`, bloco [5]):

- **13 das 15** operações passam a responder `404` — status **declarado** por elas: `consultarUsuario`, `desativarUsuario`, `consultarCliente`, `excluirCliente`, `consultarUnidadeMedida`, `excluirUnidadeMedida`, `consultarIngrediente`, `excluirIngrediente`, `listarMovimentacoesDoIngrediente`, `consultarProduto`, `desativarProduto`, `consultarComposicaoProduto`, `consultarPedido`.
- **Gap residual: 2 operações**, ambas com parâmetros apenas de consulta e sem `404` aplicável — `listarUnidadesMedida` e `listarAlertasReposicao` (ex.: `size=500` contra o máximo 100). Respondem `422`, com aviso em log. Aqui o `404` seria semanticamente errado: o recurso existe, o filtro é que não serve.

**Por que não as outras duas opções:**

- *Acrescentar `400` às 15 operações no OpenAPI* resolveria o gap por completo, mas altera o contrato normativo — vedado por AGENTS.md §2 e §5 e pela regra 12 da Fase 5 ("não altere schemas ou OpenAPI para facilitar a implementação"). O contrato é o artefato avaliado na entrega; mantê-lo intacto vale mais do que fechar um gap de 2 operações.
- *Aceitar `422` em todas as 15* era o comportamento anterior: simples, porém emitia status fora do contrato em 15 operações, inclusive onde havia um status declarado e adequado. A decisão atual reduz isso a 2.

**Consequências para as fases seguintes:**

- **Fase 5:** ao declarar `responses` nos routers, copiar exatamente os status do contrato — é essa declaração que o handler consulta. Não acrescentar `400`/`422` a operação que não os declare, pois isso mudaria a resposta.
- **Fase 6:** testar `id` inválido (`0`, negativo) esperando `404` nas 13 operações, e `422` nas 2 de consulta. O log de aviso nessas 2 é esperado, não é falha.
- **Reversível:** a tabela vive em `_CANDIDATOS` (`exceptions.py`); retirar o `404` da linha de caminho devolve o comportamento anterior sem outras mudanças.

### Evidências da execução (Fase 4)

Ambiente: Python 3.14.0 (`.venv` novo a partir de `src/api/requirements.txt`), FastAPI 0.163.2, Pydantic 2.14.3, SQLAlchemy 2.1.9, PyJWT 2.15.1, argon2-cffi 25.1.0, ruff 0.17.5; SQLite em memória e em arquivo temporário.

| Verificação | Resultado |
|---|---|
| Importação dos módulos de `src.api` (29, exceto testes) | OK |
| Hash Argon2id: formato PHC, custos gravados, `v=19`, sal aleatório, senha não exposta | OK |
| Hash inválido (vazio, `None`, lixo, bcrypt, truncado, fora do ASCII, `bytes`) → `False` sem exceção | OK |
| JWT: claims mínimos, `exp - iat` = expiração configurada, `HS256` no header, sem e-mail/hash no token | OK |
| JWT recusado: expirado, outra chave, `HS512`, `alg=none`, sem `exp`, adulterado, texto arbitrário | OK (401) |
| `get_current_user`: sem cabeçalho, credencial vazia, `sub` inválido, inexistente, inativo, desativado após emissão | OK (401) |
| `require_role`: `ADMINISTRADOR` passa, `FUNCIONARIO` → 403, ambos passam onde liberado, `ADMIN` recusado | OK |
| Matriz RBAC × OpenAPI: 26 caminhos, 44 operações, 3 públicas, 27 ADMINISTRADOR, 5 ambos, 9 só autenticadas | OK |
| Bootstrap: 1º cria admin, 2º → 409, único administrador no banco | OK |
| Bootstrap **concorrente** (2 threads, banco em arquivo): 1 sucesso, 1 conflito 409, 1 administrador | OK (4 execuções) |
| Login: válido, outra caixa de e-mail, senha errada, e-mail inexistente, conta inativa (mesma mensagem) | OK |
| Cadastro: perfil sempre `FUNCIONARIO`; DTO recusa `perfil` do cliente; e-mail duplicado → 409 | OK |
| Handlers: 400/401/403/404/409/422/503 no envelope `ApiError`, sem `detail` e sem RFC 9457 | OK |
| Classificação 400 × 422 × 404 conforme o que a operação declara (12 cenários) | OK |
| Gap de parâmetros: 13 operações resolvidas por `404` declarado; residual de 2 (consulta) | OK |
| Sigilo: senha não aparece em `valorRejeitado`; 500 sem stack trace, sem mensagem interna | OK |
| `204` sem corpo e sem `Content-Type` de JSON | OK |
| Aplicação real: 6 handlers, `GET /api/v1/auth/me` → 404 em `ApiError`, 0 rotas de negócio | OK |
| `python verify_security.py` | **305 verificações OK, 0 falhas** (estável em 4 execuções) |
| `python verify_models.py` (regressão da Fase 3) | 122 verificações OK |
| `python verify_schemas.py --openapi "Mente Fria API.openapi.json"` (regressão da Fase 2) | 5 976 verificações OK |
| `ruff check src verify_security.py` | OK (sem avisos) |

## Fase 5 — Services, routers e integração da API

**Total de tarefas: 68** — **não iniciada**

### Checklist sequencial

- [ ] **P5-01** Definir contratos internos de services e dependências de sessão para manter regras de negócio fora dos routers.  
  - Dependências: P2-57; P3-18; P4-12.
- [ ] **P5-02** Planejar services de usuários/autenticação, clientes, unidades, ingredientes, produtos, alertas, marketing e dashboard.  
  - Dependências: P5-01.
- [ ] **P5-03** Implementar service de estoque: saldo derivado, lotes, validade, entradas, saídas, quantidade restante e auditoria.  
  - Dependências: P3-06; P3-16; P4-05.
- [ ] **P5-04** Implementar consumo FEFO: selecionar primeiro os lotes não vencidos com menor data de validade e impedir consumo de lote vencido.  
  - Dependências: P5-03.
- [ ] **P5-05** Implementar service de pedidos com captura de preços vigentes, cálculo Decimal de subtotais/total e validação de estoque.  
  - Dependências: P3-10; P3-11; P5-03; P5-04.
- [ ] **P5-06** Garantir transação atômica do pedido, itens e baixas de estoque, com rollback integral em falha.  
  - Dependências: P5-05.
- [ ] **P5-07** Implementar cancelamento: alterar status, registrar data/usuário/observação conforme contrato e não repor estoque automaticamente.  
  - Dependências: P5-05; P5-06.
- [ ] **P5-08** Implementar service de recomendações e integração em `integrations/optimizer.py` para solver de Programação Linear Inteira.  
  - Dependências: P3-05; P3-07; P3-08; P5-01.
- [ ] **P5-09** Implementar recomendação de produção maximizando lucro estimado, com quantidades inteiras e estoque válido, conforme SPEC.md.  
  - Dependências: P5-08; P5-03; P5-04.
- [ ] **P5-10** Implementar recomendação de reposição sob período e orçamento informados, sem persistir histórico.  
  - Dependências: P5-08; P5-03.
- [ ] **P5-11** Mapear indisponibilidade do solver/dependência para `503` com `ApiError` quando aplicável.  
  - Dependências: P5-08; P4-15.
- [ ] **P5-12** Implementar alertas de reposição usando saldo válido abaixo da quantidade mínima.  
  - Dependências: P5-03.
- [ ] **P5-13** Implementar alertas de validade a partir de lotes com validade, classificando próximos do vencimento e vencidos.  
  - Dependências: P5-03; P5-04.
- [ ] **P5-14** Implementar sugestões de marketing informativas sob demanda, sem publicação automática nem persistência de histórico.  
  - Dependências: P5-01.
- [ ] **P5-15** Implementar dashboard por período, considerando apenas pedidos `ATIVO` nos indicadores financeiros e ranking.  
  - Dependências: P3-10; P3-11; P5-05; P5-07; P5-12; P5-13.
- [ ] **P5-16** Implementar exportação CSV UTF-8 com as mesmas regras de período e inclusão de pedidos ativos; responder como `text/csv`, não JSON.  
  - Dependências: P5-15; P2-61.
- [ ] **P5-17** Definir consultas paginadas e filtros individualmente conforme parâmetros de cada operação; não aplicar filtros globais não contratados.  
  - Dependências: P2-57; P3-18.
- [ ] **P5-18** Definir ordenação `sort` com lista permitida por recurso, respeitando o formato `campo,direção` e sem interpolar SQL não confiável.  
  - Dependências: P5-17.
- [ ] **P5-19** Planejar carregamento com `selectinload`/`joinedload` nas relações retornadas e verificar ausência de N+1.  
  - Dependências: P3-12; P5-01.
- [ ] **P5-20** Implementar `GET /api/v1/saude` — `consultarSaude` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-21** Implementar `POST /api/v1/auth/administrador` — `criarContaAdministrador` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-22** Implementar `POST /api/v1/auth/login` — `autenticarUsuario` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-23** Implementar `GET /api/v1/usuarios` — `listarUsuarios` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-24** Implementar `POST /api/v1/usuarios` — `cadastrarFuncionario` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-25** Implementar `GET /api/v1/usuarios/{id}` — `consultarUsuario` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-26** Implementar `PATCH /api/v1/usuarios/{id}` — `atualizarUsuario` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-27** Implementar `DELETE /api/v1/usuarios/{id}` — `desativarUsuario` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-28** Implementar `GET /api/v1/clientes` — `listarClientes` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-29** Implementar `POST /api/v1/clientes` — `cadastrarCliente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-30** Implementar `GET /api/v1/clientes/{id}` — `consultarCliente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-31** Implementar `PUT /api/v1/clientes/{id}` — `atualizarCliente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-32** Implementar `DELETE /api/v1/clientes/{id}` — `excluirCliente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-33** Implementar `GET /api/v1/unidades-medida` — `listarUnidadesMedida` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-34** Implementar `POST /api/v1/unidades-medida` — `cadastrarUnidadeMedida` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-35** Implementar `GET /api/v1/unidades-medida/{unidadeMedida}` — `consultarUnidadeMedida` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-36** Implementar `PUT /api/v1/unidades-medida/{unidadeMedida}` — `atualizarUnidadeMedida` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-37** Implementar `DELETE /api/v1/unidades-medida/{unidadeMedida}` — `excluirUnidadeMedida` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-38** Implementar `GET /api/v1/ingredientes` — `listarIngredientes` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-39** Implementar `POST /api/v1/ingredientes` — `cadastrarIngrediente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-40** Implementar `GET /api/v1/ingredientes/{id}` — `consultarIngrediente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-41** Implementar `PUT /api/v1/ingredientes/{id}` — `atualizarIngrediente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-42** Implementar `DELETE /api/v1/ingredientes/{id}` — `excluirIngrediente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-43** Implementar `GET /api/v1/ingredientes/{id}/movimentacoes` — `listarMovimentacoesDoIngrediente` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-44** Implementar `GET /api/v1/movimentacoes-estoque` — `listarMovimentacoesEstoque` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-45** Implementar `POST /api/v1/movimentacoes-estoque` — `registrarMovimentacaoEstoque` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-46** Implementar `GET /api/v1/produtos` — `listarProdutos` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-47** Implementar `POST /api/v1/produtos` — `cadastrarProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-48** Implementar `GET /api/v1/produtos/{id}` — `consultarProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-49** Implementar `PUT /api/v1/produtos/{id}` — `atualizarProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-50** Implementar `DELETE /api/v1/produtos/{id}` — `desativarProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-51** Implementar `GET /api/v1/produtos/{id}/composicao` — `consultarComposicaoProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-52** Implementar `PUT /api/v1/produtos/{id}/composicao` — `substituirComposicaoProduto` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-53** Implementar `GET /api/v1/pedidos` — `listarPedidos` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-54** Implementar `POST /api/v1/pedidos` — `registrarPedido` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-55** Implementar `GET /api/v1/pedidos/{id}` — `consultarPedido` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-56** Implementar `POST /api/v1/pedidos/{id}/cancelamento` — `cancelarPedido` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-57** Implementar `GET /api/v1/alertas/reposicao` — `listarAlertasReposicao` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-58** Implementar `GET /api/v1/alertas/validade` — `listarAlertasValidade` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-59** Implementar `POST /api/v1/recomendacoes/producao` — `calcularRecomendacaoProducao` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-60** Implementar `POST /api/v1/recomendacoes/reposicao` — `calcularRecomendacaoReposicao` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-61** Implementar `POST /api/v1/sugestoes-marketing` — `gerarSugestoesMarketing` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-62** Implementar `GET /api/v1/dashboard` — `consultarDashboard` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-63** Implementar `GET /api/v1/dashboard/exportacao` — `exportarDashboardCsv` — preservando parâmetros, request body, status/respostas, headers, media types e `security` exatamente como definidos no OpenAPI.  
  - Dependências: P5-01 a P5-19; P2-57; P4-07.
- [ ] **P5-64** Criar routers por domínio: `saude.py`, `auth.py`, `usuarios.py`, `clientes.py`, `unidades_medida.py`, `ingredientes.py`, `movimentacoes_estoque.py`, `produtos.py`, `pedidos.py`, `alertas.py`, `recomendacoes.py`, `sugestoes_marketing.py` e `dashboard.py`.  
  - Dependências: P5-01 a P5-63.
- [ ] **P5-65** Registrar todos os routers no `main.py` sob o prefixo `/api/v1`, mantendo a rota pública de saúde e as rotas públicas de autenticação.  
  - Dependências: P1-15; P5-64.
- [ ] **P5-66** Conferir que os 26 path keys e as 44 operações HTTP estão registrados uma única vez, com `operationId` e tags corretos.  
  - Dependências: P5-20 a P5-65.
- [ ] **P5-67** Conferir status e corpo de todas as respostas, incluindo `204` sem corpo, `201` e header `Location` quando declarado, CSV e `503`.  
  - Dependências: P5-20 a P5-66.
- [ ] **P5-68** Conferir a matriz de autenticação e RBAC final contra cada operação OpenAPI, sem criar endpoints adicionais (incluindo `/auth/me`).  
  - Dependências: P4-07; P5-20 a P5-66.

### Critérios de aceite

- [ ] Services separam domínio/HTTP e cobrem estoque, FEFO, pedidos, recomendações, alertas, marketing, dashboard e CSV.
- [ ] As 44 operações dos 26 caminhos estão implementadas com operationId, parâmetros, schemas, respostas e security do OpenAPI.
- [ ] Pedido e baixas são atômicos; cancelamento não repõe estoque; preços históricos são preservados.
- [ ] Todos os routers estão registrados; carregamento evita N+1; indisponibilidade de solver resulta em 503 quando aplicável.

## Fase 6 — Suíte de testes e validação

**Total de tarefas: 26** — **não iniciada**

### Checklist sequencial

- [ ] **P6-01** Configurar `pytest`, `TestClient`, `httpx` e opções de execução/descoberta da suíte.  
  - Dependências: P1-06; P3-21.
- [ ] **P6-02** Criar `tests/conftest.py` com banco SQLite isolado, criação/limpeza determinística, overrides de `get_db` e fixtures comuns.  
  - Dependências: P3-21; P6-01.
- [ ] **P6-03** Criar fixtures de usuários ADMINISTRADOR/FUNCIONARIO e tokens JWT para cenários autenticados.  
  - Dependências: P4-03; P4-07; P6-02.
- [ ] **P6-04** Criar `test_saude.py` para saúde da API/banco e indisponibilidade contratual.  
  - Dependências: P5-20; P5-65; P6-02.
- [ ] **P6-05** Criar `test_auth.py` para bootstrap único, login, hash, conta inativa e expiração/invalidade JWT.  
  - Dependências: P4-08; P4-09; P6-03.
- [ ] **P6-06** Criar `test_usuarios.py` para CRUD declarado, perfil FUNCIONARIO, atualização permitida e desativação lógica.  
  - Dependências: P5-20; P6-03.
- [ ] **P6-07** Criar `test_clientes.py` para CRUD, associação opcional a pedido e conflito ao excluir cliente referenciado.  
  - Dependências: P5-20; P6-03.
- [ ] **P6-08** Criar `test_unidades_medida.py` para CRUD, porção padrão e bloqueio de exclusão em uso.  
  - Dependências: P5-20; P6-03.
- [ ] **P6-09** Criar `test_ingredientes.py` para CRUD, estoque inicial zero, saldo derivado e bloqueio de exclusão com composição/histórico.  
  - Dependências: P5-20; P6-03.
- [ ] **P6-10** Criar `test_movimentacoes_estoque.py` para entrada, saída, saldo, validade, quantidade restante, FEFO, lote vencido e auditoria.  
  - Dependências: P5-03; P5-04; P5-20; P6-03.
- [ ] **P6-11** Criar `test_produtos.py` para CRUD, composição válida, substituição integral e preservação de preços históricos.  
  - Dependências: P5-20; P6-03.
- [ ] **P6-12** Criar `test_pedidos.py` para cálculo de preços, transação atômica, estoque insuficiente, baixas FEFO e cancelamento sem reposição.  
  - Dependências: P5-05; P5-06; P5-07; P6-03.
- [ ] **P6-13** Criar `test_alertas.py` para alertas de reposição e validade.  
  - Dependências: P5-12; P5-13; P6-03.
- [ ] **P6-14** Criar `test_recomendacoes.py` para produção, reposição, restrições de entrada e indisponibilidade `503` do solver.  
  - Dependências: P5-08 a P5-11; P6-03.
- [ ] **P6-15** Criar `test_dashboard.py` para período, agregações, exclusão de pedidos cancelados e exportação CSV UTF-8.  
  - Dependências: P5-15; P5-16; P6-03.
- [ ] **P6-16** Criar `test_errors.py` para envelope `ApiError` em `400`, `401`, `403`, `404`, `409`, `422`, `503` e erros internos tratados.  
  - Dependências: P4-12 a P4-17; P6-02.
- [ ] **P6-17** Adicionar testes de validação para todos os 54 schemas, incluindo aliases, limites, enums, formatos e `additionalProperties`.  
  - Dependências: P2-62 a P2-64; P6-01.
- [ ] **P6-18** Adicionar testes de paginação, filtros, ordenação e parâmetros por recurso conforme o OpenAPI.  
  - Dependências: P5-17; P5-18; P6-02.
- [ ] **P6-19** Adicionar testes de RBAC para cada operação, cobrindo `401`, `403` e rotas que exigem apenas autenticação sem restrição adicional de papel.  
  - Dependências: P4-07; P5-68; P6-03.
- [ ] **P6-20** Adicionar testes de integridade referencial, exclusões lógicas, constraints únicas e conflitos `409`.  
  - Dependências: P3-12; P3-13; P5-20; P6-02.
- [ ] **P6-21** Adicionar testes de transação e rollback para falhas durante registro de pedidos e movimentações relacionadas.  
  - Dependências: P5-06; P6-12.
- [ ] **P6-22** Adicionar testes de `204` garantindo corpo vazio e de CSV garantindo media type/encoding corretos.  
  - Dependências: P5-67; P5-16; P6-15.
- [ ] **P6-23** Implementar teste de conformidade automatizada entre OpenAPI e rotas efetivamente registradas: caminhos, métodos, `operationId`, parâmetros, schemas, respostas e segurança.  
  - Dependências: P5-66; P5-67; P5-68; P6-01.
- [ ] **P6-24** Executar a suíte completa com `pytest`, registrar resultados e corrigir falhas dentro do escopo planejado.  
  - Dependências: P6-01 a P6-23.
- [ ] **P6-25** Reexecutar a suíte completa após correções e guardar evidência reproduzível do resultado final.  
  - Dependências: P6-24.
- [ ] **P6-26** Marcar itens/fase como concluídos somente após comprovação de execução e aprovação dos critérios de aceite, conforme AGENTS.md.  
  - Dependências: P6-25.

### Critérios de aceite

- [ ] Fixtures isolam banco e usuários/tokens; os 13 arquivos de teste por domínio estão criados.
- [ ] Schemas, CRUD, filtros, paginação, RBAC, integridade, FEFO, pedidos, alertas, recomendações, dashboard e CSV estão cobertos.
- [ ] Envelope ApiError, códigos HTTP, 204 sem corpo e conformidade OpenAPI estão validados.
- [ ] `pytest` foi executado e aprovado; somente então tarefas e fase podem ser marcadas `[x]`.

## Decisões técnicas que exigem aprovação humana

As escolhas abaixo não são fixadas pelo contrato e devem ser aprovadas antes de se tornarem decisões de implementação. **Situação em 2026-11-17: 2, 3 e 6 aprovadas; 1, 4, 5 e 7 pendentes.** As pendentes 1 (solver), 4 (migrações) e 5 (seed) bloqueiam tarefas da Fase 5 — ver P5-08, P5-66 e P3-19/P3-20.

1. **Solver de Programação Linear Inteira:** selecionar biblioteca/serviço, versão, estratégia de execução e limites operacionais. O contrato e a SPEC definem o objetivo/regras, mas não identificam o fornecedor ou pacote.
2. **Hash de senha:** ~~confirmar Argon2id e a biblioteca Python/parametrização.~~ **APROVADA em 2026-11-17:** Argon2id via `argon2-cffi`, com os parâmetros padrão da biblioteca registrados em `security.PARAMETROS_HASH` (`time_cost=3`, `memory_cost=65536`, `parallelism=4`, `hash_len=32`, `salt_len=16`) e armazenamento na string PHC completa. Alterar esses parâmetros exige nova aprovação.
3. **Expiração JWT:** ~~definir valor por ambiente e política operacional.~~ **APROVADA em 2026-11-17:** 3600 s em desenvolvimento, sempre lido de `MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS` (obrigatória, sem padrão no código). O prazo de produção faz parte da decisão 7 (ambiente/segredos), ainda pendente.
4. **Migrações do banco:** aprovar Alembic ou alternativa. A stack define SQLAlchemy 2.0, mas não escolhe ferramenta de migração.
5. **Seed de dados de referência:** aprovar quais unidades/registros iniciais, se houver. Não criar administrador por seed; o primeiro administrador deve respeitar o endpoint de bootstrap. *(Fase 3: `seed_reference_data()` pronta e idempotente, com lista vazia — nada foi inventado.)*
6. **Precisão/escala física de `Numeric`:** ~~confirmar precisão/escala de armazenamento.~~ **APROVADA em 2026-11-17:** dinheiro `(10,2)`, quantidades `(10,3)`, totais/subtotais de pedido `(15,2)`, como implementado na Fase 3. Fecha P3-14.
7. **Ambiente de implantação e gestão de segredos:** definir secret manager, política de rotação e origens CORS de produção; não há valores de produção definidos nos arquivos.

## Pontos de atenção de contrato

- O contrato contém 26 caminhos, mas 44 operações (método + caminho); a Fase 5 possui uma tarefa para cada operação.
- O contrato declara Bearer para operações protegidas; o perfil exigido deve ser derivado da descrição de cada operação. Operações sem restrição de papel explícita exigem autenticação, não um papel inventado.
- `GET /api/v1/saude`, `POST /api/v1/auth/administrador` e `POST /api/v1/auth/login` são públicos.
- Não existe `/api/v1/auth/me`; não implementar sem alteração aprovada do OpenAPI.
- `DELETE` de usuário e produto é desativação lógica; cliente/unidade/ingrediente têm regras de conflito para preservar referências/histórico.
- Pedido e baixas de estoque são atômicos; cancelamento não devolve estoque automaticamente.
- Respostas paginadas usam `data` e `paginacao`; respostas `204` não têm corpo; exportação é CSV UTF-8.

## Evidências da execução (Fases 1–2)

Ambiente: Python 3.12.3, venv novo a partir de `src/api/requirements.txt`.

| Verificação | Resultado |
|---|---|
| Importação de todos os módulos de `src.api` (43) | OK |
| `ruff check src` | OK |
| Uvicorn sobe (`--factory`), `/docs` e `/openapi.json` respondem 200; 0 rotas de negócio | OK |
| Regras de configuração (segredo/expiração obrigatórios, produção, teste, CORS, `.env` só em local) | OK |
| Redação de logs (senha, token, Bearer, hash) | OK |
| `verify_schemas.py`: 54 schemas, required, limites, enums, nullability, `additionalProperties`, extras, round-trip, `Decimal` como número JSON | 4 824 verificações OK |
| `verify_schemas.py --openapi "Mente Fria API.openapi.json"` (arquivo real, repositório publicado) | 5 976 verificações OK |

## Evidências da execução (Fase 3)

Ambiente: Python 3.13.18, SQLAlchemy 2.1.9, Pydantic 2.14.3, ruff 0.16.9; SQLite em memória.

| Verificação | Resultado |
|---|---|
| Importação dos módulos de `src.api` (28, exceto testes) | OK |
| `Base.metadata` reconhece as 9 tabelas; `configure_mappers()` resolve todos os relacionamentos; sem coluna de saldo em `ingredientes` | OK |
| 10 FKs com `ondelete` esperado (9 `RESTRICT`, 1 `CASCADE` em composição); nenhuma `SET NULL` | OK |
| Unicidade/integridade: e-mail, perfil, composição duplicada, FKs inexistentes, 7 bloqueios de exclusão (unidade, cliente, ingrediente×2, produto, usuário×2, pedido), `CHECK`s de domínio e de cancelamento | OK |
| Persistência: grafo completo, `Decimal` nos limites do contrato, datas com fuso `-03:00`, `date` preservada, saldo derivado (lote vencido/válido/vence hoje) | OK |
| `get_db`: gerador, sessão fechada ao final e em exceção, escrita sem commit não persiste, uso de outra thread, `PRAGMA foreign_keys=ON` | OK |
| Isolamento: teste = memória, recusa `mente_fria.db`, dois bancos independentes, nenhum arquivo `.db` criado; `init_db` recusada em `production` | OK |
| Seed: padrão não insere nada, idempotente com dados injetados, não cria usuários | OK |
| Schemas × ORM (`from_attributes`): `Usuario` (sem hash), `Cliente`, `UnidadeMedida`, `Ingrediente`, `MovimentacaoEstoque`, `Produto`, `Pedido`, `PedidoItem`, `ComposicaoProdutoItem`; todos os campos existem nos modelos; JSON mantém nomes e `Decimal` numérico | OK |
| `python verify_models.py` | **122 verificações OK, 0 falhas** |
| `python verify_schemas.py --openapi "Mente Fria API.openapi.json"` (regressão da Fase 2) | 5 976 verificações OK |
| `ruff check src verify_models.py` | OK (único aviso restante: `RUF100` pré-existente em `verify_schemas.py`) |

## Contagem de tarefas

| Fase | Tarefas | Concluídas |
|---|---:|---:|
| Fase 1 | 17 | 17 |
| Fase 2 | 64 | 64 |
| Fase 3 | 22 | 20 |
| Fase 4 | 18 | 18 |
| Fase 5 | 68 | 0 |
| Fase 6 | 26 | 0 |
| **Total** | **215** | **100** |