# Resultados de las consultas analíticas

Generado por `scripts/analyze.py` (2026-10-28 11:16) sobre el esquema en estrella de Gold.

## 1. Ingresos y boletas por evento y mes

*¿Cómo se reparten las ventas de cada evento a lo largo de los meses de su ventana de venta?*

| nombre_evento | anio | mes | mes_nombre | boletas | ingresos |
|---|---|---|---|---|---|
| Concierto Noche Latina | 2026 | 2 | febrero | 13.567 | 1.283.939.000 |
| Concierto Noche Latina | 2026 | 3 | marzo | 13.108 | 1.333.649.000 |
| Concierto Noche Latina | 2026 | 4 | abril | 12.759 | 1.369.809.000 |
| Clásico Paisa Nacional vs Medellín | 2026 | 5 | mayo | 17.058 | 1.641.500.000 |
| Clásico Paisa Nacional vs Medellín | 2026 | 6 | junio | 14.966 | 1.547.518.500 |
| Clásico Paisa Nacional vs Medellín | 2026 | 7 | julio | 11.814 | 1.383.595.800 |
| Festival Sonidos del Valle | 2026 | 6 | junio | 19.426 | 1.906.164.500 |
| Festival Sonidos del Valle | 2026 | 7 | julio | 13.371 | 1.478.479.300 |
| Festival Sonidos del Valle | 2026 | 8 | agosto | 8.778 | 1.039.465.800 |
| Gira Urbana Medellín | 2026 | 7 | julio | 17.024 | 1.746.843.700 |
| Gira Urbana Medellín | 2026 | 8 | agosto | 12.223 | 1.351.182.000 |
| Gira Urbana Medellín | 2026 | 9 | septiembre | 10.304 | 1.210.290.100 |
| Final del Fútbol Colombiano | 2026 | 8 | agosto | 4.998 | 493.055.700 |
| Final del Fútbol Colombiano | 2026 | 9 | septiembre | 22.584 | 2.377.871.200 |
| Final del Fútbol Colombiano | 2026 | 10 | octubre | 14.345 | 1.665.531.700 |

## 2. Ocupación e ingresos por evento y zona

*¿Qué porcentaje de la capacidad de cada zona se vendió en cada evento y cuánto dinero generó?*

| nombre_evento | nombre_zona | capacidad_zona | vendidas | ocupacion_pct | ingresos |
|---|---|---|---|---|---|
| Concierto Noche Latina | Occidental | 12.000 | 10.321 | 86,01 | 1.493.235.000 |
| Concierto Noche Latina | Norte | 14.000 | 12.566 | 89,76 | 1.085.265.000 |
| Concierto Noche Latina | General | 16.000 | 14.032 | 87,70 | 806.172.000 |
| Concierto Noche Latina | VIP | 3.000 | 2.515 | 83,83 | 602.725.000 |
| Clásico Paisa Nacional vs Medellín | Occidental | 12.000 | 11.676 | 97,30 | 1.745.617.300 |
| Clásico Paisa Nacional vs Medellín | Norte | 14.000 | 14.000 | 100,00 | 1.208.074.500 |
| Clásico Paisa Nacional vs Medellín | General | 16.000 | 15.162 | 94,76 | 870.666.000 |
| Clásico Paisa Nacional vs Medellín | VIP | 3.000 | 3.000 | 100,00 | 748.256.500 |
| Festival Sonidos del Valle | Occidental | 12.000 | 11.448 | 95,40 | 1.755.351.100 |
| Festival Sonidos del Valle | Norte | 14.000 | 12.942 | 92,44 | 1.118.173.500 |
| Festival Sonidos del Valle | General | 16.000 | 14.355 | 89,72 | 824.337.000 |
| Festival Sonidos del Valle | VIP | 3.000 | 2.830 | 94,33 | 726.248.000 |
| Gira Urbana Medellín | Occidental | 12.000 | 10.739 | 89,49 | 1.710.689.800 |
| Gira Urbana Medellín | Norte | 14.000 | 12.227 | 87,34 | 1.055.601.000 |
| Gira Urbana Medellín | General | 16.000 | 13.788 | 86,18 | 791.583.000 |
| Gira Urbana Medellín | VIP | 3.000 | 2.797 | 93,23 | 750.442.000 |
| Final del Fútbol Colombiano | Occidental | 12.000 | 11.249 | 93,74 | 1.790.140.100 |
| Final del Fútbol Colombiano | Norte | 14.000 | 12.800 | 91,43 | 1.105.582.500 |
| Final del Fútbol Colombiano | General | 16.000 | 14.975 | 93,59 | 860.166.000 |
| Final del Fútbol Colombiano | VIP | 3.000 | 2.903 | 96,77 | 780.570.000 |

