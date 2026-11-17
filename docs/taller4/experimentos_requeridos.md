# Taller 4 — matriz de experimentos y reproducibilidad

## Arquitectura evaluada

CockroachDB es el motor OLTP que persiste el snapshot operacional. La extracción lleva los datos a Bronze en Parquet; Silver limpia y tipa; Gold organiza el modelo dimensional; DuckDB ejecuta las consultas analíticas. CockroachDB y DuckDB cumplen funciones diferentes y no se presentan como motores sustitutos.

## Tratamiento de calidad entre capas

El generador introduce suciedad intencional para probar la calidad de datos. La carga a CockroachDB realiza únicamente la preparación estructural indispensable para cumplir el esquema OLTP: recorta espacios en identificadores, descarta filas que incumplen columnas obligatorias y elimina duplicados que violarían la PK o la restricción UNIQUE(evento_id, silla_id). No ejecuta la limpieza completa de Silver y no reemplaza los valores nulos de canal_id.

El tratamiento debe describirse por ruta de ejecución, porque las fuentes no contienen necesariamente las mismas anomalías:

- **Sintético directo (`USE_SYNTHETIC=true`):** Bronze incluye duplicados, filas sin clave y NULL de `canal_id`; Silver deduplica, descarta filas sin clave e imputa los NULL como `DESCONOCIDO`.
- **CockroachDB (`USE_SYNTHETIC=false`):** la carga OLTP aplica preparación estructural para cumplir PK/UNIQUE/NOT NULL. La extracción conserva lo que realmente está almacenado en CockroachDB; Silver solo puede imputar los NULL que efectivamente reciba.
- **Gold:** `dim_canal` incluye el miembro especial `DESCONOCIDO` para resolver referencias sin canal conocido. La presencia de esa fila dimensional no demuestra por sí sola que se haya imputado un NULL en Silver.

### Estado de validación de las ejecuciones (16-11-2026)

- **Sintético directo:** Bronze tenía 210.358 compras y 262.936 intentos. Silver conservó 208.236 compras y 260.294 intentos; imputó 3.101 NULL de `canal_id` en compras y 3.906 en intentos, además de deduplicar y descartar registros sin clave.
- **CockroachDB, corrida anterior:** se documentó una extracción con cero NULL resueltos. Esa ejecución por sí sola no demostraba la imputación en la ruta OLTP.
- **CockroachDB, corrida verificada de las 23:19:** `main.py` se ejecutó con `USE_SYNTHETIC=false` contra CockroachDB v25.4.0. Las siete tablas Bronze quedaron marcadas `_fuente=cockroachdb`. SQL directo y Bronze coincidieron: `compras_confirmadas` 208.236 filas / 3.101 NULL de `canal_id`; `intentos_compra` 260.294 / 3.906 NULL. Silver resolvió esos mismos NULL como `DESCONOCIDO`. Esto valida CockroachDB → Bronze → Silver.

El snapshot cargado en CockroachDB fue generado por el cargador sintético del laboratorio. La ejecución valida conexión, transporte y calidad del flujo, pero no usa ventas reales de TuBoleta. El detalle de ambas rutas está en [ejecuciones_pipeline.md](ejecuciones_pipeline.md).

Las mediciones de índice e inserciones están en `benchmarks_cockroach.md` y `planes/cockroach_Q1_*.txt`; las de tipos, en `intervencion_tipos.md` y `planes/Q3_tipos_*.txt`. Son mediciones locales sobre datos experimentales, no resultados de producción. Para usar datos reales de TuBoleta hace falta importarlos a las siete tablas operacionales; el repositorio no incluye ese origen real.

## Las cuatro técnicas solicitadas

