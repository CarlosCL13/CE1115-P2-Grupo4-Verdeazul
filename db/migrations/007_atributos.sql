-- 007  Atributos de autorizacion   (persona 1)   O7, O8, y la tabla de C7
--
-- Estas tres no hacen nada por si solas. Son las que el motor consulta para
-- decidir, y entre las tres gobiernan veintiuna celdas de la matriz.


-- O8. "Este verificador trabaja en esta zona hasta esta fecha".
-- Una persona tiene varias filas, y de ahi sale el plural de sujeto.zonas.
-- Es toda la base de C1.
CREATE TABLE asignaciones_zona (
    id          integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sujeto      integer     NOT NULL REFERENCES cuentas(id),
    zona        text        NOT NULL REFERENCES zonas(id),
    vence       date        NOT NULL,
    asignada_en timestamptz NOT NULL DEFAULT now(),
    revocada_en timestamptz
);

-- La misma persona no puede tener dos asignaciones vigentes a la misma zona.
-- Revocada si, porque el historial se conserva.
CREATE UNIQUE INDEX asignaciones_vigentes_idx
    ON asignaciones_zona (sujeto, zona)
    WHERE revocada_en IS NULL;

-- Por donde pregunta C1: dame las zonas vigentes de este sujeto.
CREATE INDEX asignaciones_sujeto_idx ON asignaciones_zona (sujeto)
    WHERE revocada_en IS NULL;


-- O7. "El dueno de esta finca autoriza a este tercero hasta esta fecha".
-- Es lo unico que le da a un Tercero Autorizado permiso de ver un
-- certificado, y es toda la base de C9.
CREATE TABLE consentimientos (
    id           integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    finca        integer     NOT NULL REFERENCES fincas(id),
    tercero      integer     NOT NULL REFERENCES cuentas(id),
    otorgado_por integer     NOT NULL REFERENCES cuentas(id),
    vence        date        NOT NULL,
    otorgado_en  timestamptz NOT NULL DEFAULT now(),
    revocado_en  timestamptz
);

CREATE INDEX consentimientos_tercero_idx ON consentimientos (tercero)
    WHERE revocado_en IS NULL;
CREATE INDEX consentimientos_finca_idx   ON consentimientos (finca);


-- No es un objeto de la matriz, pero sin esta tabla C7 no se puede evaluar y
-- las doce celdas del auditor externo quedan sin implementar.
--
-- Fuera de la ventana el permiso no se suspende, deja de existir: si no hay
-- fila que cubra hoy, el auditor no tiene ningun permiso sobre nada.
CREATE TABLE ventanas_auditoria (
    id        integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auditor   integer     NOT NULL REFERENCES cuentas(id),
    inicio    date        NOT NULL,
    fin       date        NOT NULL,
    alcance   text,
    creada_en timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ventana_coherente CHECK (fin >= inicio)
);

CREATE INDEX ventanas_auditor_idx ON ventanas_auditoria (auditor, inicio, fin);

-- PENDIENTE: la matriz no dice quien crea una ventana de auditoria, porque no
-- es un objeto. Lo decidimos nosotros (Direccion General) y va anotado como
-- desviacion respecto de la Parte 1.