## 3. Volumen, ingresos y ticket promedio por canal

*¿Qué canal vende más y cuánto paga en promedio quien compra por cada uno?*

| canal | boletas | boletas_pct | ingresos | ticket_promedio | descuento_promedio |
|---|---|---|---|---|---|
| app | 99.940 | 48,44 | 9.842.735.200 | 98.486 | 4.313 |
| web | 71.396 | 34,60 | 7.894.226.400 | 110.570 | 4.532 |
| taquilla | 31.935 | 15,48 | 3.769.646.000 | 118.041 | 3.616 |
| DESCONOCIDO | 3.054 | 1,48 | 322.287.700 | 105.530 | 4.254 |

## 4. Distribución por franja horaria y día de la semana

*¿A qué hora y en qué día compra la gente? Boletas por franja horaria, abiertas por día de la semana.*

| franja_horaria | boletas | pct | lunes | martes | miercoles | jueves | viernes | sabado | domingo |
|---|---|---|---|---|---|---|---|---|---|
| madrugada | 8.364 | 4,05 | 788 | 1.630 | 1.411 | 1.210 | 1.229 | 1.058 | 1.038 |
| mañana | 47.635 | 23,09 | 10.034 | 7.583 | 6.759 | 6.547 | 6.585 | 5.067 | 5.060 |
| tarde | 66.834 | 32,39 | 12.653 | 10.708 | 9.745 | 9.548 | 9.528 | 7.384 | 7.268 |
| noche | 83.492 | 40,47 | 17.430 | 14.081 | 12.109 | 11.232 | 10.843 | 9.021 | 8.776 |

## 5a. Embudo de conversión por evento

*De cada 100 intentos de compra (lock de silla), ¿cuántos terminan en compra, abandono o rechazo UNIQUE? ¿Qué porcentaje de las ventas se pagó en el último tramo del TTL?*

| evento | intentos | compras | abandonos | rechazos_unique | conversion_pct | abandono_pct | rechazo_unique_pct | pago_tardio_pct |
|---|---|---|---|---|---|---|---|---|
| Clásico Paisa Nacional vs Medellín | 54.738 | 43.838 | 7.431 | 3.469 | 80,09 | 13,58 | 6,34 | 6,84 |
| Final del Fútbol Colombiano | 52.543 | 41.927 | 7.258 | 3.358 | 79,80 | 13,81 | 6,39 | 6,91 |
| Festival Sonidos del Valle | 52.031 | 41.575 | 7.091 | 3.365 | 79,90 | 13,63 | 6,47 | 6,95 |
| Gira Urbana Medellín | 49.414 | 39.551 | 6.692 | 3.171 | 80,04 | 13,54 | 6,42 | 6,74 |
| Concierto Noche Latina | 49.180 | 39.434 | 6.603 | 3.143 | 80,18 | 13,43 | 6,39 | 6,65 |

## 5b. Embudo de conversión por canal

*Misma lectura del embudo, ahora por canal de venta.*

