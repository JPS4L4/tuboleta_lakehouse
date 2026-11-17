# Benchmark: OLTP vs columnar

Misma agregación lógica en tres motores: **boletas e ingresos por evento x zona x mes**.

- Ventas confirmadas: 208.236
- Grupos devueltos (evento x zona x mes): 60
- Corridas por motor: 5 (más un calentamiento previo); se reporta la mediana.
- El tiempo de carga no se incluye: solo cuenta ejecutar la consulta y traer el resultado.
- Los tres motores devuelven exactamente las mismas cifras (el pipeline lo verifica con una aserción).
- Máquina: Windows-11-10.0.26100-SP0, 16 hilos lógicos; Python 3.13.14, DuckDB 2.0.0, SQLite 3.50.4.
- Ejecutado: 2026-11-16 23:20.

| Motor | Fuente | Mediana (ms) | Rango (ms) | Mejora vs (a) |
|---|---|---:|---:|---:|
| (a) SQLite, almacén por filas (OLTP-like) | Silver normalizado + índices | 444.01 | 432.67 - 455.59 | 1.0x |
| (b) DuckDB sobre Bronze crudo | Parquet sucio, limpieza en la consulta | 169.22 | 164.94 - 190.59 | 2.6x |
| (c) DuckDB sobre Gold (estrella) | Parquet columnar modelado | 16.97 | 15.13 - 17.07 | 26.2x |

## Cómo leer el resultado

- **(a)** es un almacén por filas con índices típicos de OLTP (únicos por clave, índices de unión). Está pensado para buscar y modificar filas puntuales; aquí se le pide recorrer todas las ventas y unir cuatro tablas.
- **(b)** lee Parquet columnar sin modelar, por lo que la consulta debe limpiar al vuelo; muestra cuánto aporta el formato columnar sin el modelado.
- **(c)** lee solo las columnas necesarias de la tabla de hechos y de dimensiones pequeñas con claves enteras.
- DuckDB usa varios hilos y SQLite solo uno; parte de la diferencia viene de ahí y no solo del formato de almacenamiento.
- Con volúmenes menores de 100.000 filas las diferencias se reducen; este conjunto supera las 200.000 ventas.
