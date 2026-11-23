# M2. Arquitectura de persistencia políglota e integración

> Documento de desarrollo de M2 para la entrega final. Se describen los motores y esquemas del repositorio, distinguiendo el diseño conceptual de los componentes realmente ejecutados.

## 2.1 Objetivo de la arquitectura

La arquitectura separa las operaciones que modifican el estado de una compra de las consultas que agregan grandes volúmenes de información histórica. Cada tecnología se asigna a un tipo de dato y patrón de acceso:

- **CockroachDB:** persistencia relacional transaccional y protección de la unicidad de una silla por evento.
- **Redis:** componente previsto para fila virtual, locks temporales y contadores con TTL. No está implementado ni desplegado en este laboratorio.
- **Parquet:** formato columnar de archivos para Bronze, Silver y Gold.
- **DuckDB:** motor analítico que consulta los archivos Parquet mediante read_parquet.
- **Python / pandas:** generación, extracción, limpieza, transformación y orquestación.

DuckDB no sustituye a CockroachDB. El primero atiende OLAP sobre snapshots; el segundo representa la fuente transaccional.

## 2.2 Vista lógica de la arquitectura

~~~text
              PROCESO DE VENTA (diseño operacional)
 Comprador
    |
    v
 Fila virtual / admisión
    |
    v
 Redis (previsto, no ejecutado)
 - estado de fila
 - lock de silla, TTL = 600 s
 - contadores efímeros
    |
    v
 Servicio de compra
    |
    v
 CockroachDB (implementado en laboratorio)
 - compras_confirmadas
 - intentos_compra
 - UNIQUE(evento_id, silla_id)
    |
    | extracción batch (SELECT *)
    v
 BRONZE / Parquet
 - snapshot crudo por tabla
 - _extraido_en / _fuente
    |
    | transform_silver.py
    v
 SILVER / Parquet
 - normalización y deduplicación
 - conversión de tipos
 - tratamiento de nulos
    |
    | transform_gold.py
    v
 GOLD / Parquet
 - 2 tablas de hechos
 - 6 dimensiones conformadas
 - SCD Tipo 2 en dim_zona
    |
    | DuckDB / read_parquet
    v
 Consultas de negocio y benchmark
 - scripts/analyze.py
 - scripts/consultar.py
~~~

Redis pertenece al flujo conceptual de admisión y bloqueo, pero no es dependencia del pipeline ejecutable. El pipeline puede correr en modo sintético sin CockroachDB; alternativamente, puede extraer el snapshot cargado en CockroachDB con USE_SYNTHETIC=false.

## 2.3 Persistencia políglota: tecnología y responsabilidad

| Tecnología | Modelo y datos | Patrón de acceso | Justificación | Estado |
|---|---|---|---|---|
| CockroachDB | Relacional SQL; catálogos y transacciones de compra | Inserciones y lecturas puntuales, restricciones | Fuente transaccional consistente y regla evento–silla expresada en la base | Nodo local Docker, snapshot sintético cargable y extracción verificada |
| Redis | Clave–valor efímero; fila, locks y contadores | Lecturas/escrituras rápidas con expiración | Estado temporal de admisión y reserva, separado del histórico de ventas | Diseñado/documentado; no desplegado |
| Parquet | Archivos columnares tipados | Lectura analítica por columnas, row groups y particiones | Almacenamiento histórico desacoplado del motor transaccional | Implementado en Bronze, Silver y Gold |
| DuckDB | Motor SQL analítico embebido | Escaneos columnares, filtros, joins y agregaciones | Ejecutar OLAP sobre archivos sin operar otro servidor | Implementado y usado en consultas/benchmarks |
| Python / pandas | Procesamiento tabular | ETL por lotes | Generación, extracción y transformaciones | Implementado |

### Justificación de la separación

Un motor relacional transaccional es apropiado para confirmar una compra porque la operación necesita restricciones e integridad sobre registros individuales. En cambio, las consultas de negocio recorren muchas ventas para agrupar por tiempo, evento, zona o canal. Ejecutar esos escaneos sobre la misma ruta transaccional puede competir con las escrituras de compra.

