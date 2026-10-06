"""
build_report_word.py
---------------------
Genera el Reporte IGAE (.docx) 100% en Python (python-docx), a partir del
resumen.json que produce igae_analysis.py. Mismo formato y texto narrativo
que la versión aprobada por SEDECO, pero:
  - Sin gráficas: cada figura se reemplaza por una tabla equivalente.
  - Con comparativo contra el mismo periodo del año anterior.
  - Sin ningún número hardcodeado: todo sale del JSON.

Uso:
    python build_report_word.py --summary output/resumen.json --out output/Reporte_IGAE.docx

Todo el texto narrativo se calcula a partir de los datos del mes (nada de frases
fijas que puedan quedar falsas cuando cambie la tendencia).
"""

import argparse
import json
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BLUE = RGBColor(0x4F, 0x81, 0xBD)
DARK = RGBColor(0x1F, 0x1F, 0x1F)
GRAY = RGBColor(0x6B, 0x6B, 0x6B)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
RED = RGBColor(0xC6, 0x28, 0x28)
HEADER_FILL = "D9E2F3"

HEAD_FONT = "Calibri Light"
BODY_FONT = "Cambria"

AUTOR = "Diego Canales Morales"


# ----------------------------------------------------------------------------
# Helpers de formato
# ----------------------------------------------------------------------------

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fmt_pct(v, decimals=1):
    if v is None:
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def fmt_num(v, decimals=1):
    return "-" if v is None else f"{v:.{decimals}f}"


def color_for_pct(v):
    if v is None:
        return DARK
    return GREEN if v > 0 else (RED if v < 0 else DARK)


def abbr_label(label):
    """'junio de 2025' -> 'jun-25'"""
    if not label:
        return "-"
    try:
        mes, _, anio = label.split(" ")
        return f"{mes[:3]}-{anio[2:]}"
    except ValueError:
        return label


def mes_label(periodo_ym):
    """'2026-05' -> 'mayo de 2026'"""
    anio, mes = periodo_ym.split("-")
    return f"{MESES[int(mes) - 1]} de {anio}"


def set_cell_shading(cell, hex_color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _row_flag(row, tag):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement(tag))


def add_heading(doc, text, level=1):
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    run.font.name = HEAD_FONT
    run.font.size = Pt(16 if level == 1 else 13)
    run.font.bold = True
    run.font.color.rgb = BLUE
    return h


