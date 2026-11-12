-- Datos de prueba.
--
--     python db/migrar.py semilla
--
-- No es una migracion y no se anota en migraciones_aplicadas: esto se vuelve
-- a correr cuantas veces haga falta. Todo lleva ON CONFLICT DO NOTHING, asi
-- que repetirlo no duplica nada ni pisa lo que alguien haya cambiado.
--
-- Los id van fijos con OVERRIDING SYSTEM VALUE para poder referirse a ellos
-- en las pruebas y en el informe: "la finca 1", "la cuenta 4". Al final se
-- adelantan las secuencias para que lo que cree la aplicacion no choque.
--
-- Esta pensado para que cada condicion C1 a C11 se pueda ejercitar con estos
-- datos. Al final del archivo esta la lista de que fila sirve para cada una.
--
-- Lo que NO llena: la tabla credenciales. Necesita el hash Argon2id, que es
-- del frente de identidad. Las cuentas existen pero todavia nadie puede
-- iniciar sesion con ellas.


-- ---------------------------------------------------------------------------
-- Cuentas: una por rol, mas dos tecnicos y dos verificadores
-- ---------------------------------------------------------------------------
-- Hacen falta dos de cada uno porque C3, C4 y C5 exigen personas distintas.
-- Con un solo verificador no se puede probar que alguien aprueba lo que otro
-- registro, que es justamente lo que esas condiciones protegen.

INSERT INTO cuentas (id, usuario, nombre, rol) OVERRIDING SYSTEM VALUE VALUES
    ( 1, 'dg',   'Dora Guzman',        'DIRECCION_GENERAL'),
    ( 2, 'dc',   'Diego Cordero',      'DIRECCION_CERTIFICACION'),
    ( 3, 'pa',   'Paula Arias',        'PERSONAL_ADMINISTRATIVO'),
    ( 4, 'tc1',  'Tomas Campos',       'TECNICO_CAMPO'),
    ( 5, 'tc2',  'Tania Castro',       'TECNICO_CAMPO'),
    ( 6, 'vf1',  'Victor Fonseca',     'VERIFICADOR'),
    ( 7, 'vf2',  'Valeria Flores',     'VERIFICADOR'),
    ( 8, 'ae',   'Alberto Esquivel',   'AUDITOR_EXTERNO'),
    ( 9, 'df1',  'Delia Fallas',       'DUENO_FINCA'),
    (10, 'df2',  'Daniel Fuentes',     'DUENO_FINCA'),
    (11, 'ta',   'Teresa Alvarado',    'TERCERO_AUTORIZADO')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Asignaciones de zona: la base de C1
-- ---------------------------------------------------------------------------
-- tc1 y vf1 trabajan en Pacifico Norte. tc2 y vf2 en Caribe Sur. Asi se puede
-- probar que un tecnico no ve una finca fuera de su zona.

INSERT INTO asignaciones_zona (id, sujeto, zona, vence) OVERRIDING SYSTEM VALUE VALUES
    (1, 4, 'PN', DATE '2027-12-31'),
    (2, 6, 'PN', DATE '2027-12-31'),
    (3, 5, 'CS', DATE '2027-12-31'),
    (4, 7, 'CS', DATE '2027-12-31'),
    -- Vencida a proposito: sirve para probar que C1 mira la fecha y no solo
    -- que la fila exista.
    (5, 4, 'CS', DATE '2026-01-31')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Fincas: la base de C8, y los poligonos de C6
-- ---------------------------------------------------------------------------
-- Rectangulos sencillos en coordenadas de Costa Rica. Los de la finca 1 y la
-- 3 se superponen a proposito: con eso se prueba que C6 impide emitir dos
-- certificados sobre el mismo terreno.

