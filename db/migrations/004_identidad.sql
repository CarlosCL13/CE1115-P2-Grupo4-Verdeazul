-- 004  Identidad      (persona 2)   O10, O6, y la tabla que exige C10
--
-- Todo lo que cuelga de una cuenta: con que entra, que sesion tiene abierta,
-- sus datos personales, y las solicitudes de cambio de rol.

-- O10. Tabla aparte de cuentas a proposito: en la matriz, O10 es el unico
-- objeto donde TODOS los roles tienen M y NADIE tiene L. Cada quien cambia su
-- contrasena y nadie puede leerla, ni Direccion General. Mezclada con cuentas
-- eso no se puede imponer, porque a cuentas si hay que leerla.
CREATE TABLE credenciales (
    cuenta       integer     PRIMARY KEY REFERENCES cuentas(id),

    -- Argon2id con sal, §2.3.1. Un hash rapido pierde medio criterio.
    hash_argon2   text        NOT NULL,

    -- Cifrado, no en claro: quien lea la base no puede generar codigos.
    totp_secreto bytea,
    totp_activo  boolean     NOT NULL DEFAULT false,

    cambiada_en  timestamptz NOT NULL DEFAULT now()
);

-- La sesion vive en la base, como prometio la Parte 1, para poder invalidarla
-- al instante en vez de esperar a que venza un token firmado.
CREATE TABLE sesiones (
    id                integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- El hash del token, nunca el token. El id es secuencial y no pasa nada:
    -- el secreto es esta columna, no la llave primaria.
    token_hash        text        NOT NULL UNIQUE,

    cuenta            integer     NOT NULL REFERENCES cuentas(id),
    segundo_factor_ok boolean     NOT NULL DEFAULT false,
    creada_en         timestamptz NOT NULL DEFAULT now(),
    expira_en         timestamptz NOT NULL,
    cerrada_en        timestamptz,

    CONSTRAINT vence_despues_de_crearse CHECK (expira_en > creada_en)
);

-- Para cerrar todas las sesiones de alguien cuando se bloquea la cuenta.
CREATE INDEX sesiones_abiertas_idx ON sesiones (cuenta)
    WHERE cerrada_en IS NULL;

-- O6. Lo mas delicado que guarda el sistema. LG-05 exige cifrar cedula y
-- telefono.
CREATE TABLE datos_personales (
    cuenta           integer     PRIMARY KEY REFERENCES cuentas(id),
    nombre_completo  text        NOT NULL,

    cedula_cifrada   bytea       NOT NULL,

    -- HMAC con llave, no hash simple. Una cedula de Costa Rica son nueve
    -- digitos: un diccionario de todas ellas se calcula en minutos. Con HMAC
    -- la llave no esta en la base, asi que un volcado solo no sirve.
    cedula_busqueda  bytea       NOT NULL UNIQUE,

    telefono_cifrado bytea,
    actualizado_en   timestamptz NOT NULL DEFAULT now()
);

-- No es un objeto de la matriz, pero sin esta tabla C10 no se puede evaluar.
-- La aprobacion tiene que existir ANTES de que la cuenta cambie, asi que no
-- cabe como columna en cuentas: esa fila todavia no refleja el cambio.
CREATE TABLE solicitudes_rol (
    id              integer          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cuenta_afectada integer          NOT NULL REFERENCES cuentas(id),
    rol_solicitado  rol_sujeto       NOT NULL,
    solicitante     integer          NOT NULL REFERENCES cuentas(id),
    estado          estado_solicitud NOT NULL DEFAULT 'PENDIENTE',
    aprobador       integer          REFERENCES cuentas(id),
    aprobada_en     timestamptz,
    solicitada_en   timestamptz      NOT NULL DEFAULT now(),

    -- La mitad de C10 escrita en el motor: quien aprueba no puede ser quien
    -- pide. El resto de C10 (que el aprobador sea Direccion General) lo
    -- comprueba el PDP, porque depende del rol y no de esta fila.
    CONSTRAINT aprobador_distinto_del_solicitante
        CHECK (aprobador IS NULL OR aprobador <> solicitante),

    CONSTRAINT aprobada_lleva_aprobador
        CHECK (estado <> 'APROBADA' OR aprobador IS NOT NULL)
);

CREATE INDEX solicitudes_rol_pendientes_idx ON solicitudes_rol (cuenta_afectada)
    WHERE estado = 'PENDIENTE';
