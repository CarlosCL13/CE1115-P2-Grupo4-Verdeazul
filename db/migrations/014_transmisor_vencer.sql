-- 014  El transmisor revoca lo vencido y anota lo que hace   (persona 5)
--
-- La tarea `vencer` del transmisor (HBAC-03) marca como revocadas las
-- asignaciones tecnico-zona (O8) y los consentimientos a terceros (O7) cuya
-- fecha de fin ya paso. Antes de esta migracion outbox_rw solo veia la
-- bandeja de salida.
--
-- El 013 queda para O7 (consentimientos). Este no depende de el: las dos
-- tablas existen desde la 007.
--
-- Minimo privilegio, columna por columna:
--
--   asignaciones_zona, consentimientos
--       SELECT de lo que hace falta para decidir que vencio y para el evento
--       UPDATE solo de la fecha de revocacion: no puede cambiar la zona, el
--       tercero, ni extender un vencimiento
--
--   eventos_pendientes
--       INSERT de un evento, para que cada revocacion automatica quede en la
--       bitacora igual que una hecha a mano (BI). Sin enviado_en ni eslabon:
--       un evento nuevo nace sin enviar y lo encadena `transmitir`, como
--       cualquier otro.
--
-- Lo que esto le da a quien comprometa el transmisor: revocar accesos antes
-- de tiempo (un dano de disponibilidad, no de integridad: nadie gana acceso)
-- y anotar eventos falsos en la bandeja. Lo segundo ya lo podia hacer, porque
-- tiene log_writer sobre la bitacora; esta migracion no le agrega un camino
-- nuevo. Ver D-03.

GRANT SELECT (id, sujeto, zona, vence, revocada_en)
    ON asignaciones_zona TO outbox_rw;
GRANT UPDATE (revocada_en)
    ON asignaciones_zona TO outbox_rw;

GRANT SELECT (id, finca, tercero, vence, revocado_en)
    ON consentimientos TO outbox_rw;
GRANT UPDATE (revocado_en)
    ON consentimientos TO outbox_rw;

GRANT INSERT (accion, sujeto, objeto, resultado, motivo, detalle)
    ON eventos_pendientes TO outbox_rw;
