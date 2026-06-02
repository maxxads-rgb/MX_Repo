# INPI Monitor — Guia para Claude Code

## Visão Geral

Este repositório contém o **INPI Monitor** integrado a um vault do Obsidian com o plugin **Graphify 2**, que usa a API do Claude para gerar grafos de conhecimento semântico entre as notas de marcas registradas.

## Estrutura do Projeto

```
.
├── app/                          # Aplicação principal INPI Monitor (Python/uv)
├── obsidian/                     # Vault do Obsidian
│   ├── .obsidian/
│   │   ├── plugins/
│   │   │   └── graphify/         # Plugin Graphify 2
│   │   │       ├── main.js       # Código do plugin
│   │   │       ├── manifest.json
│   │   │       ├── styles.css
│   │   │       └── data.json     # Config (apiKey — NÃO commitar preenchido)
│   │   ├── community-plugins.json
│   │   ├── core-plugins.json
│   │   └── app.json
│   ├── Marcas/
│   ├── Titulares/
│   └── Despachos/
├── export_to_obsidian.py
├── iniciar.sh
└── MANUAL.md
```

## Fluxo de Trabalho

1. **Exportar dados INPI → Obsidian**
   ```bash
   python export_to_obsidian.py --xml RM2878.xml --vault obsidian/
   ```

2. **Abrir vault no Obsidian**  
   Obsidian → Abrir pasta como vault → selecionar `obsidian/`

3. **Configurar API Key no Graphify 2**  
   Configurações → Plugins da comunidade → Graphify 2 → inserir `sk-ant-api03-...`

4. **Gerar grafo com Claude**  
   Clicar no ícone `git-fork` na barra lateral → "✦ Analisar com Claude"

## Plugin Graphify 2

O plugin usa a API do Claude para:
- Ler notas do vault e enviar ao Claude para análise semântica
- Receber conexões sugeridas com score de similaridade
- Desenhar grafo com links normais (wiki) e links IA (pontilhados coloridos)
- Abrir nota com clique no nó

### Configurações (`data.json`)

| Campo | Padrão | Descrição |
|---|---|---|
| `apiKey` | `""` | Chave Anthropic (nunca commitar preenchida) |
| `model` | `claude-sonnet-4-6` | Modelo Claude usado |
| `maxNotesPerBatch` | `20` | Notas por análise |
| `minSimilarityScore` | `0.6` | Score mínimo para exibir conexão |

## Segurança

`data.json` está no `.gitignore` — a chave da API deve ser inserida localmente no Obsidian, nunca versionada.
