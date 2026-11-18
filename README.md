# Mente Fria API

API REST para gestão de pequenos comércios, com piloto em uma açaiteria. Centraliza
usuários, clientes, unidades de medida, ingredientes, produtos e composições,
movimentações de estoque e pedidos; oferece alertas, dashboard, recomendações por
Programação Linear Inteira e sugestões de marketing.

Desenvolvida com **Spec-Driven Development (SDD)** e assistência de IA: o contrato
OpenAPI é a fonte da verdade, e cada fase foi planejada, executada e verificada antes da
seguinte.

| | |
|---|---|
| **Contrato** | [`Mente Fria API.openapi.json`](Mente%20Fria%20API.openapi.json) — OpenAPI 3.0.1, 26 caminhos, 44 operações, 54 schemas |
| **Stack** | Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · SQLite · PyJWT · Argon2id · PuLP |
| **Testes** | 757 testes (`pytest`) + 4 verificadores com ~7.400 conferências |
| **Estado** | 6 fases concluídas — 215 de 215 tarefas do [`PLAN.md`](PLAN.md) |

---

## Como executar

### 1. Ambiente

```bash
python -m venv .venv
```

Ative o ambiente virtual:

- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
- **Linux / macOS:** `source .venv/bin/activate`

```bash
pip install -r src/api/requirements.txt
```

> **Se o PowerShell recusar o `Activate.ps1`** com "a execução de scripts foi desabilitada
> neste sistema", não precisa mexer na política de execução da máquina: chame os
> executáveis do ambiente pelo caminho, sem ativar nada.
>
> ```powershell
> .venv\Scripts\pip.exe install -r src/api/requirements.txt
> ```
>
> O mesmo vale adiante: `.venv\Scripts\uvicorn.exe`, `.venv\Scripts\python.exe` e
> `.venv\Scripts\pytest.exe` no lugar de `uvicorn`, `python` e `pytest`.

### 2. Configuração

Copie o modelo e gere um segredo para o JWT:

```bash
cp .env.example .env
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Cole o valor em `MENTE_FRIA_JWT_SECRET_KEY`, dentro do `.env`. O arquivo é lido **somente**
quando `MENTE_FRIA_ENV=local`; em implantação os valores vêm do ambiente de execução.
`.env` está no `.gitignore` — nunca versione segredos.

Em desenvolvimento local o valor do modelo já serve para subir a API; gerar um próprio é
boa prática. Em `production` a aplicação **recusa** iniciar com o placeholder.

### 3. Subir a API

```bash
uvicorn --factory src.api.main:create_app
```

Sem o ambiente ativado (ver o aviso acima): `.venv\Scripts\uvicorn.exe --factory src.api.main:create_app`

- API: <http://127.0.0.1:8000/api/v1>
- Documentação interativa (Swagger UI): <http://127.0.0.1:8000/docs>
- Verificação de saúde: <http://127.0.0.1:8000/api/v1/saude>

O banco `mente_fria.db` é criado na primeira execução, **vazio**: nenhum dado de exemplo é
semeado (decisão registrada no `PLAN.md`). Os primeiros passos abaixo mostram como
povoá-lo pela própria API.

---

## Demonstração em um comando

Com a API no ar e um banco **vazio**, em outro terminal:

```bash
python demonstracao.py
```

Sem o ambiente ativado: `.venv\Scripts\python.exe demonstracao.py`

O roteiro percorre 42 chamadas pelos endpoints do contrato e narra cada passo: bootstrap
do administrador e conflito na segunda tentativa, autorização por perfil, catálogo,
entradas com validades diferentes, pedido com preço capturado e baixa em **FEFO**,
alteração de preço que não reescreve o histórico, cancelamento sem devolução de estoque,
alertas, descarte de lote vencido, recomendação por Programação Linear Inteira, dashboard,
exportação CSV e o envelope de erro em `404`, `400` e `422`.

Não é seed: o script é um cliente HTTP como outro qualquer, e a política de seed do
projeto continua vazia. Depende apenas da biblioteca padrão. Para repetir, apague o
`mente_fria.db` e suba a API de novo — ele precisa de um banco limpo, e avisa quando não
encontra um.

---

## Primeiros passos, chamada a chamada

Se preferir conduzir à mão, em vez do roteiro acima. O banco nasce sem nenhum usuário, e a
sequência abaixo sai do zero até um pedido com baixa de estoque. Os exemplos usam `curl`,
disponível no Windows 10+, Linux e macOS.

**1. Criar o primeiro administrador** (operação pública, permitida uma única vez):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/administrador -H "Content-Type: application/json" -d "{\"nome\":\"Maria Silva\",\"email\":\"maria@exemplo.com\",\"senha\":\"SenhaForte#2026\"}"
```

