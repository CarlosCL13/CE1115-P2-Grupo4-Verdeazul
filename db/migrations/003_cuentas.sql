-- 003  Cuentas        (persona 2)   O9
--
-- La tabla central: once de las quince apuntan aqui. Hasta que exista, nadie
-- puede crear una tabla con llave foranea hacia ella.
--
-- Un solo rol por cuenta. La matriz nunca da dos, y si los diera se rompe el
-- razonamiento de separacion de funciones: C5 exige tres personas distintas,
-- y eso se vuelve ambiguo si una persona lleva dos sombreros.
--
-- Sobre el id: GENERATED ALWAYS AS IDENTITY, no serial. La secuencia
-- pertenece a la columna, asi que con el permiso de INSERT sobre la tabla
-- alcanza y no hay que dar GRANT USAGE sobre una secuencia aparte. Y ALWAYS
-- significa que la aplicacion no puede fijar el id ni por error. Los datos de
-- prueba que necesiten ids fijos usan OVERRIDING SYSTEM VALUE.

CREATE TABLE cuentas (
    id                integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario           text        NOT NULL UNIQUE,
    nombre            text        NOT NULL,
    rol               rol_sujeto  NOT NULL,
    activa            boolean     NOT NULL DEFAULT true,

    -- Las mueve el inicio de sesion, no una pantalla. El bloqueo tras varios
    -- intentos es parte de §2.3.1.
    intentos_fallidos integer     NOT NULL DEFAULT 0,
    bloqueada_hasta   timestamptz,

    creada_en         timestamptz NOT NULL DEFAULT now(),

    -- Los ocho de la matriz, ni uno mas. Un rol inventado por un bug no entra
    -- a la base, y el motor de autorizacion no tiene que defenderse de el.

    CONSTRAINT intentos_no_negativos CHECK (intentos_fallidos >= 0)
);

CREATE INDEX cuentas_rol_idx ON cuentas (rol);
