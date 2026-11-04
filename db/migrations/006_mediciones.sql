-- 006  Mediciones     (persona 4)   O3
--
-- La tabla con la regla mas rara del sistema: NINGUN rol tiene M sobre O3.
-- Aprobar y devolver cambian el estado, pero el valor medido no lo modifica
-- nadie. Toda correccion posterior pasa por una enmienda (O4), que involucra
-- tres personas distintas.

CREATE TABLE mediciones (
    id                integer         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    finca             integer         NOT NULL REFERENCES fincas(id),
    periodo           integer         NOT NULL REFERENCES periodos_medicion(id),
    autor             integer         NOT NULL REFERENCES cuentas(id),

    biomasa_toneladas numeric(12,3)   NOT NULL,

    estado            estado_medicion NOT NULL DEFAULT 'REGISTRADA',
    revisada_por      integer         REFERENCES cuentas(id),
    revisada_en       timestamptz,
    motivo_devolucion text,

    registrada_en     timestamptz     NOT NULL DEFAULT now(),

    CONSTRAINT biomasa_positiva CHECK (biomasa_toneladas > 0),

    -- La mitad de C3 escrita en el motor: quien registro no puede aprobar.
    -- La otra mitad (que no haya registrado otra medicion de esa finca en ese
    -- periodo) la comprueba el PDP, porque mira otras filas.
    CONSTRAINT revisor_distinto_del_autor
        CHECK (revisada_por IS NULL OR revisada_por <> autor),

    CONSTRAINT devuelta_lleva_motivo
        CHECK (estado <> 'DEVUELTA' OR motivo_devolucion IS NOT NULL),

    CONSTRAINT revisada_lleva_revisor
        CHECK (estado = 'REGISTRADA' OR revisada_por IS NOT NULL)
);

CREATE INDEX mediciones_finca_idx   ON mediciones (finca, periodo);
CREATE INDEX mediciones_autor_idx   ON mediciones (autor);
CREATE INDEX mediciones_estado_idx  ON mediciones (estado);

-- ---------------------------------------------------------------------------
-- "Ningun rol tiene M en O3", impuesto por el motor
-- ---------------------------------------------------------------------------
-- Los privilegios por omision de la 001 le dieron a app_rw UPDATE sobre toda
-- la tabla. Aqui se lo quitamos y se lo devolvemos solo sobre las columnas que
-- cambian al aprobar o devolver.
--
-- Resultado: ni un bug ni una inyeccion SQL pueden alterar biomasa_toneladas,
-- porque la conexion con la que corre la aplicacion no tiene el permiso.

REVOKE UPDATE ON mediciones FROM app_rw;

GRANT UPDATE (estado, revisada_por, revisada_en, motivo_devolucion)
    ON mediciones TO app_rw;
