#!/usr/bin/env python3
"""
Pesquisa de jurisprudência em direito bancário.

Tribunais suportados:
  - STJ   (Superior Tribunal de Justiça)
  - TJRJ  (Tribunal de Justiça do Rio de Janeiro)

Temas pré-configurados (--tema):
  cheque-especial   Juros de cheque especial / crédito rotativo
  capitalizacao     Capitalização mensal de juros / anatocismo
  mora              Descaracterização da mora
  abusividade       Abusividade da taxa de juros
  boa-fe            Boa-fé contratual / boa-fé objetiva
  clausulas         Ambiguidade / abusividade de cláusulas contratuais
  transparencia     Dever de transparência (CDC e CC)

Uso:
  python jurisprudencia.py --tema cheque-especial --tribunal stj
  python jurisprudencia.py --tema abusividade --tribunal todos --exportar resultado.json
  python jurisprudencia.py "taxa de juros abusiva CDC" --tribunal tjrj --pagina 2
  python jurisprudencia.py --tema todos --tribunal todos --exportar bancario.csv
"""

import argparse
import csv
import json
import re
import sys
import textwrap
from dataclasses import asdict, dataclass
from typing import Callable

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

TIMEOUT = 20  # segundos

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# ---------------------------------------------------------------------------
# Temas de direito bancário pré-configurados
# ---------------------------------------------------------------------------
# Cada tema mapeia para um conjunto de termos de busca (listas alternativas).
# O script fará uma busca por termo; para --tema todos, roda cada tema uma vez.

TEMAS: dict[str, dict] = {
    "cheque-especial": {
        "descricao": "Juros de cheque especial / crédito rotativo",
        "termos": [
            "cheque especial crédito rotativo juros",
            "crédito rotativo capitalização juros",
        ],
    },
    "capitalizacao": {
        "descricao": "Capitalização mensal de juros / anatocismo",
        "termos": [
            "capitalização mensal juros bancários",
            "anatocismo contrato bancário",
        ],
    },
    "mora": {
        "descricao": "Descaracterização da mora",
        "termos": [
            "descaracterização da mora cobrança abusiva",
            "mora descaracterizada encargos excessivos",
        ],
    },
    "abusividade": {
        "descricao": "Abusividade da taxa de juros",
        "termos": [
            "abusividade taxa de juros contrato bancário CDC",
            "taxa de juros abusiva revisão contratual",
        ],
    },
    "boa-fe": {
        "descricao": "Boa-fé contratual / boa-fé objetiva",
        "termos": [
            "boa-fé objetiva contrato bancário",
            "boa fé contratual banco consumidor",
        ],
    },
    "clausulas": {
        "descricao": "Ambiguidade / abusividade de cláusulas contratuais",
        "termos": [
            "cláusula abusiva contrato bancário revisão",
            "ambiguidade cláusula contrato interpretação favorável consumidor",
        ],
    },
    "transparencia": {
        "descricao": "Dever de transparência (CDC e CC)",
        "termos": [
            "dever de transparência contrato bancário CDC",
            "transparência informação contrato financeiro Código Civil",
        ],
    },
}


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------


@dataclass
class Decisao:
    tribunal: str
    numero: str
    tipo: str = ""       # Acórdão, Decisão Monocrática, Súmula …
    relator: str = ""
    orgao: str = ""      # Turma / Câmara
    data: str = ""
    ementa: str = ""
    tema: str = ""       # tema bancário que originou a busca
    url: str = ""


# ---------------------------------------------------------------------------
# STJ
# ---------------------------------------------------------------------------

_STJ_BASE = "https://scon.stj.jus.br/SCON"
_STJ_SEARCH = _STJ_BASE + "/pesquisar.jsp"


