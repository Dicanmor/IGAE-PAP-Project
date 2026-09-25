"""
igae_analysis.py
-----------------
Limpieza + análisis del CSV crudo de INEGI (IGAE, banco BIE) y generación de:
  1. Un dataset tidy (long format) con todas las métricas/sectores/subsectores.
  2. Un resumen (JSON) con los números que necesita la ficha ejecutiva.
  3. Las gráficas (PNG) que acompañan la ficha.

Pensado para correr cada mes sin tocarse: solo cambia el CSV de entrada
(el nombre de archivo de INEGI ya incluye el periodo, p.ej.
`conjunto_de_datos_igae_igae2026_06.csv`) y el script detecta solo el
periodo más reciente con datos.

Uso:
    python igae_analysis.py --csv ruta/al/csv.csv --outdir output/

Requiere: pandas, matplotlib
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# Constantes

MONTH_MAP = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
    "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
}
MONTH_NAME_ES = {v: k.lower() for k, v in MONTH_MAP.items()}  # lowercase: se usan a media frase ("en junio de...")

METRIC_VALOR = "Índice de volumen físico, base 2018=100"
METRIC_VAR_ANUAL = "Variación porcentual anual"
METRIC_CONTRIB = "Contribución a la variación total"
METRIC_VALOR_ACUM = "Índice de volumen físico acumulado base 2018=100"
METRIC_VAR_ANUAL_ACUM = "Variación porcentual anual de los índices acumulados"

SECTORES_PRINCIPALES = ["Actividades primarias", "Actividades secundarias", "Actividades terciarias"]

SET2 = ["#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854", "#FFD92F"]
SECTOR_COLORS = {
    "Actividades primarias": "#E41A1C",
    "Actividades secundarias": "#4DAF4A",
    "Actividades terciarias": "#377EB8",
}

plt.rcParams.update({
    "font.size": 10,
    "axes.facecolor": "#EBEBEB",
    "axes.edgecolor": "white",
    "axes.grid": True,
    "grid.color": "white",
    "grid.linewidth": 1,
    "axes.axisbelow": True,
    "figure.facecolor": "white",
})


# Limpieza: CSV crudo (ancho, formato INEGI) -> long format tidy

def load_igae(csv_path: str) -> pd.DataFrame:
    """
    Convierte el export crudo de INEGI (una fila por métrica+sector[+subsector],
    una columna por periodo "AAAA|Mes") a un dataframe long format con columnas:
        metric, sector, subsector, periodo (datetime), valor (float)

    Descarta las columnas "Anual" (promedio del año, no es un periodo mensual)
    y limpia los sufijos de "preliminar"/"revisado" (<P>, <R>) que INEGI agrega
    a los meses más recientes.
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    parts = df["Descriptores"].str.split("|", expand=True)
    parts.columns = ["metric", "sector", "subsector"][: parts.shape[1]]
    wide = pd.concat([parts, df.drop(columns="Descriptores")], axis=1)

    period_cols = [c for c in df.columns if c != "Descriptores"]
    long = wide.melt(
        id_vars=[c for c in ["metric", "sector", "subsector"] if c in wide.columns],
        value_vars=period_cols,
        var_name="periodo_raw",
        value_name="valor",
    )

    anio_mes = long["periodo_raw"].str.split("|", expand=True)
    long["anio"] = anio_mes[0]
    mes_clean = anio_mes[1].str.replace(r"<[A-Za-z]>", "", regex=True)
    long = long[mes_clean != "Anual"].copy()
    long["mes"] = mes_clean.loc[long.index].map(MONTH_MAP)
    long["anio"] = long["anio"].astype(int)
    long["periodo"] = pd.to_datetime(dict(year=long["anio"], month=long["mes"], day=1))
    long["valor"] = pd.to_numeric(long["valor"], errors="coerce")

    long = long.dropna(subset=["valor"]).drop(columns=["periodo_raw", "anio", "mes"])
    return long.reset_index(drop=True)


