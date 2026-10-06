"""
run_pipeline.py
----------------
Punto de entrada de la automatización. En un solo comando:
  1. toma el CSV más reciente de data/ (o el que le pases con --csv),
  2. genera el reporte Word de los últimos N meses (solo los que no existen todavía),
  3. reconstruye el sitio (dashboard + lista de reportes) en docs/.

Es idempotente: si no hay datos nuevos no cambia nada (git no verá diferencias).

Uso:
    python fetch_inegi.py --salida data                 # baja el CSV si ya salió el mes nuevo
    python run_pipeline.py                              # reportes + sitio
    python run_pipeline.py --meses-atras 36             # más historial de reportes
    python run_pipeline.py --regenerar-todo             # reescribe también los que ya existen
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from igae_analysis import MONTH_NAME_ES, build_period_summary, json_safe, latest_period, load_igae, METRIC_VALOR
from build_report_word import AUTOR, build_report
from build_site import build_site
from fetch_inegi import csv_igae_valido

CSV_RE = re.compile(r"conjunto_de_datos_igae_igae(\d{4})_(\d{2})\.csv$", re.IGNORECASE)


def csvs_en(data_dir: Path):
    """[(AAAA, MM), Path] de los CSV del IGAE en data/, del más viejo al más nuevo."""
    out = []
    for f in data_dir.glob("*.csv"):
        m = CSV_RE.search(f.name)
        if not m:
            continue
        if not csv_igae_valido(f):
            print(f"[aviso] {f} no es un CSV del IGAE (descarga fallida); se ignora. Puedes borrarlo.")
            continue
        out.append(((int(m.group(1)), int(m.group(2))), f))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="CSV de INEGI -> reportes Word + sitio (dashboard)")
    ap.add_argument("--csv", default=None, help="CSV a usar (default: el más reciente de --data-dir)")
    ap.add_argument("--data-dir", default="data", help="Carpeta con los CSV de INEGI")
    ap.add_argument("--docs-dir", default="docs", help="Carpeta del sitio (GitHub Pages)")
    ap.add_argument("--meses-atras", type=int, default=24, help="Cuántos meses de reportes mantener (default: 24)")
    ap.add_argument("--forzar", action="store_true", help="Regenera el reporte del último mes aunque ya exista")
    ap.add_argument("--regenerar-todo", action="store_true", help="Regenera todos los reportes del rango")
    ap.add_argument("--conservar-csv", type=int, default=3,
                    help="Cuántos CSV recientes conservar en data/ (borra los más viejos; 0 = no borrar nada)")
    ap.add_argument("--autor", default=AUTOR, help="Nombre que aparece en la portada de los reportes")
    args = ap.parse_args()

    data_dir, docs_dir = Path(args.data_dir), Path(args.docs_dir)
    disponibles = csvs_en(data_dir) if data_dir.exists() else []
    if args.csv:
        csv = Path(args.csv)
    elif disponibles:
        csv = disponibles[-1][1]
    else:
        print(f"ERROR: no hay CSV en {data_dir}/. Corre fetch_inegi.py o pasa --csv.", file=sys.stderr)
        return 2
    if not csv.exists():
        print(f"ERROR: no existe {csv}", file=sys.stderr)
        return 2
    if not csv_igae_valido(csv):
        print(f"ERROR: {csv} no parece un CSV del IGAE (¿descarga fallida o página de error?). "
              "Bórralo y vuelve a correr fetch_inegi.py.", file=sys.stderr)
        return 2

    print(f"CSV: {csv}")
    long_df = load_igae(str(csv))
    latest = latest_period(long_df)
    latest_ym = latest.strftime("%Y-%m")

    mask_tot = (long_df["metric"] == METRIC_VALOR) & (long_df["sector"] == "Total") & long_df["subsector"].isna()
    primer = long_df.loc[mask_tot, "periodo"].min()

    estado_path = docs_dir / "data" / "estado.json"
    previo = json.loads(estado_path.read_text(encoding="utf-8")) if estado_path.exists() else {}

    rep_dir = docs_dir / "reportes"
    ruta = lambda p: rep_dir / f"Reporte_IGAE_{p.strftime('%Y-%m')}.docx"

    # meses objetivo (necesitan 12 meses de historia para tener variación anual)
    meses = [latest - pd.DateOffset(months=k) for k in range(args.meses_atras)]
    meses = [p for p in meses if p >= primer + pd.DateOffset(months=12)]

    pendientes = [p for p in meses
                  if args.regenerar_todo or not ruta(p).exists() or (p == latest and args.forzar)]

    generados = []
    for p in sorted(pendientes):
        try:
            summary = json_safe(build_period_summary(long_df, p))
            build_report(summary, str(ruta(p)), autor=args.autor)
            generados.append(p.strftime("%Y-%m"))
        except Exception as e:
            if p == latest:
                raise
            print(f"[aviso] no se pudo generar {p.strftime('%Y-%m')}: {type(e).__name__}: {e}")

    estado = {
        "ultimo_periodo": latest_ym,
        "ultimo_periodo_label": f"{MONTH_NAME_ES[latest.month]} de {latest.year}",
        "fuente_csv": csv.name,
        # la fecha solo cambia cuando hubo algo nuevo; así una corrida sin novedades no ensucia git
        "generado_en": (datetime.now(timezone.utc).isoformat(timespec="seconds")
                        if generados or not previo.get("generado_en") else previo["generado_en"]),
    }
    build_site(long_df, docs_dir, estado)

    # limpieza de CSV viejos (solo si el CSV vino de data/)
    if not args.csv and args.conservar_csv > 0:
        for _, f in disponibles[:-args.conservar_csv]:
            f.unlink()
            print(f"Borrado CSV viejo: {f.name}")

    if generados:
        print(f"\nReportes generados ({len(generados)}): {', '.join(generados)}")
    else:
        print("\nSin reportes nuevos (todo estaba al día).")
    print(f"Último periodo: {estado['ultimo_periodo_label']}  |  sitio en {docs_dir}/")

    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as fh:
            fh.write(f"periodo={latest_ym}\ngenerados={len(generados)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
