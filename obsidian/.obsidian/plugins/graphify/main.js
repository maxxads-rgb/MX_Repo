/*
 * Graphify 2 — Plugin Obsidian com integração Claude API
 * Analisa notas semanticamente e gera grafo de conhecimento interativo.
 */
'use strict';

const { Plugin, ItemView, WorkspaceLeaf, PluginSettingTab, Setting, Notice, TFile } = require('obsidian');

const VIEW_TYPE = 'graphify-view';

const DEFAULT_SETTINGS = {
  apiKey: '',
  model: 'claude-sonnet-4-6',
  autoAnalyze: false,
  maxNotesPerBatch: 20,
  minSimilarityScore: 0.6,
  colorGroups: [
    { tag: 'marca',   color: '#43a047' },
    { tag: 'titular', color: '#fb8c00' },
    { tag: 'classe',  color: '#5c6bc0' },
  ],
  showLabels: true,
  nodeSize: 8,
  linkDistance: 120,
};

// ── Claude API ──────────────────────────────────────────────────────────────

async function callClaude(apiKey, model, prompt) {
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 2048,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Claude API error ${resp.status}: ${err}`);
  }
  const data = await resp.json();
  return data.content[0].text;
}

async function analyzeConnections(apiKey, model, notes) {
  const summaries = notes.map(n => `### ${n.basename}\n${n.excerpt}`).join('\n\n');
  const prompt = `Você é um assistente especializado em análise de conhecimento jurídico e de marcas registradas.

Analise as seguintes notas de um vault do Obsidian e identifique conexões semânticas entre elas.
Retorne SOMENTE um JSON válido no formato abaixo, sem texto adicional:

{
  "connections": [
    { "source": "nome_da_nota_1", "target": "nome_da_nota_2", "strength": 0.85, "reason": "motivo breve" }
  ]
}

Regras:
- strength deve ser entre 0.0 e 1.0
- Inclua apenas conexões com strength >= 0.5
- source e target são os nomes dos arquivos sem extensão .md
- Limite a 50 conexões no total

Notas para analisar:

${summaries}`;

  const raw = await callClaude(apiKey, model, prompt);
  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('Claude não retornou JSON válido');
  return JSON.parse(jsonMatch[0]);
}

// ── Graph View ───────────────────────────────────────────────────────────────

