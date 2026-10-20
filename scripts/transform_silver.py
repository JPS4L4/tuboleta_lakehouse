"""Paso 3: Bronze -> Silver.

Limpieza **técnica** únicamente (sin reglas de negocio ni modelado):
  * Tipos: fechas como fecha/fecha-hora, cantidades numéricas.
  * Espacios sobrantes en los IDs (`str.strip`).
  * Filas sin clave de negocio: se descartan.
  * Duplicados por clave de negocio: se conserva la primera fila.
  * Nulos: `canal_id` nulo pasa a 'DESCONOCIDO'.

Para cada tabla se toma el archivo Bronze más reciente, se escribe
`lakehouse/silver/{tabla}_silver.parquet` (se sobrescribe) y se genera el
reporte de calidad en `docs/reporte_calidad_silver.txt`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from scripts import config

FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"
COLUMNAS_TRAZA = ["_extraido_en", "_fuente"]


@dataclass(frozen=True)
class EspecTabla:
    """Reglas de limpieza técnica de una tabla."""

    ids: tuple[str, ...]  # columnas a las que se les quitan espacios
    obligatorias: tuple[str, ...]  # si alguna es nula, la fila se descarta
    unica: tuple[str, ...]  # clave de negocio para quitar duplicados
    fechas_hora: tuple[str, ...] = ()
    fechas_dia: tuple[str, ...] = ()
    numericas: tuple[str, ...] = ()
    nulos: dict[str, str] = field(default_factory=dict)  # columna -> valor por defecto
    col_rango: str | None = None  # columna para reportar el rango de fechas
    col_suma: str | None = None  # columna monetaria para reportar la suma


ESPECIFICACIONES: dict[str, EspecTabla] = {
    "canales": EspecTabla(ids=("canal_id",), obligatorias=("canal_id",), unica=("canal_id",)),
    "zonas": EspecTabla(
        ids=("zona_id",), obligatorias=("zona_id", "valido_desde"), unica=("zona_id", "valido_desde"),
        fechas_dia=("valido_desde", "valido_hasta"), numericas=("capacidad_zona", "precio_base"),
        col_rango="valido_desde"),
    "eventos": EspecTabla(
        ids=("evento_id",), obligatorias=("evento_id",), unica=("evento_id",),
        fechas_dia=("fecha_evento", "inicio_ventas"), numericas=("aforo_total",), col_rango="fecha_evento"),
    "sillas": EspecTabla(
        ids=("silla_id", "zona_id"), obligatorias=("silla_id",), unica=("silla_id",), numericas=("numero",)),
    "usuarios": EspecTabla(ids=("usuario_id",), obligatorias=("usuario_id",), unica=("usuario_id",)),
    "compras_confirmadas": EspecTabla(
        ids=("compra_id", "silla_id", "evento_id", "usuario_id", "canal_id"),
        obligatorias=("compra_id", "silla_id", "evento_id", "fecha_compra"), unica=("compra_id",),
        fechas_hora=("fecha_compra",),
        numericas=("precio_pagado", "descuento_aplicado", "tiempo_hasta_pago_seg"),
        nulos={"canal_id": "DESCONOCIDO"}, col_rango="fecha_compra", col_suma="precio_pagado"),
    "intentos_compra": EspecTabla(
        ids=("intento_id", "silla_id", "evento_id", "usuario_id", "canal_id", "compra_id"),
        obligatorias=("intento_id", "silla_id", "evento_id", "fecha_intento"), unica=("intento_id",),
        fechas_hora=("fecha_intento",), numericas=("tiempo_en_fila_seg",),
        nulos={"canal_id": "DESCONOCIDO"}, col_rango="fecha_intento"),
}


def archivo_bronze_mas_reciente(tabla: str) -> Path:
    """Devuelve el archivo `{tabla}_{YYYYMMDD_HHMM}.parquet` más reciente de Bronze."""
    patron = re.compile(rf"^{re.escape(tabla)}_\d{{8}}_\d{{4}}\.parquet$")
    candidatos = sorted(p for p in config.BRONZE.glob(f"{tabla}_*.parquet") if patron.match(p.name))
    if not candidatos:
        raise FileNotFoundError(f"No hay archivos Bronze de '{tabla}'. Ejecuta primero la extracción.")
    return candidatos[-1]


def _a_fecha(valor: object) -> date | None:
    """Convierte un texto ISO (o fecha) a `datetime.date`; admite 9999-12-31."""
    return None if pd.isna(valor) else date.fromisoformat(str(valor)[:10])


def _convertir_tipos(df: pd.DataFrame, espec: EspecTabla) -> pd.DataFrame:
    """Aplica los tipos correctos: fechas y números."""
    df = df.copy()
    for col in espec.fechas_hora:
        df[col] = pd.to_datetime(df[col], format=FORMATO_FECHA_HORA, errors="coerce")
    for col in espec.fechas_dia:
        df[col] = df[col].map(_a_fecha)
    for col in espec.numericas:
        serie = pd.to_numeric(df[col], errors="coerce")
        df[col] = serie.astype("int64") if serie.notna().all() else serie
    return df


def limpiar_tabla(bronze: pd.DataFrame, espec: EspecTabla) -> tuple[pd.DataFrame, dict[str, int]]:
    """Limpia una tabla y devuelve el resultado con sus contadores de calidad."""
    df = bronze.drop(columns=COLUMNAS_TRAZA, errors="ignore")
    df = _convertir_tipos(df, espec)
    for col in espec.ids:
        df[col] = df[col].str.strip()

    antes = len(df)
    df = df.dropna(subset=list(espec.obligatorias))
    sin_clave = antes - len(df)

    antes = len(df)
    df = df.drop_duplicates(subset=list(espec.unica), keep="first")
    duplicados = antes - len(df)

    nulos_resueltos = 0
    for col, valor in espec.nulos.items():
        nulos_resueltos += int(df[col].isna().sum())
        df[col] = df[col].fillna(valor)

    stats = {"bronze": len(bronze), "silver": len(df), "sin_clave": sin_clave,
             "duplicados": duplicados, "nulos_resueltos": nulos_resueltos}
    return df.reset_index(drop=True), stats


def _miles(numero: int | float) -> str:
    """Formatea con punto como separador de miles (estilo colombiano)."""
    return f"{numero:,.0f}".replace(",", ".")


def _bloque_reporte(tabla: str, archivo: str, espec: EspecTabla, bronze: pd.DataFrame,
                    silver: pd.DataFrame, stats: dict[str, int]) -> list[str]:
    """Arma las líneas del reporte de calidad de una tabla."""
    retenido = 100 * stats["silver"] / stats["bronze"] if stats["bronze"] else 0.0
    detalle_nulos = ", ".join(f"{c} -> {v}" for c, v in espec.nulos.items())
    lineas = [
        f"Tabla: {tabla}",
        f"  Archivo Bronze:        {archivo}",
        f"  Filas Bronze:          {_miles(stats['bronze'])}",
        f"  Filas Silver:          {_miles(stats['silver'])}",
        f"  % retenido:            {retenido:.2f} %",
        f"  Duplicados eliminados: {_miles(stats['duplicados'])}",
        f"  Descartadas sin clave: {_miles(stats['sin_clave'])}",
        f"  Nulos resueltos:       {_miles(stats['nulos_resueltos'])}" + (f" ({detalle_nulos})" if detalle_nulos else ""),
    ]
    if espec.col_rango:
        lineas.append(f"  Rango de {espec.col_rango}: {silver[espec.col_rango].min()} a {silver[espec.col_rango].max()}")
    if espec.col_suma:
        suma_bronze = pd.to_numeric(bronze[espec.col_suma], errors="coerce").sum()
        suma_silver = silver[espec.col_suma].sum()
        lineas.append(f"  Suma de {espec.col_suma}: Bronze {_miles(suma_bronze)} | Silver {_miles(suma_silver)} COP")
    return lineas + [""]


def escribir_reporte(lineas: list[str]) -> Path:
    """Imprime el reporte y lo guarda en docs/reporte_calidad_silver.txt."""
    config.DOCS.mkdir(parents=True, exist_ok=True)
    destino = config.DOCS / "reporte_calidad_silver.txt"
    texto = "\n".join(lineas)
    destino.write_text(texto, encoding="utf-8", newline="\n")
    print(texto)
    return destino


def ejecutar() -> dict[str, int]:
    """Convierte todas las tablas de Bronze a Silver y genera el reporte de calidad."""
    config.SILVER.mkdir(parents=True, exist_ok=True)
    reporte = ["REPORTE DE CALIDAD - CAPA SILVER", f"Generado: {datetime.now():%Y-%m-%d %H:%M}", "=" * 60, ""]
    filas_silver = {}
    for tabla, espec in ESPECIFICACIONES.items():
        archivo = archivo_bronze_mas_reciente(tabla)
        bronze = pd.read_parquet(archivo)
        silver, stats = limpiar_tabla(bronze, espec)
        silver.to_parquet(config.SILVER / f"{tabla}_silver.parquet", index=False)
        filas_silver[tabla] = len(silver)
        reporte += _bloque_reporte(tabla, archivo.name, espec, bronze, silver, stats)
    escribir_reporte(reporte)
    return filas_silver


if __name__ == "__main__":
    ejecutar()
