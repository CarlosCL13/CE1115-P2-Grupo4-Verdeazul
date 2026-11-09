-- 009  Certificados   (persona 5)   O5
--
-- Un verificador emite si se cumple C6, que es la condicion mas cara del
-- sistema: la medicion aprobada, no registrada por el, y ningun certificado
-- vigente con poligono que se superponga.

CREATE TABLE certificados (
    id               integer                 GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    medicion         integer                 NOT NULL REFERENCES mediciones(id),

    -- Copia, no referencia a la finca. Si alguien corrige el poligono de una
    -- finca el ano que viene, un certificado ya emitido no puede cambiar: va
    -- firmado, y cambiarlo rompe la firma.
    poligono         geometry(Polygon, 4326) NOT NULL,

    toneladas        numeric(12,3)           NOT NULL,
    estado           estado_certificado      NOT NULL DEFAULT 'VIGENTE',

    emitido_por      integer                 NOT NULL REFERENCES cuentas(id),
    emitido_en       timestamptz             NOT NULL DEFAULT now(),

    -- §2.2: la firma con la clave privada, y la clave publica viajando dentro
    -- del documento para que un comprador en otro pais pueda verificarlo sin
    -- acceso a la base de Verdeazul.
    firma            bytea                   NOT NULL,
    llave_publica    text                    NOT NULL,

    motivo_anulacion text,
    anulado_en       timestamptz,

    CONSTRAINT toneladas_positivas CHECK (toneladas > 0),
    CONSTRAINT poligono_valido CHECK (ST_IsValid(poligono)),

    CONSTRAINT anulado_lleva_motivo
        CHECK (estado <> 'ANULADO'
               OR (motivo_anulacion IS NOT NULL AND anulado_en IS NOT NULL))
);

-- Indice parcial: C6 solo compara contra los vigentes, y un anulado deja de
-- bloquear emisiones nuevas.
CREATE INDEX certificados_poligono_idx
    ON certificados USING GIST (poligono)
    WHERE estado = 'VIGENTE';

-- Una medicion no puede tener dos certificados vigentes a la vez.
CREATE UNIQUE INDEX certificados_medicion_vigente_idx
    ON certificados (medicion)
    WHERE estado = 'VIGENTE';

CREATE INDEX certificados_emisor_idx ON certificados (emitido_por);

-- NOTA para quien implemente la emision: el indice GiST acelera la busqueda
-- de traslapes, pero no evita que dos verificadores emitan al mismo tiempo y
-- los dos vean "ningun traslape" antes de que el otro confirme. La
-- revalidacion va dentro de la transaccion, con pg_advisory_xact_lock.
