# IGAE — reportes y dashboard automáticos

Cada vez que INEGI publica un mes nuevo del IGAE, esto solo:
**descarga el CSV → genera el reporte Word → actualiza el dashboard → lo publica en GitHub Pages.**

```
GitHub Actions (cron diario del 18 al 3)
  └─ fetch_inegi.py      ¿ya salió el mes nuevo? → baja el CSV a data/
  └─ run_pipeline.py     reporte .docx del mes (y de los últimos 24) + dashboard en docs/
  └─ commit de data/ y docs/  →  GitHub Pages publica docs/
```

## Qué hay en el repo
| Archivo | Para qué |
|---|---|
| `fetch_inegi.py` | Descarga el CSV más reciente de los datos abiertos de INEGI. Avisa con **error** si un mes que ya debería existir no aparece (normalmente = cambió la URL). |
| `igae_analysis.py` | Limpia el CSV y calcula todo (niveles, variaciones, contribuciones, subsectores). |
| `build_report_word.py` | Arma el Word con `python-docx`. El texto se calcula con los datos del mes. |
| `build_site.py` + `site_template/` | Dashboard (HTML + Chart.js) y lista de reportes. |
| `run_pipeline.py` | Orquesta todo. Idempotente: sin datos nuevos no cambia ningún archivo. |
| `.github/workflows/igae-mensual.yml` | El cron mensual. |
| `data/` · `docs/` | CSV de INEGI · sitio publicado (reportes en `docs/reportes/`). |

## Puesta en marcha (una sola vez)
1. **Sube todo al repo** (incluye `data/` y `docs/`; así el sitio ya funciona desde el primer momento).
2. **Verifica la URL de descarga de INEGI (30 s).** La que trae `fetch_inegi.py` sigue el patrón de INEGI pero **no pude comprobarla** (mi entorno no llega a inegi.org.mx):
   - Entra a <https://www.inegi.org.mx/programas/igae/2018/> → sección *Datos abiertos* → clic derecho en la descarga CSV → *Copiar dirección de enlace*.
   - Si es distinta, cambia el año/mes por `{anio}` y `{mes:02d}` y guárdala en **Settings → Secrets and variables → Actions → Variables → `IGAE_URL_TEMPLATE`**. Ejemplo: `https://.../igae{anio}_{mes:02d}_csv.zip`
   - Sin tocar código. Si no la verificas, la primera alarma te llega sola (ver abajo).
3. **Pages:** Settings → Pages → *Deploy from a branch* → `main` / carpeta `/docs`.
   - Con cuenta gratuita, Pages solo funciona con repo **público** (en privado pide plan de pago).
4. **Permisos:** Settings → Actions → General → *Workflow permissions* → **Read and write**.
5. **Primera corrida de prueba:** pestaña Actions → *IGAE mensual* → *Run workflow*.

Tu sitio queda en `https://<usuario>.github.io/<repo>/` (pestañas **Dashboard** y **Reportes**).

## Uso local (Windows)
```powershell
py -m pip install -r requirements.txt
py fetch_inegi.py                       # baja el CSV si hay mes nuevo (o copia el CSV a data/ a mano)
py run_pipeline.py                      # genera reportes + sitio en docs/
py -m http.server -d docs 8000          # ver el dashboard en http://localhost:8000
```
Opciones útiles de `run_pipeline.py`: `--meses-atras 36` (más historial), `--regenerar-todo`, `--csv ruta.csv`, `--autor "Nombre"`.

## Qué esperar cada mes
- Días 18–31 y 1–3: el cron revisa. Casi siempre termina en segundos sin hacer nada.
- El día que sale el mes nuevo: baja el CSV, crea `Reporte_IGAE_AAAA-MM.docx`, actualiza el dashboard y hace commit.
- **Si algo falla, GitHub te manda correo** ("Run failed"). El caso típico: pasaron >60 días de un mes y no se encontró → cambió la URL.
- Subir un CSV a `data/` a mano también dispara todo.

## Notas importantes
- **Reportes antiguos:** se generan con los datos vigentes cuando se crean; INEGI revisa cifras recientes, así que un reporte viejo no se reescribe solo (usa `--regenerar-todo` si quieres actualizarlos).
- **API del BIE:** no se usó a propósito. El CSV de datos abiertos trae las 120 series en un archivo; la API pide una consulta + un ID por serie (120) y un token personal. Si el profe exige API, se agrega como otra fuente en `fetch_inegi.py` (cada persona necesita su token).
- **Dashboard:** los datos viajan en `docs/data/data.json` (~360 KB); el navegador calcula cualquier mes sin servidor.

## Problemas comunes
- `python no se reconoce` → usa `py` (o instala Python marcando *Add to PATH*).
- `No module named 'docx'` → `py -m pip install python-docx` (no `docx`).
- El dashboard en blanco al abrir `index.html` con doble clic → los navegadores bloquean la lectura local; usa `py -m http.server -d docs 8000`.
