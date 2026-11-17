-- 013  El documento firmado de cada certificado 
--
-- La 009 guarda la firma y la llave publica, pero no el texto exacto que se
-- firmo. Sin el, para entregarle el archivo al dueno habria que reconstruirlo
-- a partir de columnas y joins, y basta que algo cambie despues (el nombre de
-- la finca, el formato de una fecha) para que el archivo reconstruido ya no
-- cuadre con su firma.
--
-- Se guarda el documento completo tal como se entrego. Es lo que descarga el
-- dueno o el tercero autorizado, y lo que despues se sube a la verificacion
-- publica.
--
-- La tabla esta vacia hasta hoy (el modulo O5 no existia), asi que NOT NULL
-- se puede poner directo. Si alguna vez hubiera filas, esta migracion falla
-- en vez de dejar certificados sin documento.
--
-- Permisos: app_rw ya tiene INSERT sobre toda la tabla, que alcanza a las
-- columnas nuevas. UPDATE no: la 012 se lo dejo solo sobre estado,
-- motivo_anulacion y anulado_en. Asi el documento firmado tampoco se puede
-- cambiar despues de emitido, ni siquiera por la aplicacion.

ALTER TABLE certificados
    ADD COLUMN documento text NOT NULL;

-- Emitir pide el id del certificado antes de insertarlo, porque el id va
-- dentro de lo firmado (rutas.py, nextval). Los privilegios por omision de
-- 001_roles ya le dan USAGE a app_rw sobre las secuencias nuevas; se dice
-- aqui tambien para que no dependa de eso. Sin nombre fijo: se le pregunta a
-- la base como se llama la secuencia de la columna identidad.
DO $$
BEGIN
    EXECUTE format('GRANT USAGE ON SEQUENCE %s TO app_rw',
                   pg_get_serial_sequence('certificados', 'id'));
END
$$;
