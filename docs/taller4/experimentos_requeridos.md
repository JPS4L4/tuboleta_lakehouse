# Taller 4 — matriz de experimentos y reproducibilidad

## Arquitectura evaluada

CockroachDB es el motor OLTP que persiste las ventas confirmadas. La extracción lleva los datos a Bronze en Parquet; Silver limpia y tipa; Gold organiza el modelo dimensional; DuckDB ejecuta las consultas analíticas. La arquitectura no compara DuckDB contra CockroachDB como si fueran sustitutos: cada uno cumple una función diferente.

## Las cuatro técnicas solicitadas

| Técnica | Motor/capa | Comparación | Evidencia |
|---|---|---|---|
| Ordenamiento / data skipping | Parquet + DuckDB | Fact sin ordenamiento frente a Parquet ordenado por tiempo_sk | Planes Q1 y perfil de row groups |
| Particionado Hive | Parquet + DuckDB | Un archivo frente a carpetas year/month | Plan Q2 y pruning de particiones |
| Corrección de tipos | DuckDB | Fecha VARCHAR con CAST frente a TIMESTAMP nativo | scripts/taller4_tipos.py y planes Q3 |
| Índice compuesto | CockroachDB | Full scan frente a índice (tiempo_sk, evento_sk) | benchmark_cockroach.py y EXPLAIN ANALYZE |

## Volumen y validez

El generador de negocio conserva su volumen realista y las reglas de integridad del modelo. Incrementar N_USUARIOS por sí solo no aumenta el número de ventas: la cantidad de compras está acotada por la capacidad de sillas y el número de eventos. Por eso el laboratorio OLTP amplía un conjunto experimental separado, con identificadores BENCH, claves evento/silla no repetidas y semilla fija. El conjunto expandido sirve para medir escalabilidad de acceso a CockroachDB, no para afirmar que son ventas observadas ni para modificar los ingresos Gold.

Se recomienda ejecutar 1.000.000 de filas como escenario principal y repetir con 200.000 y 3.000.000. Reportar la cantidad efectiva, hardware, versión de CockroachDB, método de calentamiento, mediana y dispersión.

## Comandos

```bash
# 1. Construir Bronze, Silver y Gold funcionales
python main.py

# 2. Levantar CockroachDB local
docker compose up -d
docker compose ps

# 3. Ejecutar OLTP: carga, full scan, índice y costo de INSERT
python -m scripts.oltp.benchmark_cockroach

# 4. Ejecutar conversión de tipo en DuckDB
python -m scripts.taller4_tipos

# 5. Repetir OLTP con otros volúmenes (en PowerShell)
$env:OLTP_BENCH_ROWS = "3000000"
python -m scripts.oltp.benchmark_cockroach
```

## Criterios de aceptación

- Las consultas antes y después devuelven exactamente los mismos resultados.
- El plan anterior muestra lectura completa de la tabla o ausencia de un rango selectivo sobre tiempo_sk.
- El plan posterior muestra el índice compuesto solicitado. El script usa FORCE_INDEX para que la comparación mida ese acceso; además conserva el plan real.
- Se mide la inserción sobre una tabla aislada con y sin índice secundario, con el mismo lote.
- Se conserva el resultado de tipos aunque el tiempo no mejore: una diferencia pequeña o negativa debe analizarse, no ocultarse.
- Los tiempos son resultados locales reproducibles, no cifras universales.

## Limitaciones que deben declararse

El contenedor usa un solo nodo CockroachDB en modo insecure para laboratorio local. No representa tolerancia a fallos ni rendimiento distribuido multi-nodo. Los registros de expansión son sintéticos. Los planes y tiempos de CockroachDB solo aparecen después de ejecutar el laboratorio; no se deben rellenar con estimaciones.
