"""
build_site.py
--------------
Arma la carpeta `docs/` que publica GitHub Pages:
  docs/index.html, style.css, app.js, vendor/chart.umd.min.js   <- copiados de site_template/
  docs/data/data.json       <- toda la historia (Total, 3 actividades, 20 subsectores) para el dashboard
  docs/data/reportes.json   <- lista de reportes .docx disponibles para descargar
  docs/data/estado.json     <- último periodo y fecha de generación
  docs/reportes/*.docx      <- los reportes (los genera run_pipeline.py)

Es determinista: con los mismos datos produce exactamente los mismos archivos, así que si no hay
datos nuevos git no detecta cambios y no se hace commit.
"""

import json
import re
import shutil
from pathlib import Path

from igae_analysis import export_dashboard_data, json_safe

TEMPLATE_DIR = Path(__file__).parent / "site_template"
REPORTE_RE = re.compile(r"Reporte_IGAE_(\d{4})-(\d{2})\.docx$")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def listar_reportes(docs_dir: Path) -> list:
    """Reportes que existen en docs/reportes/, del más reciente al más antiguo."""
    items = []
    for f in (docs_dir / "reportes").glob("Reporte_IGAE_*.docx"):
        m = REPORTE_RE.search(f.name)
        if not m:
            continue
        anio, mes = int(m.group(1)), int(m.group(2))
        items.append({
            "periodo": f"{anio}-{mes:02d}",
            "label": f"{MESES[mes - 1]} de {anio}",
            "archivo": f"reportes/{f.name}",
            "kb": max(1, round(f.stat().st_size / 1024)),
        })
    items.sort(key=lambda x: x["periodo"], reverse=True)
    return items


def _escribir_json(ruta: Path, obj, compacto=False):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    kw = {"separators": (",", ":")} if compacto else {"indent": 2}
    ruta.write_text(json.dumps(json_safe(obj), ensure_ascii=False, **kw), encoding="utf-8")


def build_site(long_df, docs_dir: Path, estado: dict):
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    for src in TEMPLATE_DIR.rglob("*"):
        if src.is_file():
            dst = docs_dir / src.relative_to(TEMPLATE_DIR)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    (docs_dir / ".nojekyll").write_text("")   # que GitHub Pages sirva los archivos tal cual

    datos = docs_dir / "data"
    _escribir_json(datos / "data.json", export_dashboard_data(long_df), compacto=True)
    _escribir_json(datos / "reportes.json", listar_reportes(docs_dir))
    _escribir_json(datos / "estado.json", estado)
