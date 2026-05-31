#!/usr/bin/env python3
"""
Busca de jurisprudência em arquivos PDF locais.

Percorre um diretório (ou arquivos individuais), extrai o texto de cada página
e exibe os trechos que contêm os termos pesquisados — com contexto ao redor.

Uso:
  python buscar_pdfs.py ~/coletaneas/ --tema abusividade
  python buscar_pdfs.py ~/coletaneas/ --termo "capitalização mensal" --contexto 5
  python buscar_pdfs.py doc1.pdf doc2.pdf --tema mora --exportar resultado.json
  python buscar_pdfs.py ~/coletaneas/ --tema todos --exportar relatorio.csv
  python buscar_pdfs.py ~/coletaneas/ --termo "REsp" --regex --tribunal stj
"""

import argparse
import csv
import json
import os
import re
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# Temas de direito bancário (mesmos do jurisprudencia.py)
# ---------------------------------------------------------------------------

TEMAS: dict[str, dict] = {
    "cheque-especial": {
        "descricao": "Juros de cheque especial / crédito rotativo",
        "termos": ["cheque especial", "crédito rotativo"],
    },
    "capitalizacao": {
        "descricao": "Capitalização mensal de juros / anatocismo",
        "termos": ["capitalização mensal", "anatocismo"],
    },
    "mora": {
        "descricao": "Descaracterização da mora",
        "termos": ["descaracterização da mora", "mora descaracterizada"],
    },
    "abusividade": {
        "descricao": "Abusividade da taxa de juros",
        "termos": ["abusividade", "taxa de juros abusiva", "juros abusivos"],
    },
    "boa-fe": {
        "descricao": "Boa-fé contratual / boa-fé objetiva",
        "termos": ["boa-fé objetiva", "boa fé contratual"],
    },
    "clausulas": {
        "descricao": "Ambiguidade / abusividade de cláusulas contratuais",
        "termos": ["cláusula abusiva", "ambiguidade", "interpretação favorável ao consumidor"],
    },
    "transparencia": {
        "descricao": "Dever de transparência (CDC e CC)",
        "termos": ["dever de transparência", "dever de informação", "transparência contratual"],
    },
}

# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------


@dataclass
class Ocorrencia:
    arquivo: str          # caminho do PDF
    pagina: int           # número da página (1-based)
    termo: str            # termo que gerou o match
    tema: str             # nome do tema, ou "" para busca livre
    trecho: str           # texto ao redor do match
    numero_processo: str  # número extraído do contexto, se encontrado


# ---------------------------------------------------------------------------
# Extração de texto e busca
# ---------------------------------------------------------------------------

# Padrão para capturar número de processo (CNJ ou formato antigo)
_RE_PROCESSO = re.compile(
    r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"          # CNJ
    r"|(?:REsp|AgInt|AgRg|AREsp|HC|RMS|MS)\s*[\d\.]+/\w+"  # STJ
    r"|(?:APL|AC|AI|Ap)\s*[\d\.\-/]+",                 # TJRJ / outros
    re.I,
)


def _extrair_processo(texto: str) -> str:
    """Tenta encontrar um número de processo próximo ao trecho."""
    m = _RE_PROCESSO.search(texto)
    return m.group(0).strip() if m else ""


def _linhas_contexto(texto: str, pos_inicio: int, pos_fim: int, n_linhas: int) -> str:
    """
    Retorna N linhas antes e depois da linha que contém a ocorrência,
    destacando o trecho encontrado entre colchetes.
    """
    linhas = texto.splitlines()
    # Encontra linha que contém a posição do match
    acumulado = 0
    linha_match = 0
    for i, linha in enumerate(linhas):
        acumulado += len(linha) + 1  # +1 pelo \n
        if acumulado > pos_inicio:
            linha_match = i
            break

    inicio = max(0, linha_match - n_linhas)
    fim = min(len(linhas), linha_match + n_linhas + 1)
    bloco = linhas[inicio:fim]

    # Marca a linha do match
    bloco[linha_match - inicio] = ">>> " + bloco[linha_match - inicio]
    return "\n".join(bloco)