class GraphifyView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.nodes = [];
    this.links = [];
    this.aiLinks = [];
    this.simulation = null;
    this.tooltip = null;
  }

  getViewType() { return VIEW_TYPE; }
  getDisplayText() { return 'Graphify 2'; }
  getIcon() { return 'git-fork'; }

  async onOpen() {
    this.containerEl.addClass('graphify-container');
    this.render();
    await this.loadGraph();
  }

  onClose() {
    if (this.simulation) this.simulation = null;
  }

  render() {
    const el = this.containerEl;
    el.empty();
    el.addClass('graphify-container');

    // Toolbar
    const toolbar = el.createDiv('graphify-toolbar');

    const btnRefresh = toolbar.createEl('button', { text: '↺ Atualizar' });
    btnRefresh.addEventListener('click', () => this.loadGraph());

    const btnAnalyze = toolbar.createEl('button', { cls: 'mod-cta', text: '✦ Analisar com Claude' });
    btnAnalyze.addEventListener('click', () => this.runClaudeAnalysis());

    const btnClear = toolbar.createEl('button', { text: '✕ Limpar IA' });
    btnClear.addEventListener('click', () => {
      this.aiLinks = [];
      this.drawGraph();
    });

    // Canvas SVG
    this.canvasEl = el.createDiv('graphify-canvas');

    // Tooltip
    this.tooltip = el.createDiv('graphify-tooltip');
    this.tooltip.style.display = 'none';

    // Status bar
    this.statusEl = el.createDiv('graphify-status');
    this.statusEl.setText('Pronto');
  }

  setStatus(msg, cls = '') {
    this.statusEl.setText(msg);
    this.statusEl.className = 'graphify-status ' + cls;
  }

  async loadGraph() {
    this.setStatus('Carregando notas...', 'loading');
    try {
      const files = this.app.vault.getMarkdownFiles();
      const nodeMap = new Map();
      const links = [];

      for (const file of files) {
        const cache = this.app.metadataCache.getFileCache(file);
        const tags = (cache?.tags || []).map(t => t.tag.replace('#', ''));
        const color = this.getColorForTags(tags);
        nodeMap.set(file.basename, { id: file.basename, path: file.path, tags, color, x: Math.random() * 600, y: Math.random() * 400 });
      }

      for (const file of files) {
        const cache = this.app.metadataCache.getFileCache(file);
        const resolved = this.app.metadataCache.resolvedLinks[file.path] || {};
        for (const targetPath of Object.keys(resolved)) {
          const targetFile = this.app.vault.getAbstractFileByPath(targetPath);
          if (targetFile instanceof TFile) {
            links.push({ source: file.basename, target: targetFile.basename, ai: false });
          }
        }
      }

      this.nodes = Array.from(nodeMap.values());
      this.links = links;
      this.drawGraph();
      this.setStatus(`${this.nodes.length} notas · ${this.links.length} links`);
    } catch (e) {
      this.setStatus('Erro ao carregar: ' + e.message, 'error');
    }
  }

  getColorForTags(tags) {
    for (const group of this.plugin.settings.colorGroups) {
      if (tags.includes(group.tag)) return group.color;
    }
    return '#888888';
  }

  async runClaudeAnalysis() {
    if (!this.plugin.settings.apiKey) {
      new Notice('Configure a chave da API do Claude nas configurações do Graphify 2.');
      return;
    }
    this.setStatus('Analisando com Claude...', 'loading');
    try {
      const files = this.app.vault.getMarkdownFiles().slice(0, this.plugin.settings.maxNotesPerBatch);
      const notes = await Promise.all(files.map(async f => ({
        basename: f.basename,
        excerpt: (await this.app.vault.cachedRead(f)).slice(0, 400).replace(/---[\s\S]*?---/, '').trim(),
      })));

      const result = await analyzeConnections(
        this.plugin.settings.apiKey,
        this.plugin.settings.model,
        notes
      );

      this.aiLinks = (result.connections || [])
        .filter(c => c.strength >= this.plugin.settings.minSimilarityScore)
        .map(c => ({ ...c, ai: true }));

      this.drawGraph();
      this.setStatus(`IA: ${this.aiLinks.length} conexões sugeridas (strength ≥ ${this.plugin.settings.minSimilarityScore})`);
    } catch (e) {
      this.setStatus('Erro Claude: ' + e.message, 'error');
      new Notice('Graphify 2: ' + e.message);
    }
  }

  drawGraph() {
    this.canvasEl.empty();
    const width = this.canvasEl.clientWidth || 600;
    const height = this.canvasEl.clientHeight || 400;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.style.width = '100%';
    svg.style.height = '100%';

    const allLinks = [...this.links, ...this.aiLinks];
    const nodeMap = new Map(this.nodes.map(n => [n.id, n]));
    const r = this.plugin.settings.nodeSize;
    const settings = this.plugin.settings;

    // Posicionar nós em círculo
    if (this.nodes.length > 0) {
      this.nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / this.nodes.length;
        const rad = Math.min(width, height) * 0.38;
        n.x = width / 2 + rad * Math.cos(angle);
        n.y = height / 2 + rad * Math.sin(angle);
      });
    }

    // Links
    for (const link of allLinks) {
      const s = nodeMap.get(link.source);
      const t = nodeMap.get(link.target);
      if (!s || !t) continue;
      const line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', s.x);
      line.setAttribute('y1', s.y);
      line.setAttribute('x2', t.x);
      line.setAttribute('y2', t.y);
      line.classList.add('graphify-link');
      if (link.ai) line.classList.add('ai-link');
      if (link.strength) line.setAttribute('stroke-opacity', link.strength);
      svg.appendChild(line);
    }

    // Nós
    for (const node of this.nodes) {
      const g = document.createElementNS(ns, 'g');
      g.classList.add('graphify-node');

      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('cx', node.x);
      circle.setAttribute('cy', node.y);
      circle.setAttribute('r', r);
      circle.setAttribute('fill', node.color);

      circle.addEventListener('mouseenter', (e) => {
        this.tooltip.style.display = 'block';
        this.tooltip.innerHTML = `<strong>${node.id}</strong><br><small>${node.tags.map(t => '#' + t).join(' ') || 'sem tags'}</small>`;
      });
      circle.addEventListener('mousemove', (e) => {
        const rect = this.canvasEl.getBoundingClientRect();
        this.tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
        this.tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
      });
      circle.addEventListener('mouseleave', () => {
        this.tooltip.style.display = 'none';
      });
      circle.addEventListener('click', async () => {
        const file = this.app.vault.getAbstractFileByPath(node.path);
        if (file instanceof TFile) {
          await this.app.workspace.getLeaf('tab').openFile(file);
        }
      });

      g.appendChild(circle);

      if (settings.showLabels) {
        const text = document.createElementNS(ns, 'text');
        text.setAttribute('x', node.x);
        text.setAttribute('y', node.y + r + 12);
        text.setAttribute('text-anchor', 'middle');
        text.textContent = node.id.length > 18 ? node.id.slice(0, 16) + '…' : node.id;
        g.appendChild(text);
      }

      svg.appendChild(g);
    }

    this.canvasEl.appendChild(svg);
    this.canvasEl.appendChild(this.tooltip);
  }
}