INSERT INTO fincas (id, nombre, zona, propietario, poligono) OVERRIDING SYSTEM VALUE VALUES
    (1, 'La Esperanza', 'PN', 9,
     ST_GeomFromText('POLYGON((-85.70 10.60, -85.60 10.60, -85.60 10.70, -85.70 10.70, -85.70 10.60))', 4326)),
    (2, 'El Mirador',   'PN', 9,
     ST_GeomFromText('POLYGON((-85.40 10.60, -85.30 10.60, -85.30 10.70, -85.40 10.70, -85.40 10.60))', 4326)),
    (3, 'Vista Alegre', 'PN', 10,
     -- Se cruza con La Esperanza: C6 tiene que notarlo.
     ST_GeomFromText('POLYGON((-85.65 10.65, -85.55 10.65, -85.55 10.75, -85.65 10.75, -85.65 10.65))', 4326)),
    (4, 'Palo Verde',   'CS', 10,
     ST_GeomFromText('POLYGON((-83.10 9.60, -83.00 9.60, -83.00 9.70, -83.10 9.70, -83.10 9.60))', 4326))
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Periodos: la base de C2 y C11
-- ---------------------------------------------------------------------------

INSERT INTO periodos_medicion (id, etiqueta, estado, cerrado_en) OVERRIDING SYSTEM VALUE VALUES
    (1, '2026-Q1', 'CERRADO', TIMESTAMPTZ '2026-04-01 00:00:00+00'),
    (2, '2026-Q4', 'ABIERTO', NULL)
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Mediciones: la base de C3 y C6
-- ---------------------------------------------------------------------------

INSERT INTO mediciones (id, finca, periodo, autor, biomasa_toneladas, estado,
                        revisada_por, revisada_en)
OVERRIDING SYSTEM VALUE VALUES
    -- Aprobada por alguien distinto del autor: lista para emitir certificado.
    (1, 1, 2, 4, 120.500, 'APROBADA', 6, now()),
    -- Recien registrada: sirve para probar que su propio autor no la aprueba.
    (2, 2, 2, 4,  87.250, 'REGISTRADA', NULL, NULL),
    -- En el periodo cerrado: sirve para C11, pedir enmienda sobre ella.
    (3, 1, 1, 4, 115.000, 'APROBADA', 6, TIMESTAMPTZ '2026-03-15 00:00:00+00'),
    -- De otra zona y otro autor.
    (4, 4, 2, 5,  64.000, 'REGISTRADA', NULL, NULL),
    -- Aprobada, sobre la finca que se superpone con la 1: al intentar emitir
    -- su certificado, C6 tiene que negarlo por traslape.
    (5, 3, 2, 5,  95.750, 'APROBADA', 7, now())
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Enmiendas: la base de C4 y C5
-- ---------------------------------------------------------------------------
-- Pedida por el tecnico que registro la medicion del periodo cerrado (C11) y
-- revisada por otra persona (C4). Queda en REVISADA para que se pueda probar
-- el cierre de C5, que exige una tercera persona distinta de las dos.

INSERT INTO enmiendas (id, medicion, solicitante, justificacion, estado,
                       revisor, revisada_en)
OVERRIDING SYSTEM VALUE VALUES
    (1, 3, 4, 'El equipo de medicion estaba descalibrado esa semana.',
     'REVISADA', 6, now())
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Consentimientos: la base de C9
-- ---------------------------------------------------------------------------

INSERT INTO consentimientos (id, finca, tercero, otorgado_por, vence)
OVERRIDING SYSTEM VALUE VALUES
    (1, 1, 11,  9, DATE '2027-06-30'),
    -- Vencido: el mismo tercero, otra finca. C9 tiene que distinguirlos.
    (2, 4, 11, 10, DATE '2026-02-28')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Ventana de auditoria: la base de C7
-- ---------------------------------------------------------------------------
-- Una vigente hoy y otra que ya paso. Sin la vigente, el auditor externo no
-- tiene ningun permiso sobre nada, que es lo que dice la matriz.