El repositorio materializa una separación OLTP/OLAP: CockroachDB conserva el snapshot operacional y el lakehouse recibe extracciones en Parquet. DuckDB procesa las consultas analíticas sin convertir el almacén de archivos en una base transaccional.

Una alternativa sería usar únicamente una base relacional para escrituras y análisis. No se adopta como arquitectura principal del ejercicio porque mezcla patrones de acceso distintos y no permite demostrar las ventajas del almacenamiento columnar y del modelo analítico. Esto no significa que un motor relacional no pueda ejecutar consultas analíticas; significa que no es el objetivo de esta arquitectura.

## 2.4 Esquema operacional en CockroachDB

El DDL está en **oltp/init/01_schema.sql**. El cargador **scripts/oltp/load_cockroach.py** crea la base tuboleta, ejecuta el esquema y carga las siete tablas operacionales.

| Tabla | Clave primaria | Atributos representativos | Función |
|---|---|---|---|
| canales | canal_id | nombre, digital_flag | Catálogo de canales |
| zonas | (zona_id, valido_desde) | tipo_zona, capacidad_zona, precio_base, vigencia, activo | Tarifario e historial de versiones de zona |
| eventos | evento_id | nombre, tipo, recinto, ciudad, fecha, inicio de ventas, aforo, organizador | Catálogo de eventos |
| sillas | silla_id | zona_id, fila, número, categoría | Inventario lógico de sillas |
| usuarios | usuario_id | segmento, canal_preferido | Atributos de usuario |
| compras_confirmadas | compra_id | silla, evento, usuario, canal, fecha, precio, descuento, tiempo de pago | Compra pagada |
| intentos_compra | intento_id | silla, evento, usuario, canal, fecha, resultado, tiempo en fila, compra asociada | Resultado persistido de cada intento |

### Restricciones e integridad

La tabla **compras_confirmadas** contiene:

- PRIMARY KEY (compra_id).
- UNIQUE (evento_id, silla_id), con nombre uq_compra_evento_silla.
- fecha_compra TIMESTAMP NOT NULL.
- canal_id STRING NULL, para conservar el canal ausente y resolverlo posteriormente en Silver.

La unicidad evento–silla es la protección transaccional central contra el double-booking. Una segunda inserción con la misma combinación no puede convertirse en otra compra confirmada.

El esquema SQL del repositorio no declara claves foráneas entre todas las tablas de catálogo y transacción. Las relaciones por identificadores se utilizan en la extracción y en la construcción del modelo analítico; no debe afirmarse que CockroachDB aplica restricciones FK que no aparecen en el DDL.

El esquema también incluye **fact_ventas_boletas** y **fact_ventas_insert_bench** para experimentación del laboratorio. No forman parte de las siete tablas operacionales extraídas por **scripts/extract.py**; el benchmark de índice se documenta por separado.

### Ejemplos de operaciones OLTP

**1. Consultar si una silla ya fue vendida para un evento**

~~~sql
SELECT compra_id, fecha_compra
FROM compras_confirmadas
WHERE evento_id = 'E-002'
  AND silla_id = 'S-00001';
~~~

La consulta permite verificar el estado persistido de la combinación evento–silla. La aplicación debe tratar la restricción única como garantía definitiva, no depender únicamente de una consulta previa: dos solicitudes concurrentes podrían consultar antes de que alguna inserte.

**2. Registrar una compra confirmada**

~~~sql
INSERT INTO compras_confirmadas (
    compra_id, silla_id, evento_id, usuario_id, canal_id,
    fecha_compra, precio_pagado, descuento_aplicado,
    tiempo_hasta_pago_seg
)
VALUES (
    'C-EXAMPLE-0001', 'S-00001', 'E-002', 'U-000001',
    'C-APP', CURRENT_TIMESTAMP, 280000, 0, 420
);
~~~

La sentencia ilustra la estructura de escritura del esquema. En ejecución real los valores deben provenir del servicio de compra; si ya existe una venta para E-002 y S-00001, la restricción uq_compra_evento_silla rechaza la inserción. La sentencia no representa una compra real ni se ejecuta como parte del pipeline.

## 2.5 Redis: función prevista y límite de implementación

En el diseño, Redis cumple una función distinta de CockroachDB:

- La fila virtual representa el estado temporal de admisión.
- El lock de silla reserva temporalmente una silla y utiliza un TTL de 600 segundos.
- Los contadores permiten representar posiciones o métricas operativas de la fila.
- Cuando el lock expira sin pago, el intento puede terminar como ABANDONO.
- Redis no se considera la fuente definitiva de una compra confirmada.

La configuración define **TTL_LOCK_SEG = 600** y el umbral de pago tardío en el 80 % del TTL. El generador produce resultados de intentos y la marca es_pago_tardio a partir de datos persistidos; no consulta una instancia Redis.

**Límite que debe declararse:** no existe servicio Redis en docker-compose.yml, no hay cliente Redis en las dependencias del pipeline y no se ejecutan operaciones SET NX EX. Por ello, el proyecto no demuestra adquisición concurrente de locks, liberación por expiración, política de recuperación ni rendimiento de Redis. Es una pieza de arquitectura propuesta y simulada por el generador.

## 2.6 Almacenamiento Lakehouse: Bronze, Silver y Gold

| Capa | Formato y contenido | Transformación | Propósito |
|---|---|---|---|
| Bronze | Parquet crudo por tabla y extracción | Agrega _extraido_en y _fuente; conserva la estructura recibida | Trazabilidad y conservación del dato de origen |
| Silver | Parquet limpio y tipado | Deduplicación, strip de IDs, conversión de fechas, imputación de canal_id nulo y descarte de filas sin clave | Calidad técnica y tipos consistentes |
| Gold | Parquet dimensional | Dimensiones, claves sustitutas, dos hechos y resolución temporal SCD2 | Consultas analíticas y métricas de negocio |

### Bronze

**extract.py** selecciona una de dos fuentes:

- **USE_SYNTHETIC=true** (valor por defecto): genera el snapshot determinista.
- **USE_SYNTHETIC=false**: ejecuta SELECT * sobre las siete tablas operacionales de CockroachDB.

Cada archivo se escribe con nombre basado en tabla y marca temporal, y contiene _extraido_en y _fuente. Así se identifica cuándo se extrajo y si el origen fue sintetico o cockroachdb.

### Silver

**transform_silver.py** aplica limpieza técnica sin introducir reglas analíticas de negocio. Entre las acciones están normalizar identificadores, eliminar duplicados por clave, convertir fechas almacenadas como texto a tipos temporales, resolver canal_id nulo con el miembro DESCONOCIDO y descartar registros sin clave de negocio.

El cargador OLTP prepara la estructura necesaria para satisfacer las restricciones de CockroachDB, pero conserva canal_id = NULL; no ejecuta la imputación de Silver. Esta separación permite observar y reportar los nulos que llegaron a Bronze desde CockroachDB.

### Gold

**transform_gold.py** genera seis dimensiones (dim_tiempo, dim_evento, dim_zona, dim_silla, dim_usuario, dim_canal) y dos tablas de hechos (fact_ventas_boletas, fact_intentos_compra).

La granularidad de los hechos es:

- **fact_ventas_boletas:** una silla vendida y pagada en un evento.
- **fact_intentos_compra:** un intento de compra asociado a una silla y su resultado.

Las dimensiones son conformadas entre ambos hechos. dim_zona usa SCD Tipo 2 porque el precio de VIP y Occidental cambia el 1 de julio de 2026. Cada hecho resuelve la versión vigente según la fecha de compra o de intento. Las validaciones del pipeline comprueban unicidad evento–silla, vínculo entre venta e intento COMPRA y que cada hecho resuelva exactamente una versión de zona.

## 2.7 Integración entre subsistemas y frescura

La integración implementada es **batch**:

1. El cargador opcional prepara y carga un snapshot sintético en CockroachDB.
2. extract.py lee las siete tablas con SELECT * o llama al generador sintético.
3. Bronze conserva un archivo Parquet por tabla y extracción.
4. Silver procesa la extracción más reciente.
5. Gold reconstruye el modelo dimensional.
6. DuckDB consulta Gold para producir resultados y benchmarks.

No existe integración streaming ni CDC implementada. Tampoco hay un programador de cargas recurrentes en el repositorio. La frescura del lakehouse depende de cuándo se ejecuta manualmente el pipeline. No debe afirmarse que los datos analíticos están sincronizados en tiempo real.

