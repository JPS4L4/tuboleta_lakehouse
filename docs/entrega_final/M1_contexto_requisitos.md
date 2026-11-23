# M1. Contexto del dominio, cargas de trabajo y requisitos

> Documento de desarrollo de M1 para la entrega final. Las cifras describen el generador y las ejecuciones del laboratorio; no representan tráfico real ni compromisos de servicio de TuBoleta.

## 1.1 Contexto y problema de negocio

El proyecto modela la comercialización de boletería para eventos en el Estadio Atanasio Girardot, Medellín. La solución debe atender dos necesidades con perfiles de acceso diferentes:

1. **Operación transaccional:** registrar compras confirmadas y resultados de intentos de compra, evitando que una misma silla se venda dos veces para un mismo evento.
2. **Análisis histórico:** consultar ventas, ingresos, ocupación, comportamiento por canal y conversión del proceso de compra por evento, zona y período.

La arquitectura separa el plano operacional del analítico. CockroachDB representa la fuente transaccional de verdad; Redis aparece en el diseño como componente de estado efímero para fila virtual y bloqueos temporales; Parquet almacena las extracciones en Bronze, Silver y Gold; DuckDB ejecuta consultas analíticas sobre los archivos Parquet.

**Alcance real del prototipo.** El repositorio implementa el generador sintético, el laboratorio local de CockroachDB, la carga de un snapshot sintético, la extracción desde CockroachDB, las transformaciones Parquet y el análisis con DuckDB. Redis no se despliega ni ejecuta: la fila y los locks se representan mediante reglas y resultados generados sintéticamente. Por tanto, el proyecto demuestra el flujo de datos y las restricciones transaccionales en CockroachDB, pero no mide concurrencia de Redis ni el comportamiento de una plataforma de venta en producción.

## 1.2 Dominio y actores

| Actor o componente | Responsabilidad |
|---|---|
| Comprador | Selecciona un evento y una silla, inicia un intento y completa o no el pago. |
| Servicio de fila virtual | En el diseño, regula la admisión de compradores en períodos de alta demanda. No está implementado como servicio. |
| Gestor de bloqueo de sillas | En el diseño, reserva temporalmente una silla mediante un lock con TTL. Se representa conceptualmente con Redis; no se ejecuta en el laboratorio. |
| Servicio transaccional | Persiste la compra confirmada y aplica la regla de unicidad evento–silla en CockroachDB. |
| Proceso de extracción | Lee las siete tablas operacionales o genera datos sintéticos y escribe los archivos Bronze. |
| Proceso analítico | Limpia, tipa, modela y consulta los datos con Python, Parquet y DuckDB. |
| Analista / responsable del evento | Consulta ventas, ingresos, ocupación, canales y resultados del embudo. |

## 1.3 Proceso de compra modelado

El flujo conceptual es:

1. El comprador ingresa a la fila virtual.
2. El servicio de admisión permite que continúe.
3. Se solicita un bloqueo temporal de la silla. La configuración define un TTL de **600 segundos**.
4. Si el pago se confirma dentro del tiempo permitido, se registra la compra en CockroachDB.
5. Si vence el TTL sin pago, el intento termina como **ABANDONO** y la silla puede liberarse.
6. Si otro comprador ya registró la misma silla para el mismo evento, la restricción única de CockroachDB rechaza la segunda compra; el intento se clasifica como **RECHAZO_UNIQUE**.

La regla de integridad central es que una silla no puede venderse dos veces para un evento. En OLTP se materializa mediante la restricción única sobre **(evento_id, silla_id)** en **compras_confirmadas**. En Gold se replica con unicidad sobre **(evento_sk, silla_sk)** en **fact_ventas_boletas** y se valida durante la transformación.

El modelo distingue dos procesos analíticos:

- **Ventas confirmadas:** una fila representa una silla vendida y pagada para un evento.
- **Intentos de compra:** una fila representa un intento asociado a una silla, con resultado COMPRA, ABANDONO o RECHAZO_UNIQUE.

Un abandono no se contabiliza como venta. Esta separación evita inflar los ingresos al sumar hechos de distinta naturaleza.

## 1.4 Alcance de los datos y volumen de referencia