| Técnica | Motor/capa | Comparación | Evidencia |
|---|---|---|---|
| Ordenamiento / data skipping | Parquet + DuckDB | Fact sin ordenamiento frente a Parquet ordenado por tiempo_sk | Planes Q1 y perfil de row groups |
| Particionado Hive | Parquet + DuckDB | Un archivo frente a carpetas year/month | Plan Q2 y pruning de particiones |
| Corrección de tipos | DuckDB | Control VARCHAR + CAST frente a TIMESTAMP nativo | scripts/taller4_tipos.py y planes Q3 |
| Índice compuesto | CockroachDB | Full scan frente a índice (tiempo_sk, evento_sk) | benchmark_cockroach.py y EXPLAIN ANALYZE |

## Volumen y validez

El generador funcional produce cinco eventos, 45.000 sillas y alrededor de 208.000 compras confirmadas. Incrementar N_USUARIOS por sí solo no aumenta el número de ventas: la cantidad está acotada por la capacidad de sillas y el número de eventos. Por eso el laboratorio de índice amplía un conjunto experimental separado, con identificadores BENCH, claves evento/silla no repetidas y semilla fija. Ese conjunto sirve para medir escalabilidad de acceso a CockroachDB; no representa ventas observadas ni modifica los ingresos Gold.

Se recomienda ejecutar 1.000.000 de filas como escenario principal y repetir con 200.000 y 3.000.000. Reportar la cantidad efectiva, hardware, versión de CockroachDB, método de calentamiento, mediana y dispersión.

## Comandos

~~~bash
# 1. Construir Bronze, Silver y Gold funcionales
python main.py

# 2. (Opcional) cargar el snapshot sintético reproducible del laboratorio
docker compose up -d
docker compose ps
python -m scripts.oltp.load_cockroach

# El cargador anterior genera datos sintéticos. Para datos reales, importa primero
# el origen propio en las siete tablas operacionales del esquema CockroachDB.
# 3. Extraer desde CockroachDB y validar la calidad en Silver
# Windows PowerShell:
$env:USE_SYNTHETIC = "false"
python main.py
# Linux/macOS:
USE_SYNTHETIC=false python main.py

# 4. Ejecutar el benchmark OLTP: full scan, índice y costo de INSERT
python -m scripts.oltp.benchmark_cockroach

# 5. Ejecutar conversión de tipo en DuckDB
python -m scripts.taller4_tipos
~~~

Para repetir OLTP con otros volúmenes (PowerShell):

~~~powershell
$env:OLTP_BENCH_ROWS = "3000000"
python -m scripts.oltp.benchmark_cockroach
~~~

## Criterios de aceptación

- Las consultas antes y después devuelven exactamente los mismos resultados.
- El plan anterior muestra lectura completa de la tabla o ausencia de un rango selectivo sobre tiempo_sk.
- El plan posterior muestra el índice compuesto solicitado. El script usa FORCE_INDEX para que la comparación mida ese acceso; además conserva el plan real.
- Se mide la inserción sobre una tabla aislada con y sin índice secundario, con el mismo lote.
- Resultados medidos: la mediana de consulta CockroachDB fue 687,713 ms sin índice y 331,261 ms con índice; la inserción de 20.000 filas pasó de 460,19 a 508,56 ms. No son mediciones de producción.
- En DuckDB, VARCHAR + CAST dio 19,887 ms frente a 4,996 ms con TIMESTAMP (3,98x); ambos escenarios devolvieron 34.039 filas y 3.689.715.500 COP.
- Se conserva el resultado de tipos aunque el tiempo no mejore: una diferencia pequeña o negativa debe analizarse, no ocultarse.
- Tras la carga CockroachDB, el NULL de canal_id debe seguir presente en Bronze y el contador de Silver debe ser mayor que cero. Silver debe dejar cero nulos en esa columna después de imputar DESCONOCIDO.
- Los tiempos son resultados locales reproducibles, no cifras universales.

## Limitaciones que deben declararse

El contenedor usa un solo nodo CockroachDB en modo insecure para laboratorio local. No representa tolerancia a fallos ni rendimiento distribuido multi-nodo. Los registros de expansión del benchmark son sintéticos. Los planes y tiempos de CockroachDB solo aparecen después de ejecutar el laboratorio; no se deben rellenar con estimaciones.
