-- 002  Catalogos      (persona 4)
--
-- Los valores cerrados del sistema: las zonas y los estados. Van primero
-- porque todas las demas migraciones los usan.


-- ---------------------------------------------------------------------------
-- Tipos enumerados
-- ---------------------------------------------------------------------------
-- Un ENUM en vez de text con CHECK porque estos conjuntos no van a crecer:
-- salen del diseno de la Parte 1, no de lo que vaya pasando.
--
-- Lo que se gana sobre el CHECK:
--   el valor invalido no entra, igual que con CHECK
--   cuatro bytes en vez de texto variable
--   una sola definicion. rol_sujeto la usan cuentas y solicitudes_rol, y
--     antes era la misma lista de ocho escrita dos veces
--   \dT+ en psql lista los valores, asi que el esquema se documenta solo
--
-- Lo que cuesta, y conviene saberlo antes: agregar un valor se hace con
-- ALTER TYPE ... ADD VALUE, y el valor nuevo NO se puede usar en la misma
-- transaccion donde se agrego. Como el runner corre cada archivo en una
-- transaccion, una migracion que agregue un estado y lo use tiene que ir en
-- dos archivos. Quitar un valor no se puede: hay que recrear el tipo.

-- Los ocho roles de la matriz. Esta lista ES la matriz: si cambia, cambian
-- las 88 celdas, las politicas en Rego y las pruebas.
CREATE TYPE rol_sujeto AS ENUM (
    'DIRECCION_GENERAL',
    'DIRECCION_CERTIFICACION',
    'PERSONAL_ADMINISTRATIVO',
    'TECNICO_CAMPO',
    'VERIFICADOR',
    'AUDITOR_EXTERNO',
    'DUENO_FINCA',
    'TERCERO_AUTORIZADO'
);

-- El orden de declaracion es el orden del flujo, y tambien el que usa ORDER
-- BY. No es casualidad: asi "los mas avanzados primero" sale gratis.

CREATE TYPE estado_periodo     AS ENUM ('ABIERTO', 'CERRADO');

CREATE TYPE estado_medicion    AS ENUM ('REGISTRADA', 'APROBADA', 'DEVUELTA');

CREATE TYPE estado_enmienda    AS ENUM ('SOLICITADA', 'REVISADA',
                                        'CERRADA', 'DEVUELTA');

CREATE TYPE estado_certificado AS ENUM ('VIGENTE', 'ANULADO');

CREATE TYPE estado_solicitud   AS ENUM ('PENDIENTE', 'APROBADA',
                                        'RECHAZADA', 'APLICADA');

CREATE TYPE resultado_evento   AS ENUM ('PERMITIDO', 'DENEGADO');

-- Los tipos los crea app_migrate, que es su dueno. app_rw solo necesita
-- usarlos, y para eso no hace falta ningun GRANT: los tipos son de uso
-- publico salvo que se revoque.


-- ---------------------------------------------------------------------------
-- Zonas
-- ---------------------------------------------------------------------------
-- Unica tabla con llave de texto, y a proposito: las iniciales SON la llave
-- natural. Siete filas que no cambian nunca, y un  zona = 3  vuelve ilegible
-- toda consulta sin ganar nada.
--
-- Tabla y no ENUM porque las zonas si podrian cambiar, y porque C1 compara
-- finca.zona contra las filas de asignaciones_zona: necesita llave foranea.

CREATE TABLE zonas (
    id     text PRIMARY KEY,
    nombre text NOT NULL,

    -- Dos letras mayusculas, siempre. Evita que alguien meta 'pn' o
    -- 'Pacifico-Norte' y termine con dos filas para la misma zona.
    CONSTRAINT id_son_dos_letras CHECK (id ~ '^[A-Z]{2}$')
);

-- El catalogo va aqui y no en los datos de prueba: sin zonas no se registra
-- una finca, y sin fincas no se ejercita casi nada de la matriz.
INSERT INTO zonas (id, nombre) VALUES
    ('PN', 'Pacifico Norte'),
    ('PC', 'Pacifico Central'),
    ('PS', 'Pacifico Sur'),
    ('CN', 'Caribe Norte'),
    ('CS', 'Caribe Sur'),
    ('VC', 'Valle Central'),
    ('ZN', 'Zona Norte')
ON CONFLICT (id) DO NOTHING;
