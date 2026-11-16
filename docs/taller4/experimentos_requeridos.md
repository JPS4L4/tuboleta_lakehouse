# Taller 4 — matriz de experimentos y reproducibilidad

## Arquitectura evaluada

CockroachDB es el motor OLTP que persiste el snapshot operacional. La extracción lleva los datos a Bronze en Parquet; Silver limpia y tipa; Gold organiza el modelo dimensional; DuckDB ejecuta las consultas analíticas. CockroachDB y DuckDB cumplen funciones diferentes y no se presentan como motores sustitutos.

## Tratamiento de calidad entre capas

El generador introduce suciedad intencional para probar la calidad de datos. La carga a CockroachDB realiza únicamente la preparación estructural indispensable para cumplir el esquema OLTP: recorta espacios en identificadores, descarta filas que incumplen columnas obligatorias y elimina duplicados que violarían la PK o la restricción UNIQUE(evento_id, silla_id). No ejecuta la limpieza completa de Silver y no reemplaza los valores nulos de canal_id.

El flujo correcto de canal_id es:

1. Fuente sintética → CockroachDB: el campo acepta NULL y esos NULL se conservan.
2. CockroachDB → Bronze: la extracción lleva el NULL sin imputarlo.
3. Bronze → Silver: limpiar_tabla() cuenta los nulos y los imputa como DESCONOCIDO.
4. Silver → Gold: dim_canal contiene el miembro especial DESCONOCIDO y los hechos resuelven su clave sustituta.

El miembro desconocido preserva la integridad referencial sin inventar el canal original. El reporte de Silver debe mostrar los nulos realmente resueltos en esa ejecución. En modo sintético directo, Bronze también contiene duplicados y filas sin clave; en la fuente CockroachDB esas anomalías estructurales se eliminan antes de insertar porque las restricciones OLTP no permiten almacenarlas. La tasa de nulos de canal sí se conserva en ambos recorridos.

### Estado de validación de la última ejecución compartida

La ejecución del 16-11-2026 completó extracción, Silver, Gold y análisis, pero el reporte mostró `Nulos resueltos: 0` tanto para `compras_confirmadas` como para `intentos_compra`. Aunque Gold generó el miembro `DESCONOCIDO`, ese resultado no demuestra que se haya imputado un NULL en Silver: también puede haber valores literales `DESCONOCIDO` en la fuente. Por tanto, esta corrida no se considera evidencia de la conservación de nulos. El cargador incorpora ahora dos controles: conteo de nulos en los DataFrames antes de insertar y consulta `IS NULL` en CockroachDB después de insertar. La validación se acepta solo cuando ambos conteos coinciden y Silver registra esos nulos como resueltos. Es necesario actualizar la rama local, recargar CockroachDB y volver a ejecutar `main.py` antes de cerrar el informe.

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

# 2. Levantar CockroachDB local y cargar el snapshot operacional
docker compose up -d
docker compose ps
python -m scripts.oltp.load_cockroach

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
- Se conserva el resultado de tipos aunque el tiempo no mejore: una diferencia pequeña o negativa debe analizarse, no ocultarse.
- Tras la carga CockroachDB, el NULL de canal_id debe seguir presente en Bronze y el contador de Silver debe ser mayor que cero. Silver debe dejar cero nulos en esa columna después de imputar DESCONOCIDO.
- Los tiempos son resultados locales reproducibles, no cifras universales.

## Limitaciones que deben declararse

El contenedor usa un solo nodo CockroachDB en modo insecure para laboratorio local. No representa tolerancia a fallos ni rendimiento distribuido multi-nodo. Los registros de expansión del benchmark son sintéticos. Los planes y tiempos de CockroachDB solo aparecen después de ejecutar el laboratorio; no se deben rellenar con estimaciones.
