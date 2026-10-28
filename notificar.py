"""
notificar.py
-------------
Avisa por correo a los suscriptores que ya hay datos nuevos del IGAE, con el reporte Word adjunto.
Lo corre GitHub Actions después de publicar el sitio, solo cuando llegó un mes nuevo.

El envío lo hace el Google Apps Script de apps_script/ (ver su README). Este programa solo le manda
el resumen y el .docx. Necesita:
  - config.json -> "suscripcion_url"  (URL /exec de la aplicación web)
  - variable de entorno NOTIFY_TOKEN  (secret de GitHub; la misma que en Apps Script)
Si falta alguno, no hace nada y termina bien (el sitio ya quedó publicado).

Uso:
    python notificar.py                    # avisa del periodo más reciente
    python notificar.py --prueba           # manda el correo solo al dueño del script
    python notificar.py --forzar           # reenvía aunque ya se hubiera avisado de ese periodo
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

import calendario
from igae_analysis import MONTH_NAME_ES, build_period_summary, json_safe, latest_period, load_igae

RAIZ = Path(__file__).parent


def aviso(nivel, msg):
    if os.environ.get("GITHUB_ACTIONS") == "true" and nivel in ("warning", "error"):
        print(f"::{nivel}::{msg}")
    else:
        print(f"[{nivel}] {msg}")


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MONTH_NAME_ES[d.month]} de {d.year}"


def sitio_url(cfg: dict) -> str:
    if cfg.get("sitio_url"):
        return cfg["sitio_url"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")      # owner/repo
    if "/" in repo:
        owner, nombre = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{nombre}/"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Avisa a los suscriptores que hay datos nuevos del IGAE")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--docs-dir", default="docs")
    ap.add_argument("--prueba", action="store_true", help="Manda el correo solo al dueño del script")
    ap.add_argument("--forzar", action="store_true", help="Reenvía aunque ya se hubiera avisado de ese periodo")
    args = ap.parse_args()

    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8")) if (RAIZ / "config.json").exists() else {}
    url = (cfg.get("suscripcion_url") or "").strip()
    token = os.environ.get("NOTIFY_TOKEN", "").strip()
    if not url or not token:
        print("Avisos por correo no configurados (falta suscripcion_url en config.json o el secret NOTIFY_TOKEN). "
              "Se omite el envío.")
        return 0

    from run_pipeline import csvs_en   # reutiliza la búsqueda del CSV más reciente
    disponibles = csvs_en(Path(args.data_dir))
    if not disponibles:
        aviso("warning", "No hay CSV en data/: no se puede armar el aviso.")
        return 0
    long_df = load_igae(str(disponibles[-1][1]))
    latest = latest_period(long_df)
    ym = latest.strftime("%Y-%m")
    s = json_safe(build_period_summary(long_df, latest))
    t = s["total"]

    docx = Path(args.docs_dir) / "reportes" / f"Reporte_IGAE_{ym}.docx"
    if not docx.exists():
        aviso("warning", f"No existe {docx}: el aviso saldría sin reporte adjunto. Se omite.")
        return 0

    sig = calendario.siguiente(calendario.cargar(), (latest.year, latest.month))
    proxima = fecha_larga(sig["fecha"]) + (" (fecha estimada)" if sig["estimada"] else "")

    payload = {
        "token": token,
        "accion": "prueba" if args.prueba else "notificar",
        "forzar": args.forzar,
        "periodo": ym,
        "label": s["periodo_label"],
        "archivo": docx.name,
        "docx_b64": base64.b64encode(docx.read_bytes()).decode("ascii"),
        "sitio_url": sitio_url(cfg),
        "proxima_texto": proxima,
        "resumen": {
            "nivel": t["nivel"],
            "var_mensual": t["variacion_mensual_pct"],
            "var_anual": t["variacion_anual_pct"],
            "var_acum": t["variacion_acumulada_pct"],
            "actividades": [{"nombre": a["sector"], "var_anual": a["variacion_anual"],
                             "contrib": a["contribucion_pp"]} for a in s["sectores"]],
        },
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    try:
        # Apps Script contesta con una redirección; urllib la sigue y entrega la respuesta JSON.
        with urllib.request.urlopen(req, timeout=120) as r:
            cuerpo = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        aviso("warning", f"No se pudo contactar el servicio de avisos ({type(e).__name__}: {e}). "
                         "El sitio sí se publicó; reintenta con Run workflow → 'Enviar aviso'.")
        return 0
    try:
        resp = json.loads(cuerpo)
    except ValueError:
        aviso("warning", f"Respuesta inesperada del servicio de avisos: {cuerpo[:200]!r}. "
                         "Revisa que la implementación sea 'Cualquier persona' y la URL termine en /exec.")
        return 0
    if not resp.get("ok"):
        aviso("warning", f"El servicio de avisos rechazó el envío: {resp.get('error')}. Revisa NOTIFY_TOKEN.")
        return 0
    if resp.get("omitido"):
        print(f"Sin envío: {resp['omitido']}.")
    else:
        print(f"Avisos enviados: {resp.get('enviados')} de {resp.get('destinatarios')} "
              f"(fallidos: {resp.get('fallidos')}, sin cuota: {resp.get('sin_cuota')}).")
        if resp.get("fallidos") or resp.get("sin_cuota"):
            aviso("warning", "Algunos correos no salieron; se reintentará en la siguiente corrida con --forzar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
