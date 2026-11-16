-- Esquema operacional de laboratorio. Ejecutar en la base tuboleta.
CREATE TABLE IF NOT EXISTS canales (
  canal_id STRING PRIMARY KEY, nombre STRING NOT NULL, digital_flag BOOL NOT NULL
);
CREATE TABLE IF NOT EXISTS zonas (
  zona_id STRING NOT NULL, nombre_zona STRING NOT NULL, tipo_zona STRING NOT NULL,
  capacidad_zona INT8 NOT NULL, precio_base INT8 NOT NULL,
  valido_desde DATE NOT NULL, valido_hasta DATE NOT NULL, activo BOOL NOT NULL,
  PRIMARY KEY (zona_id, valido_desde)
);
CREATE TABLE IF NOT EXISTS eventos (
  evento_id STRING PRIMARY KEY, nombre_evento STRING NOT NULL, tipo_evento STRING NOT NULL,
  recinto STRING NOT NULL, ciudad STRING NOT NULL, fecha_evento DATE NOT NULL,
  inicio_ventas DATE NOT NULL, aforo_total INT8 NOT NULL, organizador STRING NOT NULL
);
CREATE TABLE IF NOT EXISTS sillas (
  silla_id STRING PRIMARY KEY, zona_id STRING NOT NULL, fila STRING NOT NULL,
  numero INT4 NOT NULL, categoria STRING NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
  usuario_id STRING PRIMARY KEY, segmento STRING NOT NULL, canal_preferido STRING NOT NULL
);
CREATE TABLE IF NOT EXISTS compras_confirmadas (
  compra_id STRING PRIMARY KEY, silla_id STRING NOT NULL, evento_id STRING NOT NULL,
  usuario_id STRING NOT NULL, canal_id STRING NULL, fecha_compra TIMESTAMP NOT NULL,
  precio_pagado INT8 NOT NULL, descuento_aplicado INT8 NOT NULL, tiempo_hasta_pago_seg INT8 NOT NULL,
  CONSTRAINT uq_compra_evento_silla UNIQUE (evento_id, silla_id)
);
CREATE TABLE IF NOT EXISTS intentos_compra (
  intento_id STRING PRIMARY KEY, silla_id STRING NOT NULL, evento_id STRING NOT NULL,
  usuario_id STRING NOT NULL, canal_id STRING NULL, fecha_intento TIMESTAMP NOT NULL,
  resultado STRING NOT NULL, tiempo_en_fila_seg INT8 NOT NULL, compra_id STRING NULL
);
CREATE TABLE IF NOT EXISTS fact_ventas_boletas (
  compra_id STRING PRIMARY KEY, tiempo_sk INT8 NOT NULL, evento_sk INT4 NOT NULL,
  zona_sk INT4 NOT NULL, silla_sk INT4 NOT NULL, usuario_sk INT4 NOT NULL,
  canal_sk INT4 NOT NULL, precio_pagado DECIMAL(14,2) NOT NULL,
  cantidad INT4 NOT NULL DEFAULT 1,
  CONSTRAINT uq_evento_silla_gold UNIQUE (evento_sk, silla_sk)
);
CREATE TABLE IF NOT EXISTS fact_ventas_insert_bench (
  compra_id STRING PRIMARY KEY, tiempo_sk INT8 NOT NULL, evento_sk INT4 NOT NULL,
  zona_sk INT4 NOT NULL, silla_sk INT4 NOT NULL, usuario_sk INT4 NOT NULL,
  canal_sk INT4 NOT NULL, precio_pagado DECIMAL(14,2) NOT NULL,
  cantidad INT4 NOT NULL DEFAULT 1
);
