"""Services da Mente Fria API: regras de negócio, fora da camada HTTP (Fase 5 — P5-01).

Contrato interno destes módulos:

- **Entrada:** uma ``Session`` do SQLAlchemy mais os dados já validados pelos schemas
  Pydantic; a identidade autenticada chega como ``usuario_id``/``usuario``, nunca lida do
  corpo da requisição.
- **Saída:** modelos ORM ou schemas de resposta do contrato — nunca ``Response``,
  ``status_code`` ou qualquer objeto do FastAPI.
- **Erros:** exceções de domínio de ``exceptions.py`` (`NaoEncontradoError`,
  `ConflitoError`, `ValidacaoError`, `RequisicaoInvalidaError`,
  `DependenciaIndisponivelError`), que os handlers globais convertem em ``ApiError``.
- **Transações:** cada função de escrita decide seu ``commit``/``rollback``; o caso
  atômico do pedido (itens + baixas de estoque) é coordenado por ``pedidos.registrar``.

Nenhum módulo daqui importa ``fastapi``: é isso que mantém a separação exigida pelo
STYLEGUIDE §2 verificável.
"""
