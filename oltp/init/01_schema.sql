CREATE DATABASE IF NOT EXISTS tuboleta;
USE tuboleta;

CREATE TABLE IF NOT EXISTS fact_ventas_boletas (
    compra_id STRING PRIMARY KEY,
    tiempo_sk INT8 NOT NULL,
    evento_sk INT4 NOT NULL,
    zona_sk INT4 NOT NULL,
    silla_sk INT4 NOT NULL,
    usuario_sk INT4 NOT NULL,
    canal_sk INT4 NOT NULL,
    precio_pagado DECIMAL(14,2) NOT NULL,
    cantidad INT4 NOT NULL DEFAULT 1,
    CONSTRAINT uq_evento_silla UNIQUE (evento_sk, silla_sk)
);

CREATE TABLE IF NOT EXISTS fact_ventas_insert_bench (
    compra_id STRING PRIMARY KEY,
    tiempo_sk INT8 NOT NULL,
    evento_sk INT4 NOT NULL,
    zona_sk INT4 NOT NULL,
    silla_sk INT4 NOT NULL,
    usuario_sk INT4 NOT NULL,
    canal_sk INT4 NOT NULL,
    precio_pagado DECIMAL(14,2) NOT NULL,
    cantidad INT4 NOT NULL DEFAULT 1
);