// ── Settings Tab ─────────────────────────────────────────────────────────────

class GraphifySettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl('h2', { text: 'Graphify 2 — Configurações' });

    new Setting(containerEl)
      .setName('Chave da API Claude')
      .setDesc('Sua chave da API Anthropic (começa com sk-ant-...)')
      .addText(t => t
        .setPlaceholder('sk-ant-api03-...')
        .setValue(this.plugin.settings.apiKey)
        .onChange(async v => {
          this.plugin.settings.apiKey = v.trim();
          await this.plugin.saveSettings();
        })
        .inputEl.setAttribute('type', 'password')
      );

    new Setting(containerEl)
      .setName('Modelo Claude')
      .setDesc('ID do modelo a usar para análise semântica')
      .addDropdown(d => d
        .addOption('claude-sonnet-4-6', 'Claude Sonnet 4.6 (recomendado)')
        .addOption('claude-haiku-4-5-20251001', 'Claude Haiku 4.5 (mais rápido)')
        .addOption('claude-opus-4-8', 'Claude Opus 4.8 (mais poderoso)')
        .setValue(this.plugin.settings.model)
        .onChange(async v => {
          this.plugin.settings.model = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName('Máximo de notas por análise')
      .setDesc('Quantas notas enviar ao Claude de uma vez')
      .addSlider(s => s
        .setLimits(5, 50, 5)
        .setValue(this.plugin.settings.maxNotesPerBatch)
        .setDynamicTooltip()
        .onChange(async v => {
          this.plugin.settings.maxNotesPerBatch = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName('Score mínimo de conexão')
      .setDesc('Apenas conexões com similaridade acima deste valor são exibidas (0.0–1.0)')
      .addSlider(s => s
        .setLimits(0.1, 0.9, 0.05)
        .setValue(this.plugin.settings.minSimilarityScore)
        .setDynamicTooltip()
        .onChange(async v => {
          this.plugin.settings.minSimilarityScore = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName('Mostrar rótulos')
      .setDesc('Exibir nome das notas no grafo')
      .addToggle(t => t
        .setValue(this.plugin.settings.showLabels)
        .onChange(async v => {
          this.plugin.settings.showLabels = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName('Tamanho dos nós')
      .addSlider(s => s
        .setLimits(4, 20, 1)
        .setValue(this.plugin.settings.nodeSize)
        .setDynamicTooltip()
        .onChange(async v => {
          this.plugin.settings.nodeSize = v;
          await this.plugin.saveSettings();
        })
      );
  }
}

// ── Plugin Principal ──────────────────────────────────────────────────────────

class GraphifyPlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    this.registerView(VIEW_TYPE, leaf => new GraphifyView(leaf, this));

    this.addRibbonIcon('git-fork', 'Graphify 2', () => this.activateView());

    this.addCommand({
      id: 'open-graphify',
      name: 'Abrir Graphify 2',
      callback: () => this.activateView(),
    });

    this.addCommand({
      id: 'graphify-analyze',
      name: 'Graphify 2: Analisar conexões com Claude',
      callback: async () => {
        await this.activateView();
        const leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0];
        if (leaf) await leaf.view.runClaudeAnalysis();
      },
    });

    this.addSettingTab(new GraphifySettingTab(this.app, this));

    if (this.settings.autoAnalyze) {
      this.app.workspace.onLayoutReady(() => this.activateView());
    }
  }

  onunload() {
    this.app.workspace.detachLeavesOfType(VIEW_TYPE);
  }

  async activateView() {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      await leaf.setViewState({ type: VIEW_TYPE, active: true });
    }
    workspace.revealLeaf(leaf);
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }
}

module.exports = GraphifyPlugin;
