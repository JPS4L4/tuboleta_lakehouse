# Benchmark OLTP — CockroachDB

- Filas experimentales: **1,000,000**
- Carga inicial sin índice secundario: **22835.77 ms**
- Lectura: rango temporal de septiembre de 2026; calentamiento y mediana de 7 corridas.
- Escritura: mediana de 3 lotes de 20,000 filas en tabla aislada.
- Filas expandidas sintéticas y reproducibles; no representan ventas reales ni alteran Gold.

| Medición | Sin índice | Con índice compuesto |
|---|---:|---:|
| Consulta (ms) | 426.217 | 210.591 |
| Inserción (20,000 filas, ms) | 308.35 | 358.24 |
| Costo relativo de escritura | 1.00x | 1.16x |

Factor lectura: **2.02x**. Interpretar con planes, filas procesadas, caché y configuración local.

## Evidencia
- planes/cockroach_Q1_antes_full_scan.txt
- planes/cockroach_Q1_despues_index_scan.txt

## Plan antes
planning time: 450µs
execution time: 732ms
distribution: local
vectorized: true
plan type: custom
rows decoded from KV: 1,000,000 (73 MiB, 8 gRPC calls)
cumulative time spent in KV: 445ms
cumulative time spent due to contention: 11ms
cumulative time spent waiting to acquire latches: 11ms
maximum memory usage: 17 MiB
DistSQL network usage: 0 B (0 messages)
sql cpu time: 530ms
isolation level: serializable
priority: normal
quality of service: regular

• group (hash)
│ sql nodes: n1
│ actual row count: 23
│ execution time: 188ms
│ estimated max memory allocated: 7.1 MiB
│ estimated max sql temp disk usage: 0 B
│ sql cpu time: 188ms
│ estimated row count: 1
│ group by: evento_sk
│
└── • filter
    │ sql nodes: n1
    │ actual row count: 164,066
    │ execution time: 98ms
    │ sql cpu time: 97ms
    │ estimated row count: 1
    │ filter: (tiempo_sk >= 2026090100) AND (tiempo_sk <= 2026093023)
    │
    └── • scan
          sql nodes: n1
          kv nodes: n1
          actual row count: 1,000,000
          KV time: 445ms
          KV contention time: 11ms
          KV latch wait time: 11ms
          KV rows decoded: 1,000,000
          KV bytes read: 73 MiB
          KV gRPC calls: 8
          estimated max memory allocated: 10 MiB
          sql cpu time: 245ms
          estimated row count: 1 (100% of the table; stats collected 11 seconds ago)
          table: fact_ventas_boletas@fact_ventas_boletas_pkey  ----------------------  WARNING: the row count estimate is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
          spans: FULL SCAN

WARNING: the row count estimate on table "fact_ventas_boletas" is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
## Plan después
planning time: 272µs
execution time: 241ms
distribution: local
vectorized: true
plan type: custom
rows decoded from KV: 164,066 (9.7 MiB, 1 gRPC calls)
cumulative time spent in KV: 63ms
maximum memory usage: 17 MiB
DistSQL network usage: 0 B (0 messages)
sql cpu time: 221ms
isolation level: serializable
priority: normal
quality of service: regular

• group (hash)
│ sql nodes: n1
│ actual row count: 23
│ execution time: 178ms
│ estimated max memory allocated: 7.1 MiB
│ estimated max sql temp disk usage: 0 B
│ sql cpu time: 177ms
│ estimated row count: 1
│ group by: evento_sk
│
└── • scan
      sql nodes: n1
      kv nodes: n1
      actual row count: 164,066
      KV time: 63ms
      KV rows decoded: 164,066
      KV bytes read: 9.7 MiB
      KV gRPC calls: 1
      estimated max memory allocated: 9.7 MiB
      sql cpu time: 44ms
      estimated row count: 1 (100% of the table; stats collected 20 seconds ago)
      table: fact_ventas_boletas@idx_fact_ventas_tiempo_evento  ----------------------  WARNING: the row count estimate is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
      spans: [/2026090100 - /2026093023]

WARNING: the row count estimate on table "fact_ventas_boletas" is inaccurate, consider running 'ANALYZE fact_ventas_boletas'