def buscar_em_pagina(
    texto: str,
    termos: list[str],
    n_contexto: int,
    usar_regex: bool,
) -> list[tuple[str, int, int]]:
    """
    Retorna lista de (termo_encontrado, pos_inicio, pos_fim) para cada ocorrência.
    """
    resultados = []
    for termo in termos:
        if usar_regex:
            padrao = re.compile(termo, re.I)
        else:
            padrao = re.compile(re.escape(termo), re.I)
        for m in padrao.finditer(texto):
            resultados.append((termo, m.start(), m.end()))
    # Ordena por posição
    resultados.sort(key=lambda x: x[1])
    return resultados


def buscar_em_pdf(
    caminho_pdf: Path,
    termos: list[str],
    n_contexto: int,
    usar_regex: bool,
    tema: str = "",
    pagina_max: int | None = None,
) -> list[Ocorrencia]:
    """Abre o PDF e busca os termos em cada página."""
    ocorrencias: list[Ocorrencia] = []

    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            paginas = pdf.pages
            if pagina_max:
                paginas = paginas[:pagina_max]

            for num_pag, pagina in enumerate(paginas, start=1):
                texto = pagina.extract_text() or ""
                if not texto.strip():
                    continue

                matches = buscar_em_pagina(texto, termos, n_contexto, usar_regex)

                # Deduplicar: uma ocorrência por linha por termo
                linhas_vistas: set[tuple[str, int]] = set()
                for termo_encontrado, pos_ini, pos_fim in matches:
                    linha_num = texto[:pos_ini].count("\n")
                    chave = (termo_encontrado, linha_num)
                    if chave in linhas_vistas:
                        continue
                    linhas_vistas.add(chave)

                    trecho = _linhas_contexto(texto, pos_ini, pos_fim, n_contexto)
                    num_proc = _extrair_processo(trecho)

                    ocorrencias.append(
                        Ocorrencia(
                            arquivo=str(caminho_pdf),
                            pagina=num_pag,
                            termo=termo_encontrado,
                            tema=tema,
                            trecho=trecho.strip(),
                            numero_processo=num_proc,
                        )
                    )

    except Exception as e:
        print(f"  [AVISO] Não foi possível ler {caminho_pdf.name}: {e}", file=sys.stderr)

    return ocorrencias


# ---------------------------------------------------------------------------
# Coleta de arquivos PDF
# ---------------------------------------------------------------------------


def coletar_pdfs(caminhos: list[str], recursivo: bool) -> list[Path]:
    """Expande caminhos (arquivos ou diretórios) em lista de PDFs."""
    pdfs: list[Path] = []
    for c in caminhos:
        p = Path(c).expanduser().resolve()
        if p.is_file() and p.suffix.lower() == ".pdf":
            pdfs.append(p)
        elif p.is_dir():
            glob = "**/*.pdf" if recursivo else "*.pdf"
            pdfs.extend(sorted(p.glob(glob)))
        else:
            print(f"[AVISO] Caminho não encontrado ou não é PDF: {c}", file=sys.stderr)
    return pdfs


# ---------------------------------------------------------------------------
# Exibição no terminal
# ---------------------------------------------------------------------------

_SEP = "─" * 72
_SEP2 = "=" * 72


def _imprimir_ocorrencia(oc: Ocorrencia, indice: int, verbose: bool) -> None:
    print(f"\n{_SEP}")
    print(f"[{indice}] {Path(oc.arquivo).name}  —  p. {oc.pagina}")
    if oc.numero_processo:
        print(f"    Processo  : {oc.numero_processo}")
    if oc.tema:
        print(f"    Tema      : {oc.tema}")
    print(f"    Termo     : \"{oc.termo}\"")
    print(f"    Trecho:")
    limite = None if verbose else 600
    texto = oc.trecho[:limite] + ("…" if limite and len(oc.trecho) > limite else "")
    for linha in texto.splitlines():
        print(f"      {linha}")


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------


def exportar_json(ocorrencias: list[Ocorrencia], caminho: str) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump([asdict(o) for o in ocorrencias], f, ensure_ascii=False, indent=2)
    print(f"\nResultados exportados para: {caminho}")