| canal | intentos | compras | abandonos | rechazos_unique | conversion_pct | abandono_pct | rechazo_unique_pct | pago_tardio_pct |
|---|---|---|---|---|---|---|---|---|
| app | 121.791 | 99.873 | 14.524 | 7.394 | 82,00 | 11,93 | 6,07 | 6,11 |
| web | 95.875 | 71.420 | 18.017 | 6.438 | 74,49 | 18,79 | 6,71 | 7,84 |
| taquilla | 36.358 | 31.911 | 2.010 | 2.437 | 87,77 | 5,53 | 6,70 | 6,77 |
| DESCONOCIDO | 3.882 | 3.121 | 524 | 237 | 80,40 | 13,50 | 6,11 | 6,76 |

## 6. SCD Tipo 2: ingresos VIP por versión de precio

*El 2026-07-01 sube el precio VIP. ¿Cómo cambian boletas, ingresos y descuentos entre las dos versiones?*

| zona_sk | nombre_zona | precio_base | valido_desde | valido_hasta | boletas | ingresos | ticket_promedio | descuento_promedio |
|---|---|---|---|---|---|---|---|---|
| 1 | VIP | 250.000 | 2026-01-01 | 2026-06-30 | 5.657 | 1.353.387.500 | 239.241 | 10.759 |
| 2 | VIP | 280.000 | 2026-07-01 | 9999-12-31 | 8.388 | 2.254.854.000 | 268.819 | 11.181 |

## 7. Tiempo hasta el pago por zona (promedio, mediana y p95)

*¿Cuánto tarda en pagar cada zona desde que bloquea la silla (TTL de 600 s)? ¿Cuántos pagan al límite?*

| nombre_zona | boletas | promedio_seg | mediana_seg | p95_seg | pago_tardio_pct |
|---|---|---|---|---|---|
| VIP | 14.045 | 255,50 | 219,00 | 528,00 | 8,70 |
| Occidental | 55.433 | 213,80 | 170,00 | 515,00 | 7,12 |
| General | 72.312 | 192,00 | 147,00 | 514,00 | 7,05 |
| Norte | 64.535 | 175,90 | 134,00 | 499,00 | 5,91 |

## 8. Ventas en el día de apertura

*¿Qué parte de las boletas de cada evento se vende el primer día y en los tres primeros días de venta?*

| nombre_evento | inicio_ventas | boletas | primer_dia | primer_dia_pct | tres_dias_pct | ingresos_primer_dia |
|---|---|---|---|---|---|---|
| Concierto Noche Latina | 2026-02-23 | 39.434 | 4.484 | 11,37 | 24,46 | 417.488.000 |
| Clásico Paisa Nacional vs Medellín | 2026-05-25 | 43.838 | 5.227 | 11,92 | 25,82 | 491.537.500 |
| Festival Sonidos del Valle | 2026-06-15 | 41.575 | 4.637 | 11,15 | 24,43 | 445.993.000 |
| Gira Urbana Medellín | 2026-07-20 | 39.551 | 4.505 | 11,39 | 24,85 | 450.512.500 |
| Final del Fútbol Colombiano | 2026-08-31 | 41.927 | 4.998 | 11,92 | 25,98 | 493.055.700 |

## 9. Ingreso potencial perdido por abandono, por zona

*Cada abandono libera una silla que pudo venderse. ¿Cuánto dinero de lista se asocia a esos abandonos? Es una cota superior: parte de esas sillas se vendió después a otro usuario.*

| nombre_zona | intentos | abandonos | abandono_pct | ingreso_potencial_perdido |
|---|---|---|---|---|
| Occidental | 70.907 | 10.955 | 15,45 | 1.741.395.000 |
| VIP | 18.704 | 3.473 | 18,57 | 931.250.000 |
| Norte | 79.460 | 9.882 | 12,44 | 889.380.000 |
| General | 88.835 | 10.765 | 12,12 | 645.900.000 |