**2. Autenticar e guardar o token** devolvido em `accessToken`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"maria@exemplo.com\",\"senha\":\"SenhaForte#2026\"}"
```

Nas chamadas seguintes, envie o cabeçalho `Authorization: Bearer <accessToken>`.

**3. Criar unidade de medida, ingrediente, estoque e produto**, nesta ordem:

| Passo | Operação |
|---|---|
| Unidade de medida | `POST /api/v1/unidades-medida` — `{"unidadeMedida": "g", "porcaoPadrao": 100}` |
| Ingrediente | `POST /api/v1/ingredientes` — nasce com **estoque zero** |
| Entrada de estoque | `POST /api/v1/movimentacoes-estoque` — `tipo: ENTRADA`, com `dataValidade` opcional |
| Produto | `POST /api/v1/produtos` — com `composicao` apontando para o ingrediente |
| Pedido | `POST /api/v1/pedidos` — captura o preço vigente e **baixa o estoque em FEFO** |

**4. Ver o resultado:** `GET /api/v1/dashboard?dataInicio=…&dataFim=…`,
`GET /api/v1/alertas/validade` e `POST /api/v1/recomendacoes/producao`.

O caminho completo é mais confortável pelo Swagger UI em `/docs`, que já monta os corpos
a partir do contrato e tem o botão **Authorize** para o token.

---

## Testes

Suíte completa (757 testes, ~4 minutos — cada teste usa um banco SQLite em memória novo):

```bash
pytest
```

Um domínio específico:

```bash
pytest src/api/tests/test_pedidos.py -v
```

### Verificadores

Scripts na raiz que conferem a implementação contra o contrato. Não substituem o
`pytest`: cobrem ângulos que a suíte não cobre, como ausência de N+1 por contagem de
SELECTs e concorrência com threads.

```bash
python verify_api.py
```

```bash
python verify_security.py
```

```bash
python verify_models.py
```

```bash
python verify_schemas.py --openapi "Mente Fria API.openapi.json"
```

| Script | Cobre | Conferências |
|---|---|---:|
| `verify_api.py` | OpenAPI gerado × contrato, fluxos ponta a ponta, N+1 | 1.025 |
| `verify_security.py` | hash, JWT, RBAC, bootstrap concorrente, `ApiError` | 306 |
| `verify_models.py` | modelos, relacionamentos, constraints, integridade | 122 |
| `verify_schemas.py` | os 54 schemas: limites, enums, formatos, exemplos | 5.976 |

---

## Estrutura

```text
src/api/
├── main.py              # FastAPI, lifespan, CORS, registro dos routers
├── config.py            # configuração por ambiente, sem segredo embutido
├── schemas.py           # os 54 schemas do contrato em Pydantic v2
├── models.py            # 9 entidades em SQLAlchemy 2.0
├── database.py          # engine, sessão, get_db, criação de schema
├── security.py          # Argon2id, JWT, HTTP Bearer, RBAC
├── exceptions.py        # exceções de domínio e envelope ApiError
├── services/            # regras de negócio (nenhum importa fastapi)
├── integrations/        # optimizer.py: fronteira com o solver PuLP
├── routers/             # 13 routers por domínio, só camada HTTP
└── tests/               # 15 arquivos de teste
```

**Separação de camadas:** routers cuidam de HTTP, services das regras de negócio,
`models.py` da persistência e `integrations/` do que é externo. Nenhum service importa
`fastapi` — é o que torna a separação verificável, não apenas declarada.

---

## Documentação do projeto

A metodologia está documentada no próprio repositório, e é parte da entrega:

| Arquivo | Conteúdo |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Governança do desenvolvimento com IA: personas, proibição de *vibe coding*, contrato imutável |
| [`SPEC.md`](SPEC.md) | Especificação de negócio, ORM e autenticação; regras de estoque, pedidos e relatórios |
| [`STYLEGUIDE.md`](STYLEGUIDE.md) | Constituição técnica: stack, arquitetura, nomenclatura, erros, transações |
| [`PLAN.md`](PLAN.md) | As 215 tarefas das 6 fases, com evidência por tarefa, decisões datadas e divergências registradas |
| [`Mente Fria API.openapi.json`](Mente%20Fria%20API.openapi.json) | O contrato. Fonte da verdade — nunca alterado para acomodar a implementação |

---

## Decisões técnicas

Sete decisões não fixadas pelo contrato exigiram aprovação humana; **seis foram
aprovadas** e estão registradas com data e justificativa no `PLAN.md`:

1. **Solver:** PuLP com CBC embutido, sem dependência de sistema.
2. **Hash de senha:** Argon2id (`argon2-cffi`), parâmetros registrados em código.
3. **Expiração do JWT:** configurável por ambiente, sem prazo fixo no código.
4. **Migrações:** nenhuma ferramenta adotada; criação de schema por `init_db()`, recusada em produção.
5. **Seed:** nenhum dado de referência — unidades e o primeiro administrador nascem pelos endpoints do contrato.
6. **Precisão monetária:** `Numeric(10,2)` para dinheiro, `(10,3)` para quantidades, `(15,2)` para totais; `Decimal` em todo cálculo financeiro, nunca `float`.

Pendente: **7 — ambiente de implantação e gestão de segredos**, que depende de
infraestrutura real e não afeta o funcionamento local.

Duas decisões alteram a leitura literal do `SPEC.md` e estão sinalizadas como tais:
`DESCARTE_VENCIDO` passou a consumir lotes vencidos (sem isso, estoque vencido nunca
sairia do sistema), e produto desativado não pode ser vendido.

---

## Regras de negócio que vale conhecer

- **Estoque é derivado, nunca editado.** O saldo do ingrediente é a soma dos lotes de entrada disponíveis; não existe campo editável de saldo.
- **FEFO.** Saídas consomem primeiro o lote que vence antes, e **nunca** tocam lote vencido. A única exceção é a saída com motivo `DESCARTE_VENCIDO`, que consome apenas lotes vencidos.
- **Pedido é atômico.** Pedido, itens e baixas de estoque são gravados na mesma transação; qualquer falha desfaz tudo.
- **Preço é histórico.** O item do pedido guarda nome e preço no momento da venda; alterar o produto depois não reescreve o passado.
- **Cancelar não devolve estoque.** É decisão de negócio do contrato: o pedido cancelado continua consultável, mas sai dos indicadores financeiros.
- **Erros têm formato próprio.** Toda resposta de erro segue o envelope `ApiError` do contrato — nunca o `{"detail": "..."}` padrão do FastAPI.

---

## Equipe

Projeto acadêmico desenvolvido por **Kauê Nogueira Carneiro** e **Diogo Miranda**.
