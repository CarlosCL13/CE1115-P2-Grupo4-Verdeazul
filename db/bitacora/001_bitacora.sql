-- 001  Bitacora de auditoria (verdeazul-bitacora)
--
--     python db/migrar.py bitacora
--
-- Se aplica como dueno de ESTE proyecto, que es otro distinto al de la base
-- principal. Vivir aparte es la frontera F6: quien comprometa la aplicacion
-- no alcanza el rastro.
--
-- Aqui no hay app_rw ni app_migrate, y tampoco PostGIS: esta base guarda
-- texto. Sin contrasenas, igual que la 001 de la otra base.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'log_writer') THEN
    CREATE ROLE log_writer NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'log_reader') THEN
    CREATE ROLE log_reader NOLOGIN;
  END IF;
END
$$;

REVOKE ALL ON SCHEMA   public FROM PUBLIC;
REVOKE ALL ON DATABASE neondb FROM PUBLIC;

GRANT CONNECT ON DATABASE neondb TO log_writer, log_reader;
GRANT USAGE   ON SCHEMA   public TO log_writer, log_reader;


-- O11. Los campos estan congelados en contracts/03-evento-bitacora.md, porque
-- los cinco frentes emiten eventos y uno solo los guarda.
CREATE TABLE IF NOT EXISTS eventos (
    -- La cadena HMAC necesita un orden total. momento no sirve: dos eventos
    -- pueden caer en el mismo microsegundo y entonces no se sabe cual eslabon
    -- va antes.
    secuencia   bigserial   PRIMARY KEY,

    id          uuid        NOT NULL UNIQUE,

    -- La pone esta base, nunca el cliente. Quien controle la aplicacion no
    -- puede fechar un evento en el pasado.
    momento     timestamptz NOT NULL DEFAULT now(),

    accion      text        NOT NULL,
    sujeto      text        NOT NULL,
    objeto      text        NOT NULL,
    resultado   text        NOT NULL,
    motivo      text,

    -- Contexto, sin datos personales ni secretos. Un evento es lo que paso,
    -- no una copia de los datos.
    detalle     jsonb,

    -- HMAC de este evento mas el eslabon del anterior. Alterar uno rompe la
    -- cadena de ahi en adelante y se detecta al recomputarla.
    eslabon     text        NOT NULL,

    CONSTRAINT resultado_valido
      CHECK (resultado IN ('PERMITIDO', 'DENEGADO')),

    -- El contrato pide motivo si fue denegado. Escrito aqui deja de depender
    -- de que cada quien se acuerde.
    CONSTRAINT denegado_lleva_motivo
      CHECK (resultado = 'PERMITIDO' OR motivo IS NOT NULL)
);

-- Las consultas de O11 filtran por ventana de fechas (C7 del auditor), por
-- quien actuo y por sobre que objeto.
CREATE INDEX IF NOT EXISTS eventos_momento_idx ON eventos (momento DESC);
CREATE INDEX IF NOT EXISTS eventos_sujeto_idx  ON eventos (sujeto, momento DESC);
CREATE INDEX IF NOT EXISTS eventos_objeto_idx  ON eventos (objeto, momento DESC);


-- El transmisor inserta y nada mas. Sin UPDATE ni DELETE, el solo-anexar de
-- BI-01 lo impone el motor y no la disciplina de cinco personas.
GRANT INSERT ON TABLE eventos TO log_writer;
GRANT USAGE  ON SEQUENCE eventos_secuencia_seq TO log_writer;

-- log_writer tampoco lee. No le hace falta, porque el eslabon anterior lo
-- lleva el en la bandeja de salida, y no darselo significa que comprometer el
-- transmisor no entrega el historial.

-- La API lee para las celdas L y X de O11 (DG, DC, PA y AE).
GRANT SELECT ON TABLE eventos TO log_reader;
