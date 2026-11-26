# Estado de evidencia y reproducibilidad — Taller 4

## Arquitectura

CockroachDB es el origen transaccional OLTP. El pipeline extrae los datos a Bronze (Parquet), limpia y tipa en Silver, modela Gold y ejecuta consultas analíticas con DuckDB. El benchmark SQLite/DuckDB mide la capa analítica; no equivale al benchmark de índice de CockroachDB.

## Calidad y NULL de canal

La ruta sintética directa (`USE_SYNTHETIC=true`) contiene anomalías deliberadas para probar Silver: duplicados, filas sin clave y NULL de `canal_id`. En esa corrida, Silver eliminó 2.082 duplicados de compras y 2.602 de intentos, descartó 40 filas sin clave en cada tabla e imputó 3.101 y 3.906 NULL respectivamente como `DESCONOCIDO`.

La ruta CockroachDB (`USE_SYNTHETIC=false`) se validó por separado. Una corrida anterior no tenía NULL en las tablas de hechos. En la repetición de las 23:19, CockroachDB v25.4.0, SQL directo y Bronze coincidieron en 208.236 compras con 3.101 NULL y 260.294 intentos con 3.906 NULL; las siete tablas Bronze identifican `_fuente=cockroachdb`, y Silver imputó los mismos NULL como `DESCONOCIDO`. Esto valida CockroachDB → Bronze → Silver. El contenido de la base fue generado por el cargador sintético del laboratorio, no son ventas reales. La corrida final del 26-11-2026 a las 16:40 (`USE_SYNTHETIC=false`, `Fuente: CockroachDB`) conservó los mismos conteos y NULL en Bronze y Silver (208.236 compras con 3.101 NULL; 260.294 intentos con 3.906 NULL; ambos imputados como `DESCONOCIDO`).

## Resultados medidos del pipeline

Ver [ejecuciones_pipeline.md](ejecuciones_pipeline.md), que registra por separado los conteos Bronze/Silver/Gold, validaciones, benchmarks analíticos y tiempos de ambas ejecuciones.

## Matriz de técnicas y estado de evidencia

| Técnica | Capa / motor | Evidencia disponible en el repositorio | Estado |
|---|---|---|---|
| Ordenamiento y data skipping | Parquet + DuckDB | `docs/taller4/planes/Q1_antes.txt`, `Q1_despues.txt`; benchmark de row groups y bytes leídos; 261,1 → 142,4 kB y 3 de 11 row groups, pero 4,97 ms → 5,02 ms (0,99x); `estadisticas_duckdb.csv` | Medida y documentada (corrida del 26-11-2026) |
| Particionado Hive | Parquet + DuckDB | `docs/taller4/planes/Q2_antes.txt`, `Q2_despues.txt`; pruning de archivos; 246,3 → 58,8 kB, pero 2,44 ms → 3,14 ms (0,78x); `estadisticas_duckdb.csv` | Medida y documentada (corrida del 26-11-2026) |
| Corrección VARCHAR → TIMESTAMP | DuckDB | `intervencion_tipos.md`, planes Q3; 14,338 ms → 4,285 ms (3,35x) con el mismo resultado; `estadisticas_tipos.csv` | Medida y documentada (corrida del 26-11-2026) |
| Índice compuesto (tiempo_sk, evento_sk) | CockroachDB | `benchmarks_cockroach.md`, planes EXPLAIN ANALYZE; lectura 426,217 ms → 210,591 ms (2,02x); INSERT +16,2 %; `estadisticas_cockroach.csv` | Medida y documentada (corrida del 26-11-2026) |

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

## Estado de entrega

- Los planes, medianas de consulta, impacto de INSERT y conversión a TIMESTAMP están incorporados en sus informes y evidencias, con las cifras de la corrida final del 26-11-2026.
- Los seis CSV de esa corrida (`mediciones_crudas_duckdb.csv`, `estadisticas_duckdb.csv`, `mediciones_crudas_tipos.csv`, `estadisticas_tipos.csv`, `mediciones_crudas_cockroach.csv`, `estadisticas_cockroach.csv`) están generados en `docs/taller4/`. Ya no hay estadística pendiente.
- El informe PDF tiene 9 páginas (máximo permitido: 10).
- El ZIP final reúne código, documentación y evidencias.
- Las mediciones son locales y el snapshot de CockroachDB es sintético; no deben presentarse como resultados de producción ni ventas reales.
- El PR #2 fue cerrado y fusionado en `main`. El informe PDF y el ZIP están publicados en `docs/taller4/informe_taller4.pdf` y `docs/entregables_tuboleta_lakehouse.zip`, respectivamente. La presencia de ambos archivos está verificada en el repositorio; la revisión del contenido interno del ZIP y el recuento independiente de páginas del PDF deben considerarse verificaciones de entrega separadas.
