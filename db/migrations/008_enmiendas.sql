-- 008  Enmiendas      (persona 1)   O4
--
-- Lo que reemplaza a modificar una medicion. Si una medicion estaba mal y el
-- periodo ya cerro, el tecnico que la registro pide una enmienda (C11), un
-- verificador la revisa (C4) y Direccion de Certificacion la cierra (C5).
--
-- Tres columnas de persona porque C5 exige tres personas distintas. Si
-- alguien "simplifica" a una sola columna responsable, C5 deja de poder
-- evaluarse.

CREATE TABLE enmiendas (
    id            integer         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    medicion      integer         NOT NULL REFERENCES mediciones(id),

    solicitante   integer         NOT NULL REFERENCES cuentas(id),
    justificacion text            NOT NULL,

    estado        estado_enmienda NOT NULL DEFAULT 'SOLICITADA',

    revisor       integer         REFERENCES cuentas(id),
    revisada_en   timestamptz,

    cerrada_por   integer         REFERENCES cuentas(id),
    cerrada_en    timestamptz,

    solicitada_en timestamptz     NOT NULL DEFAULT now(),


    -- C4 en el motor: quien revisa no puede ser quien pidio.
    CONSTRAINT revisor_distinto_del_solicitante
        CHECK (revisor IS NULL OR revisor <> solicitante),

    -- C5 en el motor: quien cierra no puede ser ninguno de los dos.
    -- Que ademas sea Direccion de Certificacion lo comprueba el PDP.
    CONSTRAINT cierre_de_una_tercera_persona
        CHECK (cerrada_por IS NULL
               OR (cerrada_por <> solicitante
                   AND (revisor IS NULL OR cerrada_por <> revisor))),

    CONSTRAINT cerrada_lleva_las_tres
        CHECK (estado <> 'CERRADA'
               OR (revisor IS NOT NULL AND cerrada_por IS NOT NULL))
);

CREATE INDEX enmiendas_medicion_idx ON enmiendas (medicion);
CREATE INDEX enmiendas_estado_idx   ON enmiendas (estado);
