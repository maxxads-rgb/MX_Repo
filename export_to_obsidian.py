"""Exporta dados do INPI Monitor para notas Obsidian com links wiki."""

import argparse
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


def parse_xml(xml_path: Path) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    processos = []

    for processo in root.iter('processo'):
        num = processo.get('numero', '')
        nome_elem = processo.find('.//marca/nome')
        nome = nome_elem.text.strip() if nome_elem is not None and nome_elem.text else 'SEM NOME'

        titular_elem = processo.find('.//titulares/titular/nome-razao-social')
        titular = titular_elem.text.strip() if titular_elem is not None and titular_elem.text else 'Desconhecido'

        deposito_elem = processo.find('data-deposito')
        deposito = deposito_elem.text.strip() if deposito_elem is not None and deposito_elem.text else ''

        classes = []
        for cls in processo.findall('.//classe-nice'):
            cod = cls.get('codigo', '')
            if cod:
                classes.append(cod)

        despachos = []
        for d in processo.findall('.//despacho'):
            cod = d.get('codigo', '')
            nome_d = d.find('nome')
            texto = nome_d.text.strip() if nome_d is not None and nome_d.text else cod
            despachos.append(texto)

        apresentacao_elem = processo.find('.//marca/apresentacao')
        apresentacao = apresentacao_elem.text.strip() if apresentacao_elem is not None else ''

        processos.append({
            'numero': num,
            'nome': nome,
            'titular': titular,
            'deposito': deposito,
            'classes': classes,
            'despachos': despachos,
            'apresentacao': apresentacao,
            'status': despachos[-1] if despachos else 'Desconhecido',
        })

    return processos


def render_nota_marca(p: dict) -> str:
    tags = ['marca'] + [f'classe-{c}' for c in p['classes']]
    tags_yaml = ', '.join(tags)
    classes_links = ', '.join(f'[[Despachos/Classe {c}]]' for c in p['classes'])
    despachos_texto = ' → '.join(p['despachos']) if p['despachos'] else 'N/A'
    titular_link = f'[[Titulares/{sanitize_filename(p["titular"])}]]'

    return f"""---
tags: [{tags_yaml}]
processo: "{p['numero']}"
titular: "{p['titular']}"
deposito: "{p['deposito']}"
status: {p['status']}
apresentacao: {p['apresentacao']}
---

# {p['nome']}

- **Processo:** {p['numero']}
- **Titular:** {titular_link}
- **Classes Nice:** {classes_links if classes_links else 'N/A'}
- **Depósito:** {p['deposito']}
- **Apresentação:** {p['apresentacao']}
- **Despachos:** {despachos_texto}
"""


def render_nota_titular(titular: str, processos: list[dict]) -> str:
    links = '\n'.join(f'- [[Marcas/{sanitize_filename(p["nome"])}_{p["numero"]}]]' for p in processos)
    return f"""---
tags: [titular]
nome: "{titular}"
total_marcas: {len(processos)}
---

# {titular}

## Marcas Registradas

{links}
"""


def render_nota_classe(classe: str, processos: list[dict]) -> str:
    links = '\n'.join(f'- [[Marcas/{sanitize_filename(p["nome"])}_{p["numero"]}]]' for p in processos)
    return f"""---
tags: [classe]
classe: "{classe}"
total_marcas: {len(processos)}
---

# Classe Nice {classe}

## Marcas nesta Classe

{links}
"""


def exportar(xml_path: Path, vault_path: Path, filtro: str | None = None):
    print(f"Lendo XML: {xml_path}")
    processos = parse_xml(xml_path)
    print(f"Total de processos: {len(processos)}")

    if filtro:
        processos = [p for p in processos if filtro.upper() in p['nome'].upper()]
        print(f"Após filtro '{filtro}': {len(processos)} processos")

    marcas_dir = vault_path / 'Marcas'
    titulares_dir = vault_path / 'Titulares'
    despachos_dir = vault_path / 'Despachos'
    for d in [marcas_dir, titulares_dir, despachos_dir]:
        d.mkdir(parents=True, exist_ok=True)

    titulares_map: dict[str, list] = {}
    classes_map: dict[str, list] = {}

    for p in processos:
        filename = sanitize_filename(f"{p['nome']}_{p['numero']}") + '.md'
        (marcas_dir / filename).write_text(render_nota_marca(p), encoding='utf-8')

        titulares_map.setdefault(p['titular'], []).append(p)
        for c in p['classes']:
            classes_map.setdefault(c, []).append(p)

    for titular, ps in titulares_map.items():
        filename = sanitize_filename(titular) + '.md'
        (titulares_dir / filename).write_text(render_nota_titular(titular, ps), encoding='utf-8')

    for classe, ps in classes_map.items():
        filename = f'Classe {classe}.md'
        (despachos_dir / filename).write_text(render_nota_classe(classe, ps), encoding='utf-8')

    print(f"\nExportação concluída:")
    print(f"  Marcas:    {len(processos)} notas → {marcas_dir}")
    print(f"  Titulares: {len(titulares_map)} notas → {titulares_dir}")
    print(f"  Classes:   {len(classes_map)} notas → {despachos_dir}")
    print(f"\nAbra o vault em: {vault_path.resolve()}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Exporta dados INPI para vault Obsidian')
    parser.add_argument('--xml', required=True, type=Path, help='Caminho para o arquivo XML da RPI')
    parser.add_argument('--vault', required=True, type=Path, help='Caminho para a pasta do vault Obsidian')
    parser.add_argument('--filtro', default=None, help='Filtrar marcas pelo nome (parcial)')
    args = parser.parse_args()
    exportar(args.xml, args.vault, args.filtro)
