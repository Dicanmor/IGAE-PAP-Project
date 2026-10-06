"""
fetch_inegi.py
---------------
Descarga el CSV del IGAE desde los datos abiertos de INEGI y lo deja en
`data/conjunto_de_datos_igae_igaeAAAA_MM.csv` (el mismo archivo que usa el pipeline).

INEGI publica el IGAE en una URL FIJA (el zip "mensual" se reemplaza cada mes), así que no hay que
adivinar rutas por mes: se baja siempre el mismo archivo, se lee de qué periodo es (del propio
contenido del CSV, no del nombre) y solo se guarda si es nuevo.

Pensado para correr TODOS los días de la ventana de publicación (lo hace el cron de GitHub Actions):
casi siempre INEGI sigue con el mes anterior y termina en silencio ("sin cambios").

Qué cuenta como error (el workflow falla y GitHub te avisa por correo):
  - La URL ya no existe (HTTP 404/403, o INEGI responde 200 con una página de error).
  - El archivo descargado no es un CSV del IGAE.
  - No hay conexión y no hay ningún CSV guardado en data/.
Y como aviso (no falla): fallo de red pasajero con datos ya guardados, o que INEGI lleve >60 días
de retraso con el mes que ya debería estar publicado (INEGI publica ~53 días después de cerrar el mes).

Uso:
    python fetch_inegi.py                       # baja a data/
    python fetch_inegi.py --salida data_prueba
    python fetch_inegi.py --url "https://..."   # otra URL (también se lee de la variable IGAE_URL)
"""

import argparse
import calendar
import csv
import io
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

# URL fija de los datos abiertos del IGAE (verificada). INEGI reemplaza el contenido cada mes.
DEFAULT_URL = ("https://www.inegi.org.mx/contenidos/programas/igae/2018/datosabiertos/"
               "conjunto_de_datos_igae_mensual_csv.zip")

DIAS_PUBLICACION = 53   # días naturales entre el cierre del mes y su publicación
DIAS_ALARMA = 60        # más allá de esto sin mes nuevo se avisa (warning)

FILA_TOTAL = "Índice de volumen físico, base 2018=100|Total"
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

CSV_RE = re.compile(r"conjunto_de_datos_igae_igae(\d{4})_(\d{2})\.csv$", re.IGNORECASE)
USER_AGENT = "Mozilla/5.0 (compatible; IGAE-PAP-Project/1.0)"
EN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


class RespuestaInvalida(Exception):
    """El servidor respondió, pero el contenido no es un CSV/zip del IGAE (p. ej. una página de error)."""


# ----------------------------------------------------------------------------
# Validación del contenido
# ----------------------------------------------------------------------------

def es_contenido_igae(inicio: bytes) -> bool:
    """¿Estos primeros bytes parecen el encabezado de un CSV del IGAE? ('Descriptores,1993|Enero,...')"""
    texto = inicio[:4096].decode("utf-8-sig", errors="replace").lstrip()
    primera = texto.splitlines()[0] if texto else ""
    return primera.startswith("Descriptores") and re.search(r"\d{4}\|[^\W\d_]+", primera) is not None


def csv_igae_valido(ruta: Path) -> bool:
    """True si el archivo en disco es un CSV del IGAE (y no una descarga fallida)."""
    try:
        with open(ruta, "rb") as f:
            return es_contenido_igae(f.read(4096))
    except OSError:
        return False


def periodo_desde_csv(data: bytes):
    """
    Último periodo (anio, mes) con dato en la fila 'Índice de volumen físico ... | Total'.
    Se lee del contenido: más confiable que el nombre del archivo, que INEGI puede cambiar.
    Las columnas llevan sufijos como '2026|Julio<P>' y existen columnas futuras vacías y '|Anual'.
    """
    lector = csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace")))
    cabecera = next(lector, None)
    if not cabecera:
        return None
    cols = []
    for i, c in enumerate(cabecera):
        m = re.match(r"^(\d{4})\|([^\W\d_]+)", c.strip())
        if m and m.group(2).lower() in MESES:
            cols.append((i, int(m.group(1)), MESES[m.group(2).lower()]))
    for fila in lector:
        if fila and fila[0].strip() == FILA_TOTAL:
            ultimo = None
            for i, anio, mes in cols:
                if i < len(fila) and fila[i].strip():
                    try:
                        float(fila[i])
                    except ValueError:
                        continue
                    if ultimo is None or (anio, mes) > ultimo:
                        ultimo = (anio, mes)
            return ultimo
    return None


# ----------------------------------------------------------------------------
# Fechas
# ----------------------------------------------------------------------------

