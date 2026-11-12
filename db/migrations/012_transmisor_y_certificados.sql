-- 012  Lo que necesitan el transmisor y los certificados   (persona 1)
--
-- Agrega una columna y ajusta permisos. No borra ni renombra nada, y no
-- cambia nada que el codigo de hoy use.


-- ---------------------------------------------------------------------------
-- eventos_pendientes: donde el transmisor lleva la cuenta de la cadena
-- ---------------------------------------------------------------------------
-- Cada eslabon se calcula con el del evento anterior (BI-02). El transmisor no
-- lo puede leer de la bitacora, porque log_writer solo inserta (001_bitacora).
-- Lo guarda aqui, en la fila que acaba de copiar, y la corrida siguiente lo
-- saca de la ultima fila enviada.

ALTER TABLE eventos_pendientes
    ADD COLUMN eslabon text,

    -- Se marcan juntos. Una fila enviada sin eslabon dejaria a la corrida
    -- siguiente sin punto de partida.
    ADD CONSTRAINT enviado_lleva_eslabon
        CHECK ((enviado_en IS NULL) = (eslabon IS NULL));

GRANT UPDATE (eslabon) ON eventos_pendientes TO outbox_rw;

-- La aplicacion solo anota eventos. Con UPDATE podria cambiar uno antes de
-- que el transmisor lo copie, y la cadena sellaria el texto ya alterado.
-- Ningun codigo lo usaba: lo tenia por los permisos por omision de 001_roles.
REVOKE UPDATE ON eventos_pendientes FROM app_rw;


-- ---------------------------------------------------------------------------
-- certificados: lo firmado no se cambia
-- ---------------------------------------------------------------------------
-- Un certificado circula fuera del sistema con su firma (D-10). Igual que en
-- mediciones (006), la aplicacion solo puede cambiar lo que hace falta para
-- anularlo; la firma, la llave publica y el contenido quedan como se firmaron.

REVOKE UPDATE ON certificados FROM app_rw;
GRANT  UPDATE (estado, motivo_anulacion, anulado_en) ON certificados TO app_rw;
