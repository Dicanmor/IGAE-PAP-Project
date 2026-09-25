# Pipeline IGAE — 100% Python


## 1. `igae_analysis.py`
Limpia el CSV crudo de INEGI y calcula todo lo que necesita el reporte:
nivel, variación mensual/anual/acumulada, comparativo contra el mismo
periodo del año anterior (Total y las 3 grandes actividades), ranking de
subsectores, contribución en puntos porcentuales, y la tendencia de los
últimos 12 meses. Todo queda en `output/resumen.json`.

## 2. `build_report_word.py`
Lee `resumen.json` y arma el Reporte_IGAE.docx con `python-docx`. Mismo
título, mismo texto narrativo por sección que la versión que ya vio SEDECO
— lo único que cambia es que cada gráfica se reemplazó por su tabla
equivalente, y cada sección ahora compara explícitamente contra el mismo
periodo del año anterior.

## 3. `run_pipeline.py` — el punto de entrada para automatizar
Corre los dos scripts anteriores en un solo comando. Esto es lo que
llamaría el cron / GitHub Action cada mes:

```bash
pip install pandas python-docx
python run_pipeline.py --csv conjunto_de_datos_igae_igaeAAAA_MM.csv --outdir output
```

Genera `output/resumen.json` y `output/Reporte_IGAE.docx` de un jalón.
Si en algún momento quieren regresar a la versión con gráficas (para la
ficha ilustrada), se le agrega `--con-graficas` y genera también los PNG
(usa las mismas funciones de `igae_analysis.py` de antes).

## Qué cambió respecto a la versión anterior

| Antes | Ahora |
|---|---|
| R (Rmd) + Node.js (docx-js) para el reporte | Todo en Python (`pandas` + `python-docx`) |
| Gráficas (matplotlib) en el reporte | Tablas equivalentes en cada sección |
| Solo variación anual (%) | Tabla comparativa explícita: nivel año anterior vs. nivel actual, en Total, por gran actividad y en la tendencia de 12 meses |
| Texto narrativo | Se mantiene igual — es el que ya aprobó SEDECO |
| Dos scripts sueltos | Un solo comando (`run_pipeline.py`) listo para cron/Action |

## Siguiente paso

Reviso el formato del Word — si les gusta cómo quedaron las tablas, el
siguiente paso es conectar `--csv` a la API de INEGI (en vez de un archivo
local) y montar el cron/GitHub Action que llame `run_pipeline.py` cada mes.
