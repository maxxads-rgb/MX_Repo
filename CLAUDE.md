# INPI Monitor — Guia para Claude Code

## Visão Geral

Este repositório contém o **INPI Monitor**, ferramenta de pesquisa e monitoramento de marcas no INPI, integrada a um vault do Obsidian para gestão de conhecimento e visualização de grafos.

## Estrutura do Projeto

```
.
├── app/                  # Aplicação principal (Python/uv)
├── obsidian/             # Vault do Obsidian
│   ├── .obsidian/        # Configuração do vault e plugins
│   ├── Marcas/           # Notas de processos de marcas
│   ├── Titulares/        # Notas de titulares
│   └── Despachos/        # Notas de tipos de despacho
├── export_to_obsidian.py # Exporta dados INPI → notas Obsidian
├── iniciar.sh            # Inicializa a aplicação principal
└── MANUAL.md             # Manual do usuário
```

## Vault do Obsidian

O vault está em `obsidian/`. Para abrir no Obsidian: **Abrir pasta como vault** → selecione `obsidian/`.

### Plugins instalados
- **Graphify 2** (`graphify`): Visualização de grafos de conhecimento com filtros avançados

### Exportar dados INPI para o vault

```bash
# Exportar XML da RPI para notas Obsidian
python export_to_obsidian.py --xml RM2878.xml --vault obsidian/

# Exportar apenas marcas específicas
python export_to_obsidian.py --xml RM2878.xml --vault obsidian/ --filtro "CAFE"
```

## Comandos Úteis

```bash
# Iniciar a aplicação INPI Monitor
./iniciar.sh

# Exportar dados para Obsidian
python export_to_obsidian.py --xml <arquivo.xml> --vault obsidian/

# Instalar dependências da app
cd app && uv sync
```

## Padrão das Notas Obsidian

Cada processo de marca gera uma nota com frontmatter YAML e links wiki para titular e classes Nice. Isso alimenta o grafo do Graphify 2.

### Exemplo de nota (`obsidian/Marcas/923456789.md`)

```markdown
---
tags: [marca, classe-35]
processo: "923456789"
titular: "Empresa XYZ Ltda"
deposito: "2021-03-15"
status: Concessão
---

# MARCA EXEMPLO

- **Titular:** [[Titulares/Empresa XYZ Ltda]]
- **Classe:** [[Despachos/Classe 35]]
- **Despacho:** Concessão
- **Depósito:** 2021-03-15
```

## Integração com Claude Code

Claude Code pode:
- Ler e analisar notas do vault em `obsidian/`
- Executar `export_to_obsidian.py` para atualizar o vault
- Modificar configurações do Graphify em `.obsidian/plugins/graphify/data.json`
- Consultar `app/data/monitor.db` (SQLite) para dados de monitoramento
