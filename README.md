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
| `fetch_inegi.py` | Baja el zip de datos abiertos de INEGI (URL fija), lee de qué periodo es y lo guarda en `data/` solo si es nuevo. Falla con **error** si la URL cambió. |
| `igae_analysis.py` | Limpia el CSV y calcula todo (niveles, variaciones, contribuciones, subsectores). |
| `build_report_word.py` | Arma el Word con `python-docx`. El texto se calcula con los datos del mes. |
| `build_site.py` + `site_template/` | Dashboard (HTML + Chart.js) y lista de reportes. |
| `run_pipeline.py` | Orquesta todo. Idempotente: sin datos nuevos no cambia ningún archivo. |
| `.github/workflows/igae-mensual.yml` | El cron mensual. |
| `data/` · `docs/` | CSV de INEGI · sitio publicado (reportes en `docs/reportes/`). |

## Puesta en marcha (una sola vez)
1. **Sube todo al repo** (incluye `data/` y `docs/`; así el sitio ya funciona desde el primer momento).
2. **Prueba la descarga** (la URL de INEGI ya viene configurada en `fetch_inegi.py`; es una URL fija que INEGI reemplaza cada mes):
   ```powershell
   py fetch_inegi.py --salida data_prueba
   ```
   Si algún día INEGI cambia la URL, el workflow falla con un error claro (y te llega correo). Entonces copia la nueva desde <https://www.inegi.org.mx/programas/igae/2018/> (*Datos abiertos* → clic derecho en la descarga CSV → *Copiar dirección de enlace*) y guárdala en **Settings → Secrets and variables → Actions → Variables → `IGAE_URL`**. Sin tocar código.
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
- **Si algo falla, GitHub te manda correo** ("Run failed"). El caso típico: INEGI cambió la URL y lo descargado ya no es un CSV del IGAE.
- Si INEGI se retrasa >60 días con un mes, sale un *warning* (no falla).
- Subir un CSV a `data/` a mano también dispara todo.

## Notas importantes
- **Reportes antiguos:** se generan con los datos vigentes cuando se crean; INEGI revisa cifras recientes, así que un reporte viejo no se reescribe solo (usa `--regenerar-todo` si quieres actualizarlos).
- **API del BIE:** no se usó a propósito. El CSV de datos abiertos trae las 120 series en un archivo; la API pide una consulta + un ID por serie (120) y un token personal. Si el profe exige API, se agrega como otra fuente en `fetch_inegi.py` (cada persona necesita su token).
- **Dashboard:** los datos viajan en `docs/data/data.json` (~360 KB); el navegador calcula cualquier mes sin servidor.

## Problemas comunes
- `fetch_inegi.py` dice **"Lo descargado no es un CSV del IGAE"** → INEGI no responde 404 cuando una URL no existe, responde 200 con una página de error. Significa que la URL cambió: actualízala (paso 2). Imprime los primeros caracteres de lo recibido para diagnosticar y no guarda nada basura.
- Si tienes un CSV roto en `data/` (descarga fallida), `run_pipeline.py` y `fetch_inegi.py` lo **ignoran y avisan**; puedes borrarlo.
- `python no se reconoce` → usa `py` (o instala Python marcando *Add to PATH*).
- `No module named 'docx'` → `py -m pip install python-docx` (no `docx`).
- El dashboard en blanco al abrir `index.html` con doble clic → los navegadores bloquean la lectura local; usa `py -m http.server -d docs 8000`.


## Calendario de INEGI, próxima actualización y avisos por correo

- **Ventana de revisión:** `calendario_igae.json` trae las fechas de publicación del IGAE (de INEGI). El cron solo
  consulta INEGI de **2 días antes a 2 días después** de la fecha publicada (cambia `ventana_antes` / `ventana_despues`
  si quieres otra). Si INEGI se retrasa, se sigue revisando en cada corrida del 19 al 28 hasta que salga el mes.
  Cuando INEGI publique su calendario del año siguiente, agrega las fechas en ese archivo (las de 2027 están marcadas
  `por_verificar`: confírmalas en https://www.inegi.org.mx/contenidos/saladeprensa/doc/cal_2027.pdf).
  Si falta un mes, se estima fin de mes + 53 días.
- **Popup de próxima actualización:** la página lo muestra una vez por fecha y queda un botón en el encabezado.
- **Avisos por correo:** ver `apps_script/README.md` (10 minutos, gratis). Sin configurarlo, la página funciona igual
  pero sin el formulario de correo. Para probar: Actions → Run workflow → "Enviar correo de prueba".