def latest_period(long_df: pd.DataFrame) -> pd.Timestamp:
    """Periodo más reciente con dato de nivel de índice disponible (Total)."""
    mask = (long_df["metric"] == METRIC_VALOR) & (long_df["sector"] == "Total") & long_df["subsector"].isna()
    return long_df.loc[mask, "periodo"].max()


# Resumen ejecutivo

def _short_name(nombre: str, max_len: int = 32) -> str:
    """Nombre corto para etiquetas de ejes (el nombre completo se conserva en el JSON/tablas)."""
    if len(nombre) <= max_len:
        return nombre
    return nombre[: max_len - 1].rstrip() + "…"


def _get(long_df, metric, sector=None, subsector="__any__", periodo=None):
    """Helper de filtrado. subsector='__any__' significa 'no filtrar por subsector'."""
    m = long_df["metric"] == metric
    if sector is not None:
        m &= long_df["sector"] == sector
    if subsector != "__any__":
        if subsector is None:
            m &= long_df["subsector"].isna()
        else:
            m &= long_df["subsector"] == subsector
    if periodo is not None:
        m &= long_df["periodo"] == periodo
    return long_df.loc[m]


def build_period_summary(long_df: pd.DataFrame, periodo: pd.Timestamp = None) -> dict:
    """
    Arma el diccionario de resumen para el periodo dado (por default, el más
    reciente disponible). Este dict es justo lo que consume build_ficha.js.
    """
    if periodo is None:
        periodo = latest_period(long_df)
    prev_periodo = periodo - pd.DateOffset(months=1)
    periodo_anyo_anterior = periodo - pd.DateOffset(years=1)

    # --- A. Resultado general (Total) ---
    total_now = _get(long_df, METRIC_VALOR, "Total", None, periodo)["valor"].iloc[0]
    total_prev = _get(long_df, METRIC_VALOR, "Total", None, prev_periodo)
    total_prev = total_prev["valor"].iloc[0] if len(total_prev) else None
    total_anyo_anterior = _get(long_df, METRIC_VALOR, "Total", None, periodo_anyo_anterior)
    total_anyo_anterior = total_anyo_anterior["valor"].iloc[0] if len(total_anyo_anterior) else None
    var_mensual = (total_now / total_prev - 1) if total_prev else None
    var_anual = _get(long_df, METRIC_VAR_ANUAL, "Total", None, periodo)["valor"].iloc[0] / 100
    var_acum = _get(long_df, METRIC_VAR_ANUAL_ACUM, "Total", None, periodo)["valor"].iloc[0] / 100

    total_serie = _get(long_df, METRIC_VALOR, "Total", None).sort_values("periodo")
    max_row = total_serie.loc[total_serie["valor"].idxmax()]
    es_maximo_historico = bool(max_row["periodo"] == periodo)

    # --- B. Grandes actividades (Primarias/Secundarias/Terciarias) ---
    sectores = []
    for s in SECTORES_PRINCIPALES:
        nivel = _get(long_df, METRIC_VALOR, s, None, periodo)["valor"].iloc[0]
        nivel_anyo_ant = _get(long_df, METRIC_VALOR, s, None, periodo_anyo_anterior)
        nivel_anyo_ant = nivel_anyo_ant["valor"].iloc[0] if len(nivel_anyo_ant) else None
        va = _get(long_df, METRIC_VAR_ANUAL, s, None, periodo)["valor"].iloc[0] / 100
        vacum = _get(long_df, METRIC_VAR_ANUAL_ACUM, s, None, periodo)["valor"].iloc[0] / 100
        contrib = _get(long_df, METRIC_CONTRIB, s, None, periodo)["valor"].iloc[0]
        sectores.append({"sector": s, "nivel": nivel, "nivel_anyo_anterior": nivel_anyo_ant,
                          "variacion_anual": va, "variacion_acumulada": vacum, "contribucion_pp": contrib})
    sectores.sort(key=lambda r: r["variacion_anual"], reverse=True)

    # --- C. Detalle por subsector ---
    sub_va = _get(long_df, METRIC_VAR_ANUAL, None, "__any__", periodo)
    sub_va = sub_va[sub_va["subsector"].notna()].copy()
    sub_va["nombre"] = sub_va["subsector"].str.split("---").str[1]
    sub_va = sub_va.rename(columns={"valor": "variacion_anual_pct"})[["sector", "subsector", "nombre", "variacion_anual_pct"]]

    sub_contrib = _get(long_df, METRIC_CONTRIB, None, "__any__", periodo)
    sub_contrib = sub_contrib[sub_contrib["subsector"].notna()].copy()
    sub_contrib = sub_contrib.rename(columns={"valor": "contribucion_pp"})[["subsector", "contribucion_pp"]]

    sub_nivel_now = _get(long_df, METRIC_VALOR, None, "__any__", periodo)
    sub_nivel_now = sub_nivel_now[sub_nivel_now["subsector"].notna()].rename(columns={"valor": "nivel_actual"})[["subsector", "nivel_actual"]]

    sub_nivel_prev = _get(long_df, METRIC_VALOR, None, "__any__", periodo_anyo_anterior)
    sub_nivel_prev = sub_nivel_prev[sub_nivel_prev["subsector"].notna()].rename(columns={"valor": "nivel_anyo_anterior"})[["subsector", "nivel_anyo_anterior"]]

    sub = (sub_va.merge(sub_contrib, on="subsector", how="left")
                 .merge(sub_nivel_now, on="subsector", how="left")
                 .merge(sub_nivel_prev, on="subsector", how="left")
                 .sort_values("variacion_anual_pct", ascending=False))

    top_crecen = sub.head(5).to_dict("records")
    top_caen = sub.tail(5).sort_values("variacion_anual_pct").to_dict("records")
    top_contrib = sub.sort_values("contribucion_pp", ascending=False).head(5).to_dict("records")
    min_contrib = sub.sort_values("contribucion_pp", ascending=True).head(3).to_dict("records")

    mes_es = MONTH_NAME_ES[periodo.month]
    prev_mes_es = MONTH_NAME_ES[prev_periodo.month] if total_prev else None
    anyo_anterior_label = f"{mes_es} de {periodo_anyo_anterior.year}" if total_anyo_anterior is not None else None

    def _sub_record(r):
        d = {"sector": r["sector"], "nombre": r["nombre"], "variacion_anual_pct": round(r["variacion_anual_pct"], 1)}
        if pd.notna(r.get("nivel_actual")):
            d["nivel_actual"] = round(r["nivel_actual"], 1)
        if pd.notna(r.get("nivel_anyo_anterior")):
            d["nivel_anyo_anterior"] = round(r["nivel_anyo_anterior"], 1)
        return d

    # --- Tendencia reciente (reemplaza las gráficas por tablas de los
    #     últimos N meses: nivel del Total y de cada gran actividad) ---
    tendencia = build_recent_trend(long_df, periodo, n_meses=12)

    return {
        "periodo": periodo.strftime("%Y-%m-%d"),
        "periodo_label": f"{mes_es} de {periodo.year}",
        "prev_periodo_label": f"{prev_mes_es} de {prev_periodo.year}" if prev_mes_es else None,
        "anyo_anterior_label": anyo_anterior_label,
        "total": {
            "nivel": round(float(total_now), 1),
            "nivel_prev": round(float(total_prev), 1) if total_prev else None,
            "nivel_anyo_anterior": round(float(total_anyo_anterior), 1) if total_anyo_anterior is not None else None,
            "variacion_mensual_pct": round(float(var_mensual) * 100, 1) if var_mensual is not None else None,
            "variacion_anual_pct": round(float(var_anual) * 100, 1),
            "variacion_acumulada_pct": round(float(var_acum) * 100, 1),
            "es_maximo_historico": es_maximo_historico,
            "maximo_historico_valor": round(float(max_row["valor"]), 1),
            "maximo_historico_periodo": max_row["periodo"].strftime("%Y-%m"),
        },
        "sectores": [
            {**s, "nivel": round(s["nivel"], 1),
             "nivel_anyo_anterior": round(s["nivel_anyo_anterior"], 1) if s["nivel_anyo_anterior"] is not None else None,
             "variacion_anual": round(s["variacion_anual"] * 100, 1),
             "variacion_acumulada": round(s["variacion_acumulada"] * 100, 1), "contribucion_pp": round(s["contribucion_pp"], 2)}
            for s in sectores
        ],
        "subsectores": {
            "top_crecen": [_sub_record(r) for r in top_crecen],
            "top_caen": [_sub_record(r) for r in top_caen],
            "top_contribuyen": [{"nombre": r["nombre"], "contribucion_pp": round(r["contribucion_pp"], 2)} for r in top_contrib],
            "menor_contribuyen": [{"nombre": r["nombre"], "contribucion_pp": round(r["contribucion_pp"], 2)} for r in min_contrib],
        },
        "tendencia": tendencia,
    }