def fin_de_mes(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def mes_anterior(ym):
    y, m = ym
    return (y - 1, 12) if m == 1 else (y, m - 1)


def ultimo_mes_esperado(hoy: date):
    """Último mes (y, m) cuya publicación ya debería haber ocurrido."""
    ym = (hoy.year, hoy.month)
    while fin_de_mes(*ym) + timedelta(days=DIAS_PUBLICACION) > hoy:
        ym = mes_anterior(ym)
    return ym


# ----------------------------------------------------------------------------
# Descarga
# ----------------------------------------------------------------------------

def aviso(nivel: str, msg: str):
    """Imprime un mensaje; en GitHub Actions lo vuelve anotación visible (warning/error)."""
    if EN_ACTIONS and nivel in ("warning", "error"):
        print(f"::{nivel}::{msg}")
    else:
        print(f"[{nivel}] {msg}")


def descargar(url: str, intentos: int = 3, espera: float = 3.0):
    """GET con reintentos para errores transitorios. 404/403 NO se reintentan. Regresa (contenido, url_final)."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise
            ultimo = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            ultimo = e
        if i < intentos - 1:
            time.sleep(espera * (i + 1))
    raise ultimo


def extraer_csv(contenido: bytes):
    """
    Del contenido descargado (un .zip de INEGI con conjunto_de_datos/, diccionario_de_datos/, metadatos/;
    o un .csv directo) saca el CSV de datos y su periodo. Valida que de verdad sea del IGAE.
    Regresa (bytes_del_csv, (anio, mes)).
    """
    if contenido[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            csvs = [n for n in z.namelist() if n.lower().endswith(".csv")
                    and not re.search(r"diccionario|metadato|catalogo", n, re.IGNORECASE)]
            if not csvs:
                raise RespuestaInvalida("el .zip no trae ningún CSV de datos. Contenido: "
                                        + ", ".join(z.namelist()[:10]))
            # si hay varios, el de nombre estándar; si no, el primero que sí sea del IGAE
            csvs.sort(key=lambda n: (CSV_RE.search(os.path.basename(n)) is None, n))
            data = None
            for n in csvs:
                cand = z.read(n)
                if es_contenido_igae(cand):
                    data = cand
                    break
            if data is None:
                raise RespuestaInvalida("ningún CSV del .zip tiene formato del IGAE (" + ", ".join(csvs[:5]) + ")")
    else:
        data = contenido
        if not es_contenido_igae(data):
            raise RespuestaInvalida("el contenido no es un CSV del IGAE")
    ym = periodo_desde_csv(data)
    if ym is None:
        raise RespuestaInvalida("no se pudo determinar el periodo más reciente del CSV")
    return data, ym


# ----------------------------------------------------------------------------
# Programa principal
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Descarga el CSV del IGAE (datos abiertos de INEGI)")
    ap.add_argument("--salida", default="data", help="Carpeta donde se guarda el CSV (default: data)")
    ap.add_argument("--url", default=os.environ.get("IGAE_URL") or DEFAULT_URL,
                    help="URL del .zip/.csv de INEGI (también se lee de la variable IGAE_URL)")
    ap.add_argument("--hoy", default=None, help="Fecha simulada AAAA-MM-DD (para pruebas)")
    args = ap.parse_args()

    salida = Path(args.salida)
    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()
    existentes = []
    if salida.exists():
        for f in salida.glob("*.csv"):
            mt = CSV_RE.search(f.name)
            if mt and csv_igae_valido(f):
                existentes.append((int(mt.group(1)), int(mt.group(2))))
            elif mt:
                print(f"[aviso] {f} no es un CSV del IGAE (descarga fallida); se ignora. Puedes borrarlo.")
    tengo = max(existentes) if existentes else None
    print(f"Descargando {args.url}")
    print(f"En {salida}/: {f'{tengo[0]}-{tengo[1]:02d}' if tengo else 'nada'}")

    # --- descarga ---
    try:
        contenido, url_final = descargar(args.url)
    except urllib.error.HTTPError as e:
        aviso("error", f"HTTP {e.code} al descargar {args.url}. La URL ya no existe: copia la nueva desde "
                       "https://www.inegi.org.mx/programas/igae/2018/ (Datos abiertos) y guárdala como "
                       "variable IGAE_URL (ver README).")
        return 1
    except Exception as e:  # red caída, DNS, timeouts persistentes
        if tengo:
            aviso("warning", f"No se pudo conectar con INEGI ({type(e).__name__}: {e}). "
                             "Se usan los datos ya guardados; se reintenta en la siguiente corrida.")
            return 0
        aviso("error", f"No se pudo conectar con INEGI ({type(e).__name__}: {e}) y no hay ningún CSV en {salida}/.")
        return 1

    # --- validar y leer el periodo ---
    try:
        data, ym = extraer_csv(contenido)
    except RespuestaInvalida as e:
        vista = contenido[:120].decode("utf-8", errors="replace").replace("\n", " ").replace("\r", " ")
        aviso("error", f"Lo descargado no es un CSV del IGAE ({e}). INEGI suele responder 200 con una página "
                       f"de error cuando la URL cambió. Primeros caracteres: {vista!r}. "
                       "Revisa la URL (ver README, paso 2).")
        return 1
    except zipfile.BadZipFile:
        aviso("error", "El archivo descargado está dañado (zip inválido). Se reintenta en la siguiente corrida.")
        return 1

    # --- guardar solo si es nuevo ---
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / f"conjunto_de_datos_igae_igae{ym[0]}_{ym[1]:02d}.csv"
    if destino.exists() and destino.read_bytes() == data:
        print(f"Sin cambios: INEGI sigue en {ym[0]}-{ym[1]:02d} (ya lo teníamos).")
    else:
        nuevo = tengo is None or ym > tengo
        destino.write_bytes(data)
        print(f"{'Descargado (periodo nuevo)' if nuevo else 'Actualizado (INEGI revisó cifras)'}: {destino}")

    # --- aviso de retraso de INEGI ---
    esperado = ultimo_mes_esperado(hoy)
    if ym < esperado and hoy > fin_de_mes(*esperado) + timedelta(days=DIAS_ALARMA):
        aviso("warning", f"INEGI aún no publica {esperado[0]}-{esperado[1]:02d} (el archivo llega a "
                         f"{ym[0]}-{ym[1]:02d}) y ya pasaron más de {DIAS_ALARMA} días desde que cerró ese mes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