def exportar_csv(ocorrencias: list[Ocorrencia], caminho: str) -> None:
    if not ocorrencias:
        return
    campos = list(asdict(ocorrencias[0]).keys())
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(asdict(o) for o in ocorrencias)
    print(f"\nResultados exportados para: {caminho}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    nomes_temas = list(TEMAS.keys()) + ["todos"]
    desc_temas = "\n".join(
        f"  {k:<20} {v['descricao']}" for k, v in TEMAS.items()
    )

    p = argparse.ArgumentParser(
        prog="buscar_pdfs",
        description="Busca de jurisprudência bancária em arquivos PDF locais.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Temas disponíveis (--tema):\n"
            + desc_temas + "\n"
            + "  todos                Pesquisa todos os temas acima\n\n"
            "Exemplos:\n"
            "  python buscar_pdfs.py ~/coletaneas/ --tema abusividade\n"
            "  python buscar_pdfs.py ~/docs/ --termo \"capitalização mensal\" --contexto 5\n"
            "  python buscar_pdfs.py doc1.pdf doc2.pdf --tema mora --exportar resultado.json\n"
            "  python buscar_pdfs.py ~/coletaneas/ --tema todos --exportar relatorio.csv\n"
            "  python buscar_pdfs.py ~/docs/ --termo \"REsp.*juros\" --regex\n"
        ),
    )

    p.add_argument(
        "caminhos",
        nargs="+",
        metavar="CAMINHO",
        help="Arquivo(s) PDF ou diretório(s) contendo PDFs.",
    )

    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--termo",
        metavar="TEXTO",
        help="Termo livre a buscar nos PDFs.",
    )
    grupo.add_argument(
        "--tema",
        choices=nomes_temas,
        metavar="TEMA",
        help=f"Tema bancário pré-configurado: {{{', '.join(nomes_temas)}}}.",
    )

    p.add_argument(
        "--contexto",
        type=int,
        default=3,
        metavar="N",
        help="Linhas de contexto ao redor de cada ocorrência (padrão: 3).",
    )
    p.add_argument(
        "--regex",
        action="store_true",
        help="Tratar --termo como expressão regular.",
    )
    p.add_argument(
        "--pagina-max",
        type=int,
        default=None,
        metavar="N",
        help="Limitar a busca às primeiras N páginas de cada PDF.",
    )
    p.add_argument(
        "--recursivo",
        action="store_true",
        help="Buscar PDFs em subdiretórios.",
    )
    p.add_argument(
        "--exportar",
        metavar="ARQUIVO",
        help="Exportar resultados para arquivo (.json ou .csv).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Exibir trecho completo de cada ocorrência.",
    )
    p.add_argument(
        "--sem-duplicatas",
        action="store_true",
        help="Exibir apenas a primeira ocorrência de cada processo por arquivo.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Coleta PDFs
    pdfs = coletar_pdfs(args.caminhos, args.recursivo)
    if not pdfs:
        print("Nenhum arquivo PDF encontrado nos caminhos informados.")
        sys.exit(1)
    print(f"\n{len(pdfs)} PDF(s) encontrado(s).")

    # Determina temas/termos a pesquisar
    if args.tema:
        temas_alvo = (
            list(TEMAS.items()) if args.tema == "todos"
            else [(args.tema, TEMAS[args.tema])]
        )
    else:
        temas_alvo = [("", {"descricao": "", "termos": [args.termo]})]

    todas: list[Ocorrencia] = []
    idx = 1

    for nome_tema, info_tema in temas_alvo:
        termos = info_tema["termos"]
        descricao = info_tema.get("descricao", "")

        if descricao:
            print(f"\n{'#' * 72}")
            print(f"  TEMA: {descricao}")
            print(f"  Termos: {' | '.join(termos)}")
            print(f"{'#' * 72}")

        processos_vistos: set[tuple[str, str]] = set()  # (arquivo, numero_processo)

        for pdf in pdfs:
            print(f"\n  Lendo: {pdf.name} ...", end="", flush=True)
            ocorrencias = buscar_em_pdf(
                pdf, termos, args.contexto, args.regex, descricao, args.pagina_max
            )
            print(f" {len(ocorrencias)} ocorrência(s)")

            for oc in ocorrencias:
                if args.sem_duplicatas and oc.numero_processo:
                    chave = (oc.arquivo, oc.numero_processo)
                    if chave in processos_vistos:
                        continue
                    processos_vistos.add(chave)

                _imprimir_ocorrencia(oc, idx, args.verbose)
                idx += 1
                todas.append(oc)

    print(f"\n{_SEP}")
    print(f"Total: {len(todas)} ocorrência(s) em {len(pdfs)} arquivo(s).")

    if args.exportar and todas:
        if args.exportar.endswith(".csv"):
            exportar_csv(todas, args.exportar)
        else:
            exportar_json(todas, args.exportar)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(0)
