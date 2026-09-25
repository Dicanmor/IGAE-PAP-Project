"""
run_pipeline.py
----------------
Punto de entrada único para la automatización: limpia+analiza el CSV de
INEGI y genera el Reporte_IGAE.docx en un solo comando. Esto es lo que
correría el cron/GitHub Action cada mes.

Uso:
    python run_pipeline.py --csv conjunto_de_datos_igae_igaeAAAA_MM.csv --outdir output
"""

import argparse
from pathlib import Path

from igae_analysis import load_igae, build_period_summary, make_charts
from build_report_word import build_report
import json
import pandas as pd


def main():
    ap = argparse.ArgumentParser(description="Pipeline completo: CSV de INEGI -> Reporte_IGAE.docx")
    ap.add_argument("--csv", required=True, help="Ruta al CSV crudo de INEGI (export del BIE)")
    ap.add_argument("--outdir", default="output", help="Carpeta de salida")
    ap.add_argument("--periodo", default=None, help="Periodo a resumir, formato AAAA-MM (default: el más reciente)")
    ap.add_argument("--con-graficas", action="store_true",
                     help="También genera las gráficas PNG (para la ficha ilustrada); el reporte Word no las usa")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    long_df = load_igae(args.csv)

    periodo = pd.Timestamp(args.periodo + "-01") if args.periodo else None
    summary = build_period_summary(long_df, periodo)

    if args.con_graficas:
        summary["charts"] = make_charts(long_df, summary, outdir / "charts")

    with open(outdir / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    long_df.to_csv(outdir / "igae_clean_long.csv", index=False)

    build_report(summary, str(outdir / "Reporte_IGAE.docx"))

    print(f"\nListo — periodo: {summary['periodo_label']}")
    print(f"  {outdir / 'resumen.json'}")
    print(f"  {outdir / 'Reporte_IGAE.docx'}")


if __name__ == "__main__":
    main()