La evolución propuesta sería incorporar CDC o una estrategia incremental con marca de agua, conservando la separación entre fuente operacional y almacenamiento analítico. Kafka, Debezium o un servicio de orquestación serían componentes futuros, no parte de la implementación actual.

## 2.8 CAP y consistencia entre capas

La decisión CAP se aplica al plano operacional distribuido:

- CockroachDB es la fuente de verdad para la compra y prioriza consistencia transaccional y unicidad evento–silla.
- Redis se propone para estado efímero de fila y locks con TTL; su disponibilidad no debe reemplazar la garantía transaccional de CockroachDB.
- Bronze, Silver y Gold son snapshots por lotes. Pueden estar temporalmente desactualizados respecto de OLTP y no participan en la confirmación de una compra.
- DuckDB consulta el último Gold generado; no coordina escrituras de compra.

El nodo CockroachDB del docker-compose.yml se inicia con **start-single-node --insecure**. Esta configuración permite reproducir el laboratorio, pero no sirve para validar particiones, quórum o tolerancia a fallos de un clúster distribuido. La clasificación CP corresponde a la decisión arquitectónica y a las garantías transaccionales del motor, no a una prueba CAP ejecutada por el prototipo.

## 2.9 Alternativas y decisiones

| Necesidad | Decisión | Alternativa no elegida como arquitectura principal | Motivo |
|---|---|---|---|
| Compra transaccional | CockroachDB | Ejecutar compras en DuckDB/Parquet | Los archivos analíticos no sustituyen restricciones transaccionales sobre compras concurrentes |
| Estado efímero de fila y lock | Redis en el diseño | Persistir cada cambio temporal como compra | La fila y el lock son estados temporales, no hechos de venta |
| Almacenamiento analítico | Parquet | Mantener el histórico solo en tablas OLTP | Parquet permite lectura columnar desacoplada de la carga transaccional |
| Consultas analíticas | DuckDB | Ejecutar todas las agregaciones históricas en CockroachDB | DuckDB está orientado a escaneos y agregaciones sobre archivos |
| Integración | Extracción batch | Streaming/CDC | Batch es la integración implementada y reproducible; CDC queda como evolución |

## 2.10 Evidencia y comandos de reproducción

| Evidencia | Archivo |
|---|---|
| Arquitectura y alcance | README.md |
| Esquema SQL OLTP | oltp/init/01_schema.sql |
| Guía CockroachDB | oltp/README.md |
| Configuración, TTL y fuente | scripts/config.py |
| Carga del snapshot | scripts/oltp/load_cockroach.py |
| Extracción a Bronze | scripts/extract.py |
| Limpieza Silver | scripts/transform_silver.py |
| Modelo Gold | scripts/transform_gold.py |
| Modelo dimensional | docs/modelo_dimensional.dbml y docs/diseno_dimensional.md |
| Orquestación | main.py |

**Levantar y cargar CockroachDB (laboratorio):**

~~~bash
docker compose up -d
python -m scripts.oltp.load_cockroach
~~~

**Extraer desde CockroachDB (Windows PowerShell):**

~~~powershell
$env:USE_SYNTHETIC = "false"
python main.py
~~~

**Extraer desde CockroachDB (Linux/macOS):**

~~~bash
USE_SYNTHETIC=false python main.py
~~~

**Ejecutar el pipeline con datos sintéticos:**

~~~bash
python main.py
~~~

El pipeline predeterminado no necesita CockroachDB porque USE_SYNTHETIC vale true. El laboratorio CockroachDB requiere Docker y la carga previa del snapshot.

## 2.11 Criterios de aceptación de M2

- Se identifican las tecnologías políglotas y su responsabilidad.
- Se presenta la arquitectura desde el proceso operacional hasta las consultas analíticas.
- El esquema OLTP coincide con oltp/init/01_schema.sql.
- Se documenta la restricción única evento–silla y no se atribuyen al DDL claves foráneas inexistentes.
- Se distingue Redis diseñado de Redis ejecutado.
- Se describen Bronze, Silver y Gold según las transformaciones reales.
- Se especifica que la integración actual es batch y que no hay CDC/streaming.
- Los ejemplos SQL son compatibles con las columnas definidas en el esquema.
