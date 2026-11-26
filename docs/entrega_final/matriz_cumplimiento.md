# Matriz de cumplimiento — Entrega final

Esta matriz resume el estado verificable de la plantilla oficial. La etiqueta **pendiente local** indica una acción que requiere ejecutar o comprobar el proyecto en el equipo de entrega. Las ejecuciones locales de M4 y del pipeline se completaron en la corrida final del 26-11-2026.

| Requisito de la plantilla | Estado | Evidencia / acción |
|---|---|---|
| Resumen ejecutivo | Cubierto | `docs/informe_final.md` |
| Contexto, dominio y cargas | Cubierto | `docs/entrega_final/M1_contexto_requisitos.md` |
| Requisitos no funcionales y CAP | Cubierto con alcance declarado | M1 e informe principal; no afirmar SLA productivo no medido |
| Diagrama general | Cubierto | `arquitectura_general.svg` |
| Persistencia políglota | Cubierto con limitación | CockroachDB implementado; DuckDB/Parquet analíticos; Redis conceptual, no desplegado |
| Bronze / Silver / Gold | Cubierto | Informe principal y pipeline |
| Integración entre capas | Cubierto con limitación | Batch manual; no CDC/streaming; latencia igual a duración de corrida |
| Estructura y ejecución | Cubierto | `complemento_documental.md`, README |
| Cinco consultas SQL completas | Cubierto documentalmente | `consultas_sql_resultados.md`; validar ejecución local antes de entrega |
| Benchmark OLTP vs OLAP | Parcial / aclarado | SQLite vs DuckDB es OLAP-like; no es CockroachDB vs DuckDB |
| Dashboard | No implementado / N.A. | Declarado explícitamente; sin capturas ni KPIs ficticios |
| Diagnóstico y planes M4 | Cubierto | `docs/taller4/planes/` y documento M4 |
| Mediana y comparaciones M4 | Cubierto (corrida final 26-11-2026) | M4; conservar protocolos distintos por experimento |
| Min, max y desviación estándar | Cubierto (corrida final 26-11-2026) | Seis CSV en `docs/taller4/` (`mediciones_crudas_*.csv`, `estadisticas_*.csv`); tablas consolidadas en M4, informe final e informe del Taller 4 |
| Lecciones aprendidas | Cubierto | `complemento_documental.md` |
| Trazabilidad M1 → M4 | Cubierto | `complemento_documental.md` |
| Anexos | Cubierto con verificación final | Rutas listadas en complemento documental |
| `python main.py` sin errores | Cubierto (26-11-2026 16:40, `USE_SYNTHETIC=false`, 6,92 s) | Salida registrada en `docs/reporte_calidad_silver.txt` y `docs/taller4/ejecuciones_pipeline.md` |
| PDF final y límite de páginas | PDF regenerado el 26-11-2026 con las cifras finales: `informe_final.pdf` tiene 15 páginas (A4) e `informe_taller4.pdf` 9; la plantilla pide 20–30 páginas sin anexos, comprobar si aplica | `docs/informe_final.pdf` y `docs/taller4/informe_taller4.pdf` |
| Acceso docente al repositorio | Pendiente de confirmar | Confirmar repositorio público o compartir acceso |

## Orden mínimo antes de entregar

1. ~~Ejecutar `python main.py` en el equipo que se usará para la entrega.~~ Hecho el 26-11-2026.
2. ~~Ejecutar los laboratorios de estadísticas M4 y guardar los CSV.~~ Hecho el 26-11-2026; los estadísticos salen de los CSV.
3. ~~Regenerar el PDF final desde el informe actualizado.~~ Hecho (15 páginas); la plantilla pide 20–30 páginas sin anexos, verificar si ese límite aplica.
4. Abrir el PDF, revisar diagramas, tablas, saltos de página y enlaces.
5. Verificar el contenido del ZIP final y confirmar que el docente tenga acceso al repositorio.