INSERT INTO ventanas_auditoria (id, auditor, inicio, fin, alcance)
OVERRIDING SYSTEM VALUE VALUES
    (1, 8, CURRENT_DATE - 7, CURRENT_DATE + 30, 'Auditoria anual 2026'),
    (2, 8, DATE '2025-01-01', DATE '2025-03-31', 'Auditoria 2025, cerrada')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Solicitud de cambio de rol: la base de C10
-- ---------------------------------------------------------------------------
-- Pedida por el administrativo y aprobada por Direccion General, que son
-- personas distintas. Es lo que C10 exige antes de tocar una cuenta.

INSERT INTO solicitudes_rol (id, cuenta_afectada, rol_solicitado, solicitante,
                             estado, aprobador, aprobada_en)
OVERRIDING SYSTEM VALUE VALUES
    (1, 5, 'VERIFICADOR', 3, 'APROBADA', 1, now()),
    (2, 4, 'VERIFICADOR', 3, 'PENDIENTE', NULL, NULL)
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Adelantar las secuencias
-- ---------------------------------------------------------------------------
-- Los id de arriba se pusieron a mano, asi que el contador de cada tabla
-- sigue en 1. Sin esto, el primer INSERT de la aplicacion choca con la
-- semilla y falla por llave duplicada.

SELECT setval(pg_get_serial_sequence('cuentas', 'id'),
              (SELECT max(id) FROM cuentas));
SELECT setval(pg_get_serial_sequence('asignaciones_zona', 'id'),
              (SELECT max(id) FROM asignaciones_zona));
SELECT setval(pg_get_serial_sequence('fincas', 'id'),
              (SELECT max(id) FROM fincas));
SELECT setval(pg_get_serial_sequence('periodos_medicion', 'id'),
              (SELECT max(id) FROM periodos_medicion));
SELECT setval(pg_get_serial_sequence('mediciones', 'id'),
              (SELECT max(id) FROM mediciones));
SELECT setval(pg_get_serial_sequence('enmiendas', 'id'),
              (SELECT max(id) FROM enmiendas));
SELECT setval(pg_get_serial_sequence('consentimientos', 'id'),
              (SELECT max(id) FROM consentimientos));
SELECT setval(pg_get_serial_sequence('ventanas_auditoria', 'id'),
              (SELECT max(id) FROM ventanas_auditoria));
SELECT setval(pg_get_serial_sequence('solicitudes_rol', 'id'),
              (SELECT max(id) FROM solicitudes_rol));


-- ---------------------------------------------------------------------------
-- Que fila sirve para probar que condicion
-- ---------------------------------------------------------------------------
--
--  C1  zona asignada        tc1 (4) tiene PN; la finca 4 esta en CS, no la ve.
--                           La asignacion 5 esta vencida: tampoco cuenta.
--  C2  periodo abierto      el 2 esta ABIERTO, el 1 CERRADO.
--  C3  no aprobar lo propio la medicion 2 la registro tc1 (4); tc1 no puede
--                           aprobarla, vf1 (6) si.
--  C4  revisor distinto     la enmienda 1 la pidio tc1 (4) y la reviso vf1 (6).
--  C5  tres personas        esa enmienda esta REVISADA: para cerrarla hace
--                           falta alguien que no sea ni 4 ni 6.
--  C6  traslape             la medicion 5 es de la finca 3, que se cruza con
--                           la finca 1. Si la 1 ya tiene certificado vigente,
--                           la 5 no se puede emitir.
--  C7  ventana de auditoria la ventana 1 cubre hoy, la 2 ya paso.
--  C8  propietario          las fincas 1 y 2 son de df1 (9); las 3 y 4 de
--                           df2 (10).
--  C9  consentimiento       el 1 esta vigente, el 2 vencio.
--  C10 aprobacion previa    la solicitud 1 la pidio pa (3) y la aprobo dg (1).
--  C11 periodo cerrado      la medicion 3 esta en el periodo 1, que esta
--                           CERRADO, y la registro tc1 (4).