def build_recent_trend(long_df: pd.DataFrame, periodo: pd.Timestamp, n_meses: int = 12) -> dict:
    """
    Serie de los últimos `n_meses` (Total + las 3 grandes actividades), para
    tablas de tendencia que reemplazan las gráficas de líneas del reporte.
    """
    periodos = pd.date_range(end=periodo, periods=n_meses, freq="MS")

    total = _get(long_df, METRIC_VALOR, "Total", None).set_index("periodo")["valor"]
    va_total = _get(long_df, METRIC_VAR_ANUAL, "Total", None).set_index("periodo")["valor"]

    total_rows = []
    for p in periodos:
        if p not in total.index:
            continue
        mes_abbr = MONTH_NAME_ES[p.month][:3]
        total_rows.append({
            "periodo_label": f"{mes_abbr}-{str(p.year)[2:]}",
            "nivel": round(float(total.loc[p]), 1),
            "variacion_anual_pct": round(float(va_total.loc[p]), 1) if p in va_total.index else None,
        })

    sector_series = {}
    for s in SECTORES_PRINCIPALES:
        sector_series[s] = _get(long_df, METRIC_VALOR, s, None).set_index("periodo")["valor"]

    sector_rows = []
    for p in periodos:
        if p not in total.index:
            continue
        mes_abbr = MONTH_NAME_ES[p.month][:3]
        row = {"periodo_label": f"{mes_abbr}-{str(p.year)[2:]}"}
        for s in SECTORES_PRINCIPALES:
            ser = sector_series[s]
            row[s] = round(float(ser.loc[p]), 1) if p in ser.index else None
        sector_rows.append(row)

    return {"total_ultimos_meses": total_rows, "sectores_ultimos_meses": sector_rows}



