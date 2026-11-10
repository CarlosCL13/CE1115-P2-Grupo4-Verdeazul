-- 011  Ajustes de identidad   (persona 2)   O9, O10 y la tabla de C10
--
-- Lo que la 004 no previo y aparecio al escribir la autenticacion. La 004 ya
-- esta aplicada en Neon, asi que no se edita: todo va aqui.
--
-- Nada de esto borra ni renombra. Solo agrega columnas, relaja dos NOT NULL
-- que impedian un caso real (pedir el alta de una cuenta que todavia no
-- existe) y agrega restricciones que llevan a la base reglas que antes solo
-- vivian en el codigo.


-- ---------------------------------------------------------------------------
-- sesiones: inactividad y reautenticacion
-- ---------------------------------------------------------------------------
-- ultimo_uso: el Informe de politicas de P1 (Tabla 7.1) fija un cierre por
-- inactividad distinto por perfil, 15 minutos para las direcciones y 60 para
-- el tecnico de campo. expira_en solo cubre el tope absoluto de SE-01; sin
-- esta columna no hay forma de saber cuanto lleva quieta una sesion.
--
-- reautenticada_en: P1 vuelve a pedir el factor antes de cambiar roles,
-- abrir o cerrar periodos y aprobar. Se guarda en la sesion, no en la cuenta,
-- porque reautenticarse en un navegador no debe habilitar otro.

ALTER TABLE sesiones
    ADD COLUMN ultimo_uso       timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN reautenticada_en timestamptz;


-- ---------------------------------------------------------------------------
-- credenciales: TOTP sin repeticion, codigos de recuperacion, clave temporal
-- ---------------------------------------------------------------------------
-- totp_ultimo_paso: el numero de la ventana de 30 segundos del ultimo codigo
-- aceptado. Un codigo vale para su ventana y la tolerancia de reloj la
-- extiende a tres; sin esto, quien mire el codigo por encima del hombro lo
-- puede volver a usar durante un minuto y medio.
--
-- codigos_recuperacion: RC-02. Huellas SHA-256, nunca los codigos. Son
-- aleatorios de 50 bits, asi que no hace falta un hash lento como con las
-- contrasenas: no hay diccionario que recorrer.
--
-- debe_cambiar: una cuenta nueva nace con una clave temporal que conoce quien
-- la creo. Hasta cambiarla, la sesion solo sirve para cambiarla.

ALTER TABLE credenciales
    ADD COLUMN totp_ultimo_paso     bigint,
    ADD COLUMN codigos_recuperacion text[]  NOT NULL DEFAULT '{}',
    ADD COLUMN debe_cambiar         boolean NOT NULL DEFAULT false;


-- ---------------------------------------------------------------------------
-- cuentas: cuando se dio de baja
-- ---------------------------------------------------------------------------
-- CU-13: las cuentas no se borran, se desactivan. activa ya existia; la fecha
-- es lo que permite responder "desde cuando" sin ir a la bitacora.

ALTER TABLE cuentas
    ADD COLUMN desactivada_en timestamptz,

    ADD CONSTRAINT desactivada_lleva_fecha
        CHECK (activa OR desactivada_en IS NOT NULL);


-- ---------------------------------------------------------------------------
-- solicitudes_rol: alta, cambio de rol y baja
-- ---------------------------------------------------------------------------
-- La 004 solo modelaba el cambio de rol de una cuenta que ya existe. Pero C10
-- gobierna las tres celdas de PA sobre O9 (L, C, M), y crear una cuenta (C)
-- tambien exige la aprobacion previa de Direccion General (CU-01). Esa
-- solicitud se hace antes de que la cuenta exista, asi que cuenta_afectada
-- no puede ser obligatoria.
--
-- Tipo enumerado nuevo y no un valor agregado a otro: CREATE TYPE se puede
-- usar en la misma transaccion, ALTER TYPE ... ADD VALUE no.

CREATE TYPE tipo_solicitud AS ENUM ('ALTA', 'CAMBIO_ROL', 'BAJA');

ALTER TABLE solicitudes_rol
    ALTER COLUMN cuenta_afectada DROP NOT NULL,
    ALTER COLUMN rol_solicitado  DROP NOT NULL,

    -- Las filas que ya existen son cambios de rol, que era lo unico que se
    -- podia pedir. El valor por omision las deja bien clasificadas.
    ADD COLUMN tipo           tipo_solicitud NOT NULL DEFAULT 'CAMBIO_ROL',

    -- Solo para ALTA: los datos de la cuenta que todavia no existe.
    ADD COLUMN usuario_nuevo  text,
    ADD COLUMN nombre_nuevo   text,

    ADD COLUMN justificacion  text,

    -- Quien ejecuto el cambio ya aprobado. Es el "sujeto" de C10.
    ADD COLUMN aplicada_por   integer REFERENCES cuentas(id),
    ADD COLUMN aplicada_en    timestamptz,

    ADD COLUMN rechazada_en   timestamptz,
    ADD COLUMN motivo_rechazo text,

    -- Cada tipo lleva lo suyo y nada mas.
    ADD CONSTRAINT forma_segun_tipo CHECK (
        CASE tipo
            WHEN 'ALTA' THEN
                usuario_nuevo IS NOT NULL AND nombre_nuevo IS NOT NULL
                AND rol_solicitado IS NOT NULL
                -- Al aplicarse se anota que cuenta nacio de ella.
                AND (estado <> 'APLICADA' OR cuenta_afectada IS NOT NULL)
            WHEN 'CAMBIO_ROL' THEN
                cuenta_afectada IS NOT NULL AND rol_solicitado IS NOT NULL
            WHEN 'BAJA' THEN
                cuenta_afectada IS NOT NULL AND rol_solicitado IS NULL
        END),

    -- CU-03: nadie se asigna permisos a si mismo. Ni quien pide ni quien
    -- aprueba puede ser la cuenta que cambia.
    ADD CONSTRAINT nadie_pide_para_si
        CHECK (cuenta_afectada IS NULL OR cuenta_afectada <> solicitante),
    ADD CONSTRAINT nadie_aprueba_para_si
        CHECK (cuenta_afectada IS NULL OR aprobador IS NULL
               OR cuenta_afectada <> aprobador),

    -- La otra mitad de C10 que si cabe en un CHECK: quien ejecuta no es
    -- quien aprobo. La 004 ya impedia que quien pide sea quien aprueba.
    ADD CONSTRAINT aplica_otro_que_el_aprobador
        CHECK (aplicada_por IS NULL OR aplicada_por <> aprobador),

    ADD CONSTRAINT aplicada_lleva_quien
        CHECK (estado <> 'APLICADA'
               OR (aplicada_por IS NOT NULL AND aplicada_en IS NOT NULL)),
    ADD CONSTRAINT rechazada_lleva_motivo
        CHECK (estado <> 'RECHAZADA'
               OR (motivo_rechazo IS NOT NULL AND rechazada_en IS NOT NULL));

-- Lo que el administrativo tiene por aplicar.
CREATE INDEX solicitudes_rol_aprobadas_idx ON solicitudes_rol (cuenta_afectada)
    WHERE estado = 'APROBADA';
