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


# Formato

def fmt_pct(v, decimals=1):
    if v is None:
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def color_for_pct(v):
    if v is None:
        return DARK
    return GREEN if v > 0 else (RED if v < 0 else DARK)


def set_cell_shading(cell, hex_color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


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
    rows: lista de listas de dicts {text, bold, color, align}
    """
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"

    hdr_cells = table.rows[0].cells
    for i, htext in enumerate(headers):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        run = p.add_run(htext)
        run.font.name = BODY_FONT
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = DARK
        set_cell_shading(hdr_cells[i], HEADER_FILL)

    for row in rows:
        cells = table.add_row().cells
        for i, cell_data in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            if cell_data.get("align") == "right":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run(str(cell_data["text"]))
            run.font.name = BODY_FONT
            run.font.size = Pt(10)
            run.font.bold = cell_data.get("bold", False)
            run.font.color.rgb = cell_data.get("color", DARK)

    if col_widths_in:
        for row in table.rows:
            for i, w in enumerate(col_widths_in):
                row.cells[i].width = Inches(w)
    return table


def add_source_note(doc, periodo_label):
    p1 = doc.add_paragraph()
    r1 = p1.add_run("Fuente: INEGI | Indicador Global de la Actividad Económica (IGAE) — Banco de Información Económica (BIE)")
    r1.font.italic = True
    r1.font.size = Pt(9)
    r1.font.color.rgb = GRAY
    r1.font.name = BODY_FONT

    p2 = doc.add_paragraph()
    r2 = p2.add_run(f"Cifra correspondiente a {periodo_label}, dato preliminar sujeto a revisión")
    r2.font.italic = True
    r2.font.size = Pt(9)
    r2.font.color.rgb = GRAY
    r2.font.name = BODY_FONT


# Construcción del documento

def build_report(summary: dict, out_path: str):
    t = summary["total"]
    periodo_label = summary["periodo_label"]
    prev_label = summary.get("prev_periodo_label")
    anyo_ant_label = summary.get("anyo_anterior_label")
    sectores_ordenados = sorted(summary["sectores"], key=lambda s: s["variacion_anual"], reverse=True)

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
    add_title(doc, AUTOR, 11, color=DARK, bold=False)
    add_title(doc, periodo_label.replace(" de ", " ").title(), 11, color=DARK, bold=False)

    # --- Sección 1: Evolución general del IGAE ---
    add_heading(doc, "Evolución general del IGAE")
    comparativo_txt = (
        f" En comparación con {anyo_ant_label} (cuando el índice se ubicó en {t['nivel_anyo_anterior']} puntos), "
        f"esto representa una variación anual de {fmt_pct(t['variacion_anual_pct'])}."
        if t.get("nivel_anyo_anterior") is not None
        else f" Esto representa una variación anual de {fmt_pct(t['variacion_anual_pct'])} respecto al mismo mes del año anterior."
    )
    add_paragraph(doc, [
        {"text": f"Durante {periodo_label}, el IGAE General se ubicó en {t['nivel']} puntos (base 2018=100). "
                 f"Esto representa una variación mensual de {fmt_pct(t['variacion_mensual_pct'])} respecto al mes "
                 f"inmediato anterior." + comparativo_txt},
    ])

    # --- Sección 2: Evolución histórica del IGAE General ---
    add_heading(doc, "Evolución histórica del IGAE General")
    add_paragraph(doc, [
        {"text": "La siguiente tabla resume el comparativo anual del índice general y su tendencia en los "
                 "últimos 12 meses. En el periodo se observa una tendencia de crecimiento moderado, "
                 "consistente con el comportamiento de mediano plazo del indicador desde 1993, interrumpido "
                 "históricamente solo por caídas puntuales asociadas a crisis económicas (la más pronunciada, "
                 "la de 2020 por la pandemia de COVID-19)."},
    ])

    add_paragraph(doc, [{"text": f"Comparativo anual — {anyo_ant_label or 'año anterior'} vs. {periodo_label}", "bold": True}])
    add_table(
        doc,
        ["Indicador", anyo_ant_label or "-", periodo_label, "Variación"],
        [
            [
                {"text": "Nivel del índice"},
                {"text": t.get("nivel_anyo_anterior", "-"), "align": "right"},
                {"text": t["nivel"], "align": "right"},
                {"text": fmt_pct(t["variacion_anual_pct"]), "bold": True, "color": color_for_pct(t["variacion_anual_pct"]), "align": "right"},
            ],
        ],
        col_widths_in=[2.5, 1.3, 1.3, 1.3],
    )
    doc.add_paragraph()

    add_paragraph(doc, [{"text": "Nivel mensual (últimos 12 meses)", "bold": True}])
    trend_rows = summary["tendencia"]["total_ultimos_meses"]
    add_table(
        doc,
        ["Periodo", "Nivel del Índice", "Variación % anual"],
        [
            [
                {"text": r["periodo_label"]},
                {"text": r["nivel"], "align": "right"},
                {"text": fmt_pct(r["variacion_anual_pct"]), "color": color_for_pct(r["variacion_anual_pct"]), "align": "right"},
            ]
            for r in trend_rows
        ],
        col_widths_in=[2.2, 2.2, 2.0],
    )
    doc.add_paragraph()

    # --- Sección 3: IGAE por Grandes Actividades ---
    add_heading(doc, "IGAE por Grandes Actividades (Primarias, Secundarias y Terciarias)")
    add_paragraph(doc, [
        {"text": f"En {periodo_label}, la actividad económica con mayor nivel de índice fue "
                 f"{sectores_ordenados[0]['sector']} con un valor de {sectores_ordenados[0]['nivel']}, seguida de "
                 f"{sectores_ordenados[1]['sector']} con {sectores_ordenados[1]['nivel']} y "
                 f"{sectores_ordenados[2]['sector']} con {sectores_ordenados[2]['nivel']}. La siguiente tabla "
                 f"muestra el nivel del IGAE por actividad económica y su comparación contra "
                 f"{anyo_ant_label or 'el mismo periodo del año anterior'}."},
    ])
    add_table(
        doc,
        ["Actividad Económica", f"Nivel {anyo_ant_label or 'año ant.'}", "Nivel Actual", "Var. Anual", "Var. Acumulada", "Contrib. (pp)"],
        [
            [
                {"text": s["sector"]},
                {"text": s.get("nivel_anyo_anterior", "-"), "align": "right"},
                {"text": s["nivel"], "align": "right"},
                {"text": fmt_pct(s["variacion_anual"]), "color": color_for_pct(s["variacion_anual"]), "align": "right"},
                {"text": fmt_pct(s["variacion_acumulada"]), "color": color_for_pct(s["variacion_acumulada"]), "align": "right"},
                {"text": f"{s['contribucion_pp']:.2f}", "align": "right"},
            ]
            for s in sectores_ordenados
        ],
        col_widths_in=[1.9, 1.1, 1.0, 0.9, 1.1, 1.0],
    )
    doc.add_paragraph()

    # --- Sección 4: Tendencias Históricas ---
    add_heading(doc, "Tendencias Históricas")
    add_paragraph(doc, [
        {"text": "La siguiente tabla muestra el comportamiento del índice para los tres grandes sectores "
                 "económicos (primarias, secundarias y terciarias) en los últimos 12 meses, lo que permite "
                 "identificar la tendencia reciente de cada uno sin depender de una gráfica."},
    ])
    sector_rows = summary["tendencia"]["sectores_ultimos_meses"]
    add_table(
        doc,
        ["Periodo", "Primarias", "Secundarias", "Terciarias"],
        [
            [
                {"text": r["periodo_label"]},
                {"text": r.get("Actividades primarias", "-"), "align": "right"},
                {"text": r.get("Actividades secundarias", "-"), "align": "right"},
                {"text": r.get("Actividades terciarias", "-"), "align": "right"},
            ]
            for r in sector_rows
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
    args = ap.parse_args()

    with open(args.summary, encoding="utf-8") as f:
        summary = json.load(f)

    build_report(summary, args.out)


if __name__ == "__main__":
    main()