Los datos son sintéticos y reproducibles mediante una semilla fija (**SEED = 42**). El generador modela cinco eventos, cuatro zonas, tres canales, 45.000 sillas y 150.000 usuarios. Los precios de VIP y Occidental cambian el 1 de julio de 2026 para permitir el análisis histórico mediante SCD Tipo 2.

En una ejecución funcional documentada, Gold contiene:

| Elemento | Volumen |
|---|---:|
| Eventos | 5 |
| Zonas de negocio | 4 |
| Versiones de zona | 6 |
| Canales de origen | 3 |
| Sillas | 45.000 |
| Usuarios | 150.000 |
| Ventas confirmadas | 208.236 |
| Intentos de compra | 260.294 |
| Registros de dimensión tiempo | 5.656 |

Estos valores describen el conjunto de prueba del repositorio. No son ventas históricas reales, capacidad productiva ni tasas observadas de conversión de TuBoleta. Las tasas de abandono, rechazo, descuento y pago tardío son parámetros del generador.

## 1.5 Cargas de trabajo

| Carga | Tipo | Escala demostrada | Patrón de acceso | Consistencia requerida |
|---|---|---|---|---|
| Confirmar compra | OLTP, escritura puntual | Una compra por silla/evento; conjunto funcional de 208.236 ventas | Inserción por clave de compra y validación de unicidad | Alta: no aceptar dos ventas para la misma silla/evento |
| Consultar compra o intento | OLTP, lectura puntual | Tablas de compras e intentos | Búsqueda por identificadores de compra, intento, evento o silla | Lectura coherente con el estado transaccional |
| Registrar resultado del intento | OLTP, escritura | 260.294 intentos en el snapshot de referencia | Inserción de un resultado por intento | Distinguir compra, abandono y rechazo |
| Extraer datos | Batch / ETL | Siete tablas operacionales | Lectura por tabla mediante SELECT; ejecución por lote | Snapshot del momento de extracción; no hay CDC |
| Limpiar y tipar | Batch / ETL | Todo el conjunto extraído | Procesamiento de archivos Parquet | Reglas deterministas de deduplicación, tipado e imputación |
| Construir el modelo analítico | Batch / OLAP | Dos hechos y seis dimensiones | Reconstrucción completa de Gold | Integridad de claves y correspondencia temporal SCD2 |
| Consultas de negocio | OLAP, lectura intensiva | 208.236 ventas y 260.294 intentos | Agregaciones por evento, zona, canal y período | Consistencia del snapshot; no es lectura transaccional en tiempo real |

Las consultas analíticas que justifican el modelo son: ventas e ingresos por evento/zona/mes; conversión de intentos; ventas por canal; ocupación por evento y zona; y variación de ingresos según la versión del precio de una zona.

## 1.6 Requisitos funcionales

1. Registrar compras confirmadas e intentos con identificadores de negocio.
2. Impedir la doble venta de una silla dentro de un mismo evento.
3. Diferenciar compras pagadas, abandonos y rechazos por unicidad.
4. Conservar fecha y hora de compra e intento para el análisis temporal.
5. Identificar evento, silla, usuario, zona y canal asociados a cada registro.
6. Mantener el histórico de cambios de precio de las zonas mediante versiones con vigencia.
7. Extraer las tablas operacionales a Bronze sin ocultar valores nulos que deben tratarse en Silver.
8. Producir un modelo Gold que permita responder consultas de ventas y del embudo.

## 1.7 Requisitos no funcionales

El repositorio no define acuerdos de nivel de servicio (SLA/SLO) de producción ni mide la disponibilidad de una plataforma distribuida. Por ello, se separan los atributos derivados del diseño de las metas que todavía tendrían que acordarse con el negocio.

