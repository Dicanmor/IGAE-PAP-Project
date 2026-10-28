"""
calendario.py
--------------
Calendario de publicación del IGAE (INEGI) y lógica de la "ventana de revisión".

INEGI publica sus fechas por adelantado; las guardamos en calendario_igae.json. Solo se consulta
INEGI en la ventana [fecha - 2 días, fecha + 2 días] de la publicación que sigue. Si esa publicación
se retrasa (pasó la ventana y el mes sigue sin aparecer) se sigue revisando en cada corrida del cron
hasta que salga: es justo el caso en que hace falta.
"""

import calendar
import json
from datetime import date, timedelta
from pathlib import Path

RUTA = Path(__file__).parent / "calendario_igae.json"
DIAS_PUBLICACION = 53   # estimación cuando el calendario no trae el mes: fin de mes + 53 días


def sig_mes(ym):
    y, m = ym
    return (y + 1, 1) if m == 12 else (y, m + 1)


def cargar(ruta: Path = RUTA) -> dict:
    """{'antes': 2, 'despues': 2, 'fechas': {(2026, 8): (date(2026,10,23), por_verificar)}}"""
    cfg = {"antes": 2, "despues": 2, "fechas": {}}
    try:
        raw = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    cfg["antes"] = int(raw.get("ventana_antes", 2))
    cfg["despues"] = int(raw.get("ventana_despues", 2))
    for f in raw.get("fechas", []):
        y, m = map(int, f["referencia"].split("-"))
        cfg["fechas"][(y, m)] = (date.fromisoformat(f["publica"]), bool(f.get("por_verificar")))
    return cfg


def fecha_publicacion(cfg: dict, ref):
    """(fecha, es_estimada) de la publicación del mes de referencia `ref` = (anio, mes)."""
    if ref in cfg["fechas"]:
        return cfg["fechas"][ref][0], False
    fin = date(ref[0], ref[1], calendar.monthrange(*ref)[1])
    return fin + timedelta(days=DIAS_PUBLICACION), True


def siguiente(cfg: dict, ultimo):
    """Datos de la próxima publicación, dado el último mes que ya tenemos (anio, mes)."""
    ref = sig_mes(ultimo)
    fecha, estimada = fecha_publicacion(cfg, ref)
    verificar = estimada or cfg["fechas"].get(ref, (None, False))[1]
    return {"referencia": ref, "fecha": fecha, "estimada": estimada, "por_verificar": verificar}


def en_ventana(cfg: dict, ultimo, hoy: date):
    """
    ¿Toca revisar INEGI hoy? Regresa (bool, motivo).
    Sin ningún dato guardado: siempre sí. Con datos: dentro de la ventana de la próxima publicación,
    o si ya se pasó (publicación retrasada).
    """
    if ultimo is None:
        return True, "no hay datos guardados"
    s = siguiente(cfg, ultimo)
    ini = s["fecha"] - timedelta(days=cfg["antes"])
    fin = s["fecha"] + timedelta(days=cfg["despues"])
    if hoy < ini:
        return False, f"la próxima publicación es el {s['fecha']:%d/%m/%Y}; se revisa desde el {ini:%d/%m/%Y}"
    if hoy <= fin:
        return True, f"dentro de la ventana ({ini:%d/%m} a {fin:%d/%m}) de la publicación del {s['fecha']:%d/%m/%Y}"
    return True, f"INEGI debía publicar el {s['fecha']:%d/%m/%Y} y aún no aparece: se sigue revisando"