def buscar_stj(
    termo: str,
    pagina: int = 1,
    por_pagina: int = 10,
) -> tuple[list[Decisao], int]:
    """Busca acórdãos no STJ."""
    s = requests.Session()
    s.headers.update(HEADERS)
    inicio = (pagina - 1) * por_pagina + 1
    params = {
        "b": "ACOR",
        "livre": termo,
        "p": "true",
        "thesaurus": "JURIDICO",
        "operador": "e",
        "tipo_visualizacao": "RESUMO",
        "i": str(inicio),
        "quantidade": str(por_pagina),
    }
    try:
        resp = s.get(_STJ_SEARCH, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Erro de conexão com o STJ: {e}") from e
    return _parse_stj(resp.text, por_pagina)


def _parse_stj(html: str, por_pagina: int) -> tuple[list[Decisao], int]:
    soup = BeautifulSoup(html, "lxml")
    decisoes: list[Decisao] = []
    total_paginas = 1

    # Total de documentos
    total_txt = soup.find(string=re.compile(r"\d+\s+documento", re.I))
    if total_txt:
        m = re.search(r"(\d+)", total_txt)
        if m:
            total_docs = int(m.group(1))
            total_paginas = max(1, (total_docs + por_pagina - 1) // por_pagina)

    for bloco in soup.find_all("div", class_=re.compile(r"documento", re.I)):
        d = Decisao(tribunal="STJ", numero="")

        cabecalho = bloco.find(class_=re.compile(r"cabecalho|header", re.I))
        if cabecalho:
            texto_cab = cabecalho.get_text(" | ", strip=True)

            m_num = re.search(
                r"(REsp|AgRg|AgInt|HC|RMS|MS|AREsp|EAREsp|CC|RHC|SDI|AR|ACO|REL)\s*[\w\-\.]+",
                texto_cab, re.I,
            )
            if m_num:
                d.numero = m_num.group(0).strip()
                d.tipo = m_num.group(1).upper()

            m_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", texto_cab)
            if m_data:
                d.data = m_data.group(1)

            m_rel = re.search(r"Relator[a]?[:\s]+([^|;\n]+)", texto_cab, re.I)
            if m_rel:
                d.relator = m_rel.group(1).strip()

            m_org = re.search(
                r"(T\d|PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|SEXTA|[SC]EÇ[ÃA]O\b[^|]*)",
                texto_cab, re.I,
            )
            if m_org:
                d.orgao = m_org.group(0).strip()

        ementa_el = bloco.find(class_=re.compile(r"ementa", re.I)) or bloco.find("p")
        if ementa_el:
            d.ementa = ementa_el.get_text(" ", strip=True)

        link = bloco.find("a", href=re.compile(r"num_registro|processo|detalhe", re.I))
        if link:
            href = link.get("href", "")
            d.url = (_STJ_BASE + href) if not href.startswith("http") else href

        if d.numero or d.ementa:
            decisoes.append(d)

    return decisoes, total_paginas


# ---------------------------------------------------------------------------
# TJRJ
# ---------------------------------------------------------------------------

_TJRJ_SEARCH = "https://www4.tjrj.jus.br/ejud/ConsultaJurisprudencia.aspx"


def buscar_tjrj(
    termo: str,
    pagina: int = 1,
    por_pagina: int = 10,
) -> tuple[list[Decisao], int]:
    """
    Busca jurisprudência no TJRJ.
    A pesquisa usa o portal ASPX do TJRJ (requer ViewState).
    """
    s = requests.Session()
    s.headers.update(HEADERS)

    # 1ª requisição: buscar o ViewState da página
    try:
        get_resp = s.get(_TJRJ_SEARCH, timeout=TIMEOUT)
        get_resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Erro de conexão com o TJRJ: {e}") from e

    soup_get = BeautifulSoup(get_resp.text, "lxml")
    viewstate = _campo_hidden(soup_get, "__VIEWSTATE")
    viewstate_gen = _campo_hidden(soup_get, "__VIEWSTATEGENERATOR")
    event_val = _campo_hidden(soup_get, "__EVENTVALIDATION")

    # 2ª requisição: submeter a busca
    data = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": viewstate_gen,
        "__EVENTVALIDATION": event_val,
        "ctl00$ContentPlaceHolder1$TxtEmenta": termo,
        "ctl00$ContentPlaceHolder1$BtnPesquisar": "Pesquisar",
        "ctl00$ContentPlaceHolder1$TxtNumero": "",
        "ctl00$ContentPlaceHolder1$TxtRelator": "",
    }
    try:
        post_resp = s.post(
            _TJRJ_SEARCH, data=data, timeout=TIMEOUT,
            headers={**HEADERS, "Referer": _TJRJ_SEARCH},
        )
        post_resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Erro ao submeter busca no TJRJ: {e}") from e

    decisoes, total_paginas = _parse_tjrj(post_resp.text, por_pagina)

    # Paginação: se solicitado, navegar para a página correta
    if pagina > 1 and total_paginas >= pagina:
        decisoes, total_paginas = _paginar_tjrj(
            s, post_resp.text, pagina, por_pagina
        )

    return decisoes, total_paginas


def _campo_hidden(soup: BeautifulSoup, name: str) -> str:
    el = soup.find("input", {"name": name, "type": "hidden"})
    return el["value"] if el else ""


def _parse_tjrj(html: str, por_pagina: int) -> tuple[list[Decisao], int]:
    soup = BeautifulSoup(html, "lxml")
    decisoes: list[Decisao] = []
    total_paginas = 1

    # Total de resultados
    total_el = soup.find(string=re.compile(r"resultado|encontrado|Total", re.I))
    if total_el:
        m = re.search(r"(\d[\d\.]*)", total_el)
        if m:
            total_docs = int(m.group(1).replace(".", ""))
            total_paginas = max(1, (total_docs + por_pagina - 1) // por_pagina)

    # Tabela de resultados
    tabela = soup.find("table", id=re.compile(r"Grid|Result|Lista", re.I))
    if not tabela:
        tabela = soup.find("table", class_=re.compile(r"Grid|Result|Lista", re.I))
    if not tabela:
        # Tenta qualquer tabela com dados relevantes
        for t in soup.find_all("table"):
            if t.find(string=re.compile(r"Acórdão|Número|Ementa", re.I)):
                tabela = t
                break

    if tabela:
        linhas = tabela.find_all("tr")
        for linha in linhas[1:]:  # pula cabeçalho
            cols = linha.find_all("td")
            if len(cols) < 2:
                continue
            textos = [c.get_text(" ", strip=True) for c in cols]

            d = Decisao(tribunal="TJRJ", numero="")

            # Tenta extrair número CNJ da primeira coluna ou texto geral
            linha_txt = " ".join(textos)
            m_num = re.search(
                r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
                r"|\d{4}\.\d{3}\.\d{6}-\d"
                r"|(?:APL|AC|AI|RG|Rec)\s*[\d\.\-/]+",
                linha_txt, re.I,
            )
            if m_num:
                d.numero = m_num.group(0).strip()

            m_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", linha_txt)
            if m_data:
                d.data = m_data.group(1)

            # Ementa: coluna mais longa
            d.ementa = max(textos, key=len)[:600]

            link = linha.find("a", href=True)
            if link:
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://www4.tjrj.jus.br" + href
                d.url = href

            if d.numero or (d.ementa and len(d.ementa) > 30):
                decisoes.append(d)
    else:
        # Fallback: blocos de texto livre
        for bloco in soup.find_all(
            ["div", "article"],
            class_=re.compile(r"acordao|julgado|resultado|ementa", re.I),
        ):
            texto = bloco.get_text(" ", strip=True)
            if len(texto) < 40:
                continue
            d = Decisao(tribunal="TJRJ", numero="", ementa=texto[:600])
            m_num = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", texto)
            if m_num:
                d.numero = m_num.group(0)
            m_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", texto)
            if m_data:
                d.data = m_data.group(1)
            link = bloco.find("a", href=True)
            if link:
                d.url = link["href"]
            decisoes.append(d)

    return decisoes, total_paginas


def _paginar_tjrj(
    s: requests.Session, html_primeira: str, pagina: int, por_pagina: int
) -> tuple[list[Decisao], int]:
    """Navega para página N usando o mecanismo de postback do TJRJ."""
    soup = BeautifulSoup(html_primeira, "lxml")
    viewstate = _campo_hidden(soup, "__VIEWSTATE")
    viewstate_gen = _campo_hidden(soup, "__VIEWSTATEGENERATOR")
    event_val = _campo_hidden(soup, "__EVENTVALIDATION")

    data = {
        "__EVENTTARGET": f"ctl00$ContentPlaceHolder1$GridJulgados$ctl01$lbPage{pagina}",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": viewstate_gen,
        "__EVENTVALIDATION": event_val,
    }
    try:
        resp = s.post(
            _TJRJ_SEARCH, data=data, timeout=TIMEOUT,
            headers={**HEADERS, "Referer": _TJRJ_SEARCH},
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Erro ao paginar no TJRJ: {e}") from e

    return _parse_tjrj(resp.text, por_pagina)


# ---------------------------------------------------------------------------
# Mapa de funções por tribunal
# ---------------------------------------------------------------------------

TRIBUNAIS: dict[str, Callable] = {
    "stj": buscar_stj,
    "tjrj": buscar_tjrj,
}


# ---------------------------------------------------------------------------
# Exibição no terminal
# ---------------------------------------------------------------------------

_SEP = "─" * 72


def _imprimir_decisao(d: Decisao, indice: int, verbose: bool) -> None:
    print(f"\n{_SEP}")
    cab = f"[{indice}] {d.tribunal}"
    if d.tipo:
        cab += f"  {d.tipo}"
    if d.numero:
        cab += f"  {d.numero}"
    print(cab)
    if d.tema:
        print(f"    Tema      : {d.tema}")
    if d.data:
        print(f"    Data      : {d.data}")
    if d.relator:
        print(f"    Relator   : {d.relator}")
    if d.orgao:
        print(f"    Órgão     : {d.orgao}")
    if d.url:
        print(f"    URL       : {d.url}")
    if d.ementa:
        limite = None if verbose else 300
        texto = d.ementa[:limite] + ("…" if limite and len(d.ementa) > limite else "")
        wrapped = textwrap.fill(
            texto, width=70, initial_indent="    ", subsequent_indent="    "
        )
        print(f"    Ementa:\n{wrapped}")


def _imprimir_cabecalho_tema(nome: str, info: dict) -> None:
    print(f"\n{'#' * 72}")
    print(f"  TEMA: {info['descricao']}")
    print(f"{'#' * 72}")


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------


def exportar_json(decisoes: list[Decisao], caminho: str) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump([asdict(d) for d in decisoes], f, ensure_ascii=False, indent=2)
    print(f"\nResultados exportados para: {caminho}")


def exportar_csv(decisoes: list[Decisao], caminho: str) -> None:
    if not decisoes:
        return
    campos = list(asdict(decisoes[0]).keys())
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(asdict(d) for d in decisoes)
    print(f"\nResultados exportados para: {caminho}")


# ---------------------------------------------------------------------------
# Execução de uma busca simples (termo + tribunal)
# ---------------------------------------------------------------------------


def _executar_busca(
    termo: str,
    tribunais_alvo: list[str],
    pagina: int,
    por_pagina: int,
    verbose: bool,
    tema_nome: str = "",
) -> list[Decisao]:
    todas: list[Decisao] = []
    idx_base = 1

    for trib in tribunais_alvo:
        fn = TRIBUNAIS[trib]
        print(f"\n{'=' * 72}")
        print(f"  {trib.upper()}  —  \"{termo}\"")
        print(f"{'=' * 72}")

        try:
            resultados, total_pags = fn(termo, pagina=pagina, por_pagina=por_pagina)
        except ConnectionError as e:
            print(f"  ERRO: {e}")
            continue
        except Exception as e:
            print(f"  ERRO inesperado: {e}")
            continue

        if not resultados:
            print("  Nenhum resultado encontrado.")
            continue

        print(f"  {len(resultados)} resultado(s) — página {pagina}/{total_pags}")

        for d in resultados:
            d.tema = tema_nome
            _imprimir_decisao(d, idx_base, verbose)
            idx_base += 1
            todas.append(d)

    return todas


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    nomes_temas = list(TEMAS.keys()) + ["todos"]
    desc_temas = "\n".join(
        f"  {k:<20} {v['descricao']}" for k, v in TEMAS.items()
    )

    p = argparse.ArgumentParser(
        prog="jurisprudencia",
        description="Pesquisa de jurisprudência em direito bancário (STJ e TJRJ).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Temas disponíveis (--tema):\n"
            + desc_temas + "\n"
            + "  todos                Pesquisa todos os temas acima\n\n"
            "Exemplos:\n"
            "  python jurisprudencia.py --tema cheque-especial\n"
            "  python jurisprudencia.py --tema abusividade --tribunal stj --max 5\n"
            "  python jurisprudencia.py --tema todos --exportar bancario.json\n"
            "  python jurisprudencia.py \"taxa de juros abusiva\" --tribunal tjrj\n"
        ),
    )

    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "termos",
        nargs="*",
        default=None,
        help="Termos livres de pesquisa.",
    )
    grupo.add_argument(
        "--tema",
        choices=nomes_temas,
        metavar="TEMA",
        help=f"Tema bancário pré-configurado: {{{', '.join(nomes_temas)}}}.",
    )

    p.add_argument(
        "--tribunal",
        choices=["stj", "tjrj", "todos"],
        default="todos",
        help="Tribunal a pesquisar (padrão: todos).",
    )
    p.add_argument(
        "--pagina",
        type=int,
        default=1,
        metavar="N",
        help="Página dos resultados (padrão: 1).",
    )
    p.add_argument(
        "--max",
        type=int,
        default=10,
        metavar="N",
        help="Máximo de resultados por tribunal (padrão: 10).",
    )
    p.add_argument(
        "--exportar",
        metavar="ARQUIVO",
        help="Exportar resultados para arquivo (.json ou .csv).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Exibir ementa completa.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    tribunais_alvo = list(TRIBUNAIS.keys()) if args.tribunal == "todos" else [args.tribunal]
    todas: list[Decisao] = []

    # ── Modo tema ──────────────────────────────────────────────────────────
    if args.tema:
        temas_a_pesquisar = (
            list(TEMAS.items()) if args.tema == "todos"
            else [(args.tema, TEMAS[args.tema])]
        )
        for nome_tema, info_tema in temas_a_pesquisar:
            _imprimir_cabecalho_tema(nome_tema, info_tema)
            # Usa apenas o primeiro termo de cada tema (mais preciso)
            termo_principal = info_tema["termos"][0]
            resultado_tema = _executar_busca(
                termo_principal,
                tribunais_alvo,
                args.pagina,
                args.max,
                args.verbose,
                tema_nome=info_tema["descricao"],
            )
            todas.extend(resultado_tema)

    # ── Modo termos livres ─────────────────────────────────────────────────
    else:
        if not args.termos:
            parser.error("Informe termos de pesquisa ou use --tema.")
        termo = " ".join(args.termos)
        resultado = _executar_busca(
            termo, tribunais_alvo, args.pagina, args.max, args.verbose
        )
        todas.extend(resultado)

    # ── Sumário ────────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print(f"Total geral: {len(todas)} decisão(ões) encontrada(s).")

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