| Atributo | Requisito de diseño | Evidencia o límite actual |
|---|---|---|
| Integridad transaccional | No permitir más de una compra por evento–silla | Restricción UNIQUE en CockroachDB y validación equivalente en Gold |
| Consistencia | Priorizar la corrección de la compra sobre la disponibilidad de una réplica aislada | CockroachDB es fuente de verdad; laboratorio de un nodo |
| Disponibilidad | La fila virtual puede degradarse sin comprometer la regla final de venta | Redis no está desplegado; no hay medición |
| Rendimiento OLTP | Operaciones puntuales y acceso eficiente por claves | Hay experimento de índice; no hay SLO productivo |
| Rendimiento OLAP | Consultas eficientes sobre columnas y agregaciones | DuckDB consulta Parquet Gold; hay benchmarks locales |
| Escalabilidad | Separar carga transaccional de escaneos analíticos | Separación arquitectónica; entorno local y dataset sintético |
| Calidad de datos | Deduplicar, normalizar IDs, tipar fechas, tratar nulos y descartar filas sin clave | Silver y reporte de calidad |
| Reproducibilidad | Regenerar datos y repetir el pipeline | Semilla fija 42 y comando python main.py |
| Retención y trazabilidad | Identificar archivos por tabla, extracción y fuente | Bronze agrega _extraido_en y _fuente; no hay política formal de retención |
| Seguridad | No usar configuración insegura en producción | --insecure y root se limitan al laboratorio; falta endurecimiento productivo |
| Costos | Entorno académico reproducible y de bajo costo | Docker local, Python, Parquet y DuckDB; sin estimación productiva |

**Metas pendientes de definición:** latencia máxima de compra, disponibilidad mensual, RPO/RTO, retención histórica, volumen máximo esperado, concurrencia pico, presupuesto y objetivo de frescura del lakehouse. No se asignan cifras sin requisitos del negocio o pruebas que las respalden.

## 1.8 Decisión CAP por subsistema

CAP se usa como criterio de diseño para servicios distribuidos bajo una partición de red; no como etiqueta universal de cada producto. La clasificación describe la intención arquitectónica, no una prueba de tolerancia a fallos ejecutada en el laboratorio.

| Subsistema | Prioridad de diseño | Comportamiento esperado ante partición | Justificación y estado |
|---|---|---|---|
| Redis (fila y locks efímeros) | AP, según el diseño documentado | Mantener admisión/estado temporal disponible cuando sea posible, aceptando que no es autoridad final de venta | Fila y locks con TTL de 600 s. Redis no está desplegado ni probado; AP es una decisión conceptual |
| CockroachDB (compras confirmadas) | CP, según el diseño documentado | Priorizar consistencia y unicidad; una partición sin quórum puede reducir disponibilidad antes que aceptar ventas conflictivas | Fuente de verdad con UNIQUE evento–silla. El laboratorio es de un nodo y no valida particiones de clúster |
| Parquet / Bronze-Silver-Gold | No se asigna categoría CAP en este prototipo | Los archivos representan snapshots derivados y no coordinan escrituras transaccionales distribuidas | Extracción batch; Parquet se regenera en cada ejecución |
| DuckDB | No se usa como coordinador transaccional distribuido | Ejecuta lecturas analíticas locales sobre Parquet | Motor OLAP; no reemplaza la fuente de verdad |

La separación evita que un estado temporal de fila o bloqueo se convierta en autoridad de compra. La confirmación final depende de CockroachDB y de la restricción única evento–silla. Incluso si la capa de admisión temporal presenta una condición de concurrencia, la regla de integridad se protege en la base transaccional.

## 1.9 Criterios de aceptación de M1

- Dominio y flujo de compra descritos con actores y estados.
- Cargas OLTP, ETL y OLAP diferenciadas.
- Volúmenes identificados como sintéticos y reproducibles.
- Requisitos no funcionales separados entre decisiones implementadas y objetivos aún no medidos.
- Decisión CAP justificada por subsistema, aclarando que Redis no se ejecutó y CockroachDB se probó localmente en un solo nodo.

## 1.10 Evidencia del repositorio

- **README.md:** alcance, dominio, arquitectura, volúmenes y limitaciones.
- **scripts/config.py:** TTL, semilla, volúmenes y conexión.
- **scripts/generate_synthetic.py:** eventos, zonas, canales, usuarios, ventas e intentos sintéticos.
- **oltp/init/01_schema.sql:** tablas operacionales y restricción única evento–silla.
- **scripts/oltp/load_cockroach.py:** carga estructural del snapshot sintético.
- **scripts/extract.py:** extracción desde CockroachDB o fuente sintética hacia Bronze.
- **docs/diseno_dimensional.md:** procesos analíticos, granularidad y dimensiones.