# Gráficas

def make_charts(long_df: pd.DataFrame, summary: dict, outdir: Path):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    total = _get(long_df, METRIC_VALOR, "Total", None).sort_values("periodo")

    # Histórico del Total
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    ax.plot(total["periodo"], total["valor"], color="darkblue", linewidth=1)
    ax.set_xlabel("Periodo")
    ax.set_ylabel("Índice (2018=100)")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(outdir / "1_historico_total.png")
    plt.close(fig)

    # Barras: nivel por gran actividad (periodo actual)
    sect_df = pd.DataFrame(summary["sectores"]).sort_values("nivel")
    fig, ax = plt.subplots(figsize=(7.0, 2.8), dpi=150)
    colors = [SET2[i % len(SET2)] for i in range(len(sect_df))]
    bars = ax.barh(sect_df["sector"], sect_df["nivel"], color=colors)
    for bar, val in zip(bars, sect_df["nivel"]):
        ax.text(val + 1.2, bar.get_y() + bar.get_height() / 2, f"{val:.1f}", va="center", fontsize=9)
    ax.set_xlabel("Índice")
    ax.set_xlim(0, sect_df["nivel"].max() * 1.15)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(outdir / "2_barras_actividades.png")
    plt.close(fig)

    # 3. Líneas combinadas: primarias/secundarias/terciarias
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    for s in SECTORES_PRINCIPALES:
        d = _get(long_df, METRIC_VALOR, s, None).sort_values("periodo")
        ax.plot(d["periodo"], d["valor"], label=s, color=SECTOR_COLORS[s], linewidth=1)
    ax.set_xlabel("Periodo")
    ax.set_ylabel("Índice")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(outdir / "3_lineas_sectores.png")
    plt.close(fig)

    # 4. Ranking de subsectores: variación anual (barh, top crecen / top caen)
    top = summary["subsectores"]["top_crecen"] + summary["subsectores"]["top_caen"][::-1]
    names = [_short_name(r["nombre"]) for r in top]
    vals = [r["variacion_anual_pct"] for r in top]
    colors = ["#4DAF4A" if v >= 0 else "#E41A1C" for v in vals]
    fig, ax = plt.subplots(figsize=(8.4, 4.4), dpi=150)
    bars = ax.barh(names, vals, color=colors)
    xmin, xmax = min(vals + [0]), max(vals + [0])
    pad = (xmax - xmin) * 0.15 or 1
    for bar, val in zip(bars, vals):
        offset = pad * 0.15 if val >= 0 else -pad * 0.15
        ha = "left" if val >= 0 else "right"
        ax.text(val + offset, bar.get_y() + bar.get_height() / 2, f"{val:+.1f}%", va="center", ha=ha, fontsize=8)
    ax.axvline(0, color="#888888", linewidth=0.8)
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_xlabel("Variación % anual")
    ax.tick_params(axis="y", labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(left=0.42, right=0.97, top=0.96, bottom=0.12)
    fig.savefig(outdir / "4_ranking_subsectores.png")
    plt.close(fig)

    # 5. Contribución a la variación total (subsectores top)
    top_c = summary["subsectores"]["top_contribuyen"]
    fig, ax = plt.subplots(figsize=(8.0, 2.9), dpi=150)
    names = [_short_name(r["nombre"]) for r in top_c][::-1]
    vals = [r["contribucion_pp"] for r in top_c][::-1]
    bars = ax.barh(names, vals, color="#377EB8")
    for bar, val in zip(bars, vals):
        ax.text(val + max(vals) * 0.02, bar.get_y() + bar.get_height() / 2, f"{val:.2f} pp", va="center", fontsize=8)
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_xlabel("Contribución (puntos porcentuales)")
    ax.tick_params(axis="y", labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(left=0.4, right=0.97, top=0.95, bottom=0.18)
    fig.savefig(outdir / "5_contribucion_subsectores.png")
    plt.close(fig)

    return {
        "historico_total": str(outdir / "1_historico_total.png"),
        "barras_actividades": str(outdir / "2_barras_actividades.png"),
        "lineas_sectores": str(outdir / "3_lineas_sectores.png"),
        "ranking_subsectores": str(outdir / "4_ranking_subsectores.png"),
        "contribucion_subsectores": str(outdir / "5_contribucion_subsectores.png"),
    }


# CLI

def main():
    ap = argparse.ArgumentParser(description="Limpieza + análisis del IGAE (INEGI)")
    ap.add_argument("--csv", required=True, help="Ruta al CSV crudo de INEGI (export del BIE)")
    ap.add_argument("--outdir", default="output", help="Carpeta de salida (gráficas + resumen.json)")
    ap.add_argument("--periodo", default=None, help="Periodo a resumir, formato AAAA-MM (default: el más reciente)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    long_df = load_igae(args.csv)

    periodo = pd.Timestamp(args.periodo + "-01") if args.periodo else None
    summary = build_period_summary(long_df, periodo)
    chart_paths = make_charts(long_df, summary, outdir / "charts")
    summary["charts"] = chart_paths

    with open(outdir / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # también dejamos el tidy dataset guardado, útil para otros análisis / auditoría
    long_df.to_csv(outdir / "igae_clean_long.csv", index=False)

    print(f"Listo. Periodo analizado: {summary['periodo_label']}")
    print(f"Resumen: {outdir / 'resumen.json'}")
    print(f"Gráficas: {outdir / 'charts'}")


if __name__ == "__main__":
    main()