def add_title(doc, text, size_pt, color=BLUE, bold=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = HEAD_FONT
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = color
    return p


def add_paragraph(doc, runs, align=None):
    """runs: lista de dicts {text, bold, color}"""
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    for r in runs:
        run = p.add_run(r["text"])
        run.font.name = BODY_FONT
        run.font.size = Pt(11)
        run.font.bold = r.get("bold", False)
        run.font.color.rgb = r.get("color", DARK)
    return p


def add_table(doc, headers, rows, col_widths_in=None):
    """
    headers: lista de str
    rows: lista de listas de dicts {text, bold, color, align, shade}
    Los encabezados se repiten si la tabla salta de página y ninguna fila se parte.
    """
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"
    table.autofit = False  # respeta los anchos de columna

    hdr = table.rows[0]
    _row_flag(hdr, "w:tblHeader")
    _row_flag(hdr, "w:cantSplit")
    for i, htext in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        if i > 0:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rows and rows[0][i].get("align") == "right" else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(htext)
        run.font.name = BODY_FONT
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = DARK
        set_cell_shading(cell, HEADER_FILL)

    for row in rows:
        tr = table.add_row()
        _row_flag(tr, "w:cantSplit")
        for i, cell_data in enumerate(row):
            cell = tr.cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            if cell_data.get("align") == "right":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run(str(cell_data["text"]))
            run.font.name = BODY_FONT
            run.font.size = Pt(10)
            run.font.bold = cell_data.get("bold", False)
            run.font.color.rgb = cell_data.get("color", DARK)
            if cell_data.get("shade"):
                set_cell_shading(cell, cell_data["shade"])

    if col_widths_in:
        for i, w in enumerate(col_widths_in):
            table.columns[i].width = Inches(w)      # cuadrícula (tblGrid): la que respeta Word/LibreOffice
        for row in table.rows:
            for i, w in enumerate(col_widths_in):
                row.cells[i].width = Inches(w)      # y cada celda
    return table


def add_source_note(doc, periodo_label):
    p1 = doc.add_paragraph()
    r1 = p1.add_run("Fuente: INEGI | Indicador Global de la Actividad Económica (IGAE) — Banco de Información Económica (BIE)")
    r1.font.italic = True
    r1.font.size = Pt(9)
    r1.font.color.rgb = GRAY
    r1.font.name = BODY_FONT

    p2 = doc.add_paragraph()
    r2 = p2.add_run(f"Cifras correspondientes a {periodo_label}, según los datos de INEGI vigentes al generar el reporte "
                    "(las cifras más recientes son preliminares y están sujetas a revisión).")
    r2.font.italic = True
    r2.font.size = Pt(9)
    r2.font.color.rgb = GRAY
    r2.font.name = BODY_FONT


# ----------------------------------------------------------------------------
# Texto narrativo (calculado a partir de los datos del mes)
# ----------------------------------------------------------------------------

def texto_tendencia(summary):
    t = summary["total"]
    periodo_label = summary["periodo_label"]
    partes = ["La siguiente tabla resume el comparativo anual del índice general y su tendencia en los últimos 12 meses."]

    anuales = [r["variacion_anual_pct"] for r in summary["tendencia"]["total_ultimos_meses"]
               if r.get("variacion_anual_pct") is not None]
    if anuales:
        positivos = sum(1 for v in anuales if v > 0)
        partes.append(f"En {positivos} de los últimos {len(anuales)} meses el índice registró una variación anual positiva.")

    if t.get("es_maximo_historico"):
        partes.append(f"El nivel de {periodo_label} es el más alto de toda la serie histórica.")
    else:
        partes.append(f"El máximo histórico del índice se registró en {mes_label(t['maximo_historico_periodo'])} "
                      f"({t['maximo_historico_valor']} puntos).")

    partes.append("A largo plazo, el indicador mantiene una tendencia creciente desde 1993, con caídas puntuales "
                  "asociadas a crisis económicas (la más pronunciada, la de 2020 por la pandemia de COVID-19).")
    return " ".join(partes)


def texto_actividades(summary):
    s = summary["sectores"]
    anyo = summary.get("anyo_anterior_label") or "el mismo periodo del año anterior"
    por_nivel = sorted(s, key=lambda x: x["nivel"], reverse=True)
    por_crec = sorted(s, key=lambda x: x["variacion_anual"], reverse=True)
    return (
        f"En {summary['periodo_label']}, la actividad económica con mayor nivel de índice fue "
        f"{por_nivel[0]['sector']} con un valor de {por_nivel[0]['nivel']}, seguida de "
        f"{por_nivel[1]['sector']} con {por_nivel[1]['nivel']} y {por_nivel[2]['sector']} con {por_nivel[2]['nivel']}. "
        f"En términos de crecimiento anual, {por_crec[0]['sector']} registró la mayor variación "
        f"({fmt_pct(por_crec[0]['variacion_anual'])}), seguida de {por_crec[1]['sector']} "
        f"({fmt_pct(por_crec[1]['variacion_anual'])}) y {por_crec[2]['sector']} "
        f"({fmt_pct(por_crec[2]['variacion_anual'])}). La siguiente tabla muestra el nivel del IGAE por actividad "
        f"económica y su comparación contra {anyo}."
    )


def texto_subsectores(summary, detalle):
    todos = [r for g in detalle for r in g["subsectores"] if r.get("contribucion_pp") is not None]
    n = len(todos)
    t = summary["total"]
    txt = (
        f"La siguiente tabla desglosa el IGAE de {summary['periodo_label']} en los {n} subsectores que lo integran, "
        "agrupados por gran actividad. Para cada uno se presenta su variación anual, su variación acumulada en lo que va "
        "del año y su contribución, en puntos porcentuales (pp), a la variación anual del IGAE total; la suma de las "
        f"contribuciones equivale a la variación anual del índice general ({fmt_pct(t['variacion_anual_pct'])})."
    )
    if todos:
        mejor = max(todos, key=lambda r: r["contribucion_pp"])
        peor = min(todos, key=lambda r: r["contribucion_pp"])
        txt += f" {mejor['nombre']} fue el subsector que más aportó ({mejor['contribucion_pp']:.2f} pp)"
        if peor["contribucion_pp"] < 0:
            txt += f", mientras que {peor['nombre']} fue el que más restó ({peor['contribucion_pp']:.2f} pp)."
        else:
            txt += "."
    return txt


# ----------------------------------------------------------------------------
# Construcción del documento
# ----------------------------------------------------------------------------

def build_report(summary: dict, out_path: str, autor: str = AUTOR):
    t = summary["total"]
    periodo_label = summary["periodo_label"]
    anyo_ant_label = summary.get("anyo_anterior_label")
    sectores_por_nivel = sorted(summary["sectores"], key=lambda s: s["nivel"], reverse=True)
    detalle = summary.get("subsectores_detalle") or []
    ant_corto = abbr_label(anyo_ant_label)

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    # --- Portada ---
    add_title(doc, "Índice Global de la Actividad Económica (IGAE)", 22)
    add_title(doc, autor, 11, color=DARK, bold=False)
    add_title(doc, periodo_label.replace(" de ", " ").title(), 11, color=DARK, bold=False)

    # --- Sección 1: Evolución general del IGAE ---
    add_heading(doc, "Evolución general del IGAE")
    if t.get("nivel_anyo_anterior") is not None:
        comparativo_txt = (f" En comparación con {anyo_ant_label} (cuando el índice se ubicó en {t['nivel_anyo_anterior']} "
                           f"puntos), esto representa una variación anual de {fmt_pct(t['variacion_anual_pct'])}.")
    else:
        comparativo_txt = (f" Esto representa una variación anual de {fmt_pct(t['variacion_anual_pct'])} "
                           "respecto al mismo mes del año anterior.")
    add_paragraph(doc, [
        {"text": f"Durante {periodo_label}, el IGAE General se ubicó en {t['nivel']} puntos (base 2018=100). "
                 f"Esto representa una variación mensual de {fmt_pct(t['variacion_mensual_pct'])} respecto al mes "
                 f"inmediato anterior." + comparativo_txt},
    ])

    # --- Sección 2: Evolución histórica del IGAE General ---
    add_heading(doc, "Evolución histórica del IGAE General")
    add_paragraph(doc, [{"text": texto_tendencia(summary)}])

    add_paragraph(doc, [{"text": f"Comparativo anual — {anyo_ant_label or 'año anterior'} vs. {periodo_label}", "bold": True}])
    add_table(
        doc,
        ["Indicador", ant_corto, abbr_label(periodo_label), "Variación"],
        [[
            {"text": "Nivel del índice"},
            {"text": fmt_num(t.get("nivel_anyo_anterior")), "align": "right"},
            {"text": fmt_num(t["nivel"]), "align": "right"},
            {"text": fmt_pct(t["variacion_anual_pct"]), "bold": True, "color": color_for_pct(t["variacion_anual_pct"]), "align": "right"},
        ]],
        col_widths_in=[2.6, 1.3, 1.3, 1.3],
    )
    doc.add_paragraph()

    add_paragraph(doc, [{"text": "Nivel mensual (últimos 12 meses)", "bold": True}])
    add_table(
        doc,
        ["Periodo", "Nivel del Índice", "Variación % anual"],
        [
            [
                {"text": r["periodo_label"]},
                {"text": fmt_num(r["nivel"]), "align": "right"},
                {"text": fmt_pct(r["variacion_anual_pct"]), "color": color_for_pct(r["variacion_anual_pct"]), "align": "right"},
            ]
            for r in summary["tendencia"]["total_ultimos_meses"]
        ],
        col_widths_in=[2.2, 2.2, 2.1],
    )
    doc.add_paragraph()

    # --- Sección 3: IGAE por Grandes Actividades ---
    add_heading(doc, "IGAE por Grandes Actividades (Primarias, Secundarias y Terciarias)")
    add_paragraph(doc, [{"text": texto_actividades(summary)}])
    add_table(
        doc,
        ["Actividad Económica", f"Nivel {ant_corto}", "Nivel actual", "Var. anual", "Var. acumulada", "Contrib. (pp)"],
        [
            [
                {"text": s["sector"]},
                {"text": fmt_num(s.get("nivel_anyo_anterior")), "align": "right"},
                {"text": fmt_num(s["nivel"]), "align": "right"},
                {"text": fmt_pct(s["variacion_anual"]), "color": color_for_pct(s["variacion_anual"]), "align": "right"},
                {"text": fmt_pct(s["variacion_acumulada"]), "color": color_for_pct(s["variacion_acumulada"]), "align": "right"},
                {"text": fmt_num(s["contribucion_pp"], 2), "align": "right"},
            ]
            for s in sectores_por_nivel
        ],
        col_widths_in=[1.6, 1.0, 0.9, 0.9, 1.1, 1.0],
    )
    doc.add_paragraph()

    # --- Sección 4: Detalle por subsector ---
    if detalle:
        add_heading(doc, "Detalle por subsector (Primarias, Secundarias y Terciarias)")
        add_paragraph(doc, [{"text": texto_subsectores(summary, detalle)}])
        rows = []
        for g in detalle:
            tg = g["total"]
            shade = "EAF1FB"
            rows.append([
                {"text": g["sector"], "bold": True, "shade": shade},
                {"text": fmt_pct(tg["variacion_anual_pct"]), "bold": True, "color": color_for_pct(tg["variacion_anual_pct"]), "align": "right", "shade": shade},
                {"text": fmt_pct(tg["variacion_acumulada_pct"]), "bold": True, "color": color_for_pct(tg["variacion_acumulada_pct"]), "align": "right", "shade": shade},
                {"text": fmt_num(tg["contribucion_pp"], 2), "bold": True, "color": color_for_pct(tg["contribucion_pp"]), "align": "right", "shade": shade},
            ])
            for r in g["subsectores"]:
                rows.append([
                    {"text": f"{r['codigo']}  {r['nombre']}"},
                    {"text": fmt_pct(r["variacion_anual_pct"]), "color": color_for_pct(r["variacion_anual_pct"]), "align": "right"},
                    {"text": fmt_pct(r["variacion_acumulada_pct"]), "color": color_for_pct(r["variacion_acumulada_pct"]), "align": "right"},
                    {"text": fmt_num(r["contribucion_pp"], 2), "color": color_for_pct(r["contribucion_pp"]), "align": "right"},
                ])
        add_table(
            doc,
            ["Actividad / Subsector", "Var. anual", "Var. acumulada", "Contrib. (pp)"],
            rows,
            col_widths_in=[3.3, 0.95, 1.2, 1.05],
        )
        doc.add_paragraph()

    # --- Sección 5: Tendencias Históricas ---
    add_heading(doc, "Tendencias Históricas")
    add_paragraph(doc, [
        {"text": "La siguiente tabla muestra el comportamiento del índice para los tres grandes sectores "
                 "económicos (primarias, secundarias y terciarias) en los últimos 12 meses, lo que permite "
                 "identificar la tendencia reciente de cada uno."},
    ])
    add_table(
        doc,
        ["Periodo", "Primarias", "Secundarias", "Terciarias"],
        [
            [
                {"text": r["periodo_label"]},
                {"text": fmt_num(r.get("Actividades primarias")), "align": "right"},
                {"text": fmt_num(r.get("Actividades secundarias")), "align": "right"},
                {"text": fmt_num(r.get("Actividades terciarias")), "align": "right"},
            ]
            for r in summary["tendencia"]["sectores_ultimos_meses"]
        ],
        col_widths_in=[1.6, 1.6, 1.6, 1.6],
    )
    doc.add_paragraph()

    add_source_note(doc, periodo_label)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    print(f"Reporte generado: {out_path}")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Genera el Reporte IGAE en Word (python-docx)")
    ap.add_argument("--summary", default="output/resumen.json", help="Ruta al resumen.json (de igae_analysis.py)")
    ap.add_argument("--out", default="output/Reporte_IGAE.docx", help="Ruta del .docx de salida")
    ap.add_argument("--autor", default=AUTOR, help="Nombre que aparece en la portada")
    args = ap.parse_args()

    with open(args.summary, encoding="utf-8") as f:
        summary = json.load(f)

    build_report(summary, args.out, autor=args.autor)


if __name__ == "__main__":
    main()
