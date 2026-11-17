# Estado de evidencia y reproducibilidad — Taller 4

## Arquitectura

CockroachDB es el origen transaccional OLTP. El pipeline extrae los datos a Bronze (Parquet), limpia y tipa en Silver, modela Gold y ejecuta consultas analíticas con DuckDB. El benchmark SQLite/DuckDB mide la capa analítica; no equivale al benchmark de índice de CockroachDB.

## Calidad y NULL de canal

La ruta sintética directa (`USE_SYNTHETIC=true`) contiene anomalías deliberadas para probar Silver: duplicados, filas sin clave y NULL de `canal_id`. En la corrida compartida, Silver eliminó 2.082 duplicados de compras y 2.602 de intentos, descartó 40 filas sin clave en cada tabla e imputó 3.101 y 3.906 NULL respectivamente como `DESCONOCIDO`.

La ruta CockroachDB (`USE_SYNTHETIC=false`) es una extracción diferente. La ejecución compartida reportó 208.236 compras y 260.294 intentos tanto en Bronze como en Silver, sin duplicados, filas descartadas ni NULL resueltos. Por tanto, esa ejecución no constituye evidencia de imputación de NULL. La prueba de que Silver resuelve NULL está en la ruta sintética directa.

No se deben trasladar las cifras de calidad de una ruta a la otra ni describir la salida CockroachDB compartida como si Silver hubiera imputado valores nulos.

## Resultados medidos del pipeline

Ver [ejecuciones_pipeline.md](ejecuciones_pipeline.md), que registra por separado los conteos Bronze/Silver/Gold, validaciones, benchmarks analíticos y tiempos de ambas ejecuciones.

## Matriz de técnicas y estado de evidencia

| Técnica | Capa / motor | Evidencia disponible en el repositorio | Estado |
|---|---|---|---|
| Ordenamiento y data skipping | Parquet + DuckDB | `docs/taller4/planes/Q1_antes.txt`, `Q1_despues.txt`; benchmark de row groups y bytes leídos | Documentada |
| Particionado Hive | Parquet + DuckDB | `docs/taller4/planes/Q2_antes.txt`, `Q2_despues.txt`; pruning de archivos | Documentada |
| Corrección VARCHAR → TIMESTAMP | DuckDB | Script `scripts/taller4_tipos.py`; debe ejecutarse para producir `intervencion_tipos.md` y planes | Pendiente de incorporar salida medida |
| Índice compuesto (tiempo_sk, evento_sk) | CockroachDB | Script `scripts/oltp/benchmark_cockroach.py`; debe ejecutarse para producir `benchmarks_cockroach.md` y planes | Pendiente de incorporar salida medida |

## Comandos de ejecución

```bash
# CockroachDB local
docker compose up -d
python -m scripts.oltp.load_cockroach

# Extraer desde CockroachDB y ejecutar el pipeline
# PowerShell:
$env:USE_SYNTHETIC = "false"
python main.py

# Experimentos del Taller 4
python -m scripts.oltp.benchmark_cockroach
python -m scripts.taller4_tipos
```

El benchmark OLTP usa por defecto 1.000.000 de filas experimentales (`OLTP_BENCH_ROWS`) y mide un lote de 20.000 INSERT (`OLTP_INSERT_ROWS`). Esas filas se generan con prefijo BENCH en una tabla de prueba y no representan ventas reales ni alteran los resultados Gold. El benchmark de INSERT usa una tabla aislada. Los tiempos deben copiarse únicamente desde la salida generada en el equipo donde se ejecuta.

## Criterio para cerrar la entrega

- Incorporar las salidas reales de `benchmarks_cockroach.md` e `intervencion_tipos.md`.
- Verificar que los planes antes/después correspondan a la misma corrida y configuración.
- Regenerar el PDF a partir del informe Markdown con `python -m scripts.taller4_pdf` en un equipo con Edge o Chrome.
- Actualizar el ZIP de entrega después de regenerar los documentos.
- No dar por cerrado el PR hasta comprobar los experimentos que aún están pendientes.
