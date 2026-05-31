# Contribuindo

## Ambiente de desenvolvimento

1. Clone o repositório e entre na pasta do app:

   ```bash
   git clone https://github.com/mrcsistemas-dev/inpi-monitor.git
   cd inpi-monitor/app
   ```

2. Instale o [uv](https://github.com/astral-sh/uv) e sincronize dependências (a versão do Python está em `.python-version`):

   ```bash
   uv sync
   ```

3. Execute a interface (requer ambiente gráfico — PyQt6):

   ```bash
   uv run python main.py
   ```

   Ou, na raiz do repositório:

   ```bash
   ./iniciar.sh
   ```

## Estrutura do código

| Caminho | Função |
|--------|--------|
| `app/main.py` | Ponto de entrada |
| `app/core/` | Modelos, banco, parser XML, scraper INPI |
| `app/ui/` | Janelas PyQt6 e abas |

## Pull requests

- Descreva o que mudou e por quê.
- Garanta que o workflow **CI** passe (sincronização `uv` e compilação dos fontes Python).

## Workflows opcionais (Claude)

Os arquivos `.github/workflows/claude*.y` exigem o secret `CLAUDE_CODE_OAUTH_TOKEN` no repositório. Sem esse secret, esses workflows não são necessários para desenvolvimento local.
