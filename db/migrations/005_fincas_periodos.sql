-- 005  Fincas y periodos   (persona 4)   O1, O2
--
-- Las dos tablas sobre las que se monta todo el flujo de trabajo.


-- O1. Las tres columnas del medio existen cada una por una condicion:
-- zona por C1, propietario por C8, poligono por C6.
CREATE TABLE fincas (
    id            integer                 GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre        text                    NOT NULL,
    zona          text                    NOT NULL REFERENCES zonas(id),
    propietario   integer                 NOT NULL REFERENCES cuentas(id),

    poligono      geometry(Polygon, 4326) NOT NULL,

    registrada_en timestamptz             NOT NULL DEFAULT now(),

    -- La frontera F3 dice que el poligono se valida con funciones
    -- geoespaciales antes de guardarse. Un poligono que se cruza a si mismo
    -- hace que ST_Intersects devuelva cualquier cosa, y C6 deja de ser
    -- confiable.
    CONSTRAINT poligono_valido CHECK (ST_IsValid(poligono))
);

-- GiST es lo que hace que C6 no recorra la tabla entera en cada emision.
CREATE INDEX fincas_poligono_idx     ON fincas USING GIST (poligono);
CREATE INDEX fincas_zona_idx         ON fincas (zona);
CREATE INDEX fincas_propietario_idx  ON fincas (propietario);


-- O2. Un periodo es una campana de medicion global, no una por finca.
-- Direccion de Certificacion lo abre (Ab) y lo cierra (Cr), y son las unicas
-- dos operaciones que existen sobre el.
CREATE TABLE periodos_medicion (
    id         integer        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- El nombre con el que la gente lo llama: '2026-Q1'. La llave es un
    -- numero, pero nadie quiere ver "periodo 3" en una pantalla.
    etiqueta   text           NOT NULL UNIQUE,

    estado     estado_periodo NOT NULL DEFAULT 'ABIERTO',
    abierto_en timestamptz    NOT NULL DEFAULT now(),
    cerrado_en timestamptz,


    -- El estado y la fecha no pueden contradecirse. C2 y C11 leen estado, y
    -- una fila cerrada sin fecha seria invisible para cualquier auditoria.
    CONSTRAINT cerrado_lleva_fecha
        CHECK ((estado = 'ABIERTO'  AND cerrado_en IS NULL)
            OR (estado = 'CERRADO'  AND cerrado_en IS NOT NULL))
);
