-- 001  Roles de la base principal (verdeazul-app)
--
--     python db/migrar.py roles
--
-- Se aplica una vez, como dueno del proyecto. Es la unica vez que se usa
-- neondb_owner: de la 002 en adelante todo corre como app_migrate.
--
-- Sin contrasenas, a proposito. PostgreSQL no acepta parametros en DDL, asi
-- que lo natural seria CREATE ROLE app_rw LOGIN PASSWORD '...', y eso es una
-- credencial versionada: anula los 12 puntos del criterio de secretos. Los
-- roles nacen NOLOGIN y el login se da con migrar.py claves.

CREATE EXTENSION IF NOT EXISTS postgis;


-- Los tres roles. Idempotente porque esto se corre varias veces mientras el
-- esquema se estabiliza.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migrate') THEN
    CREATE ROLE app_migrate NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outbox_rw') THEN
    CREATE ROLE outbox_rw NOLOGIN;
  END IF;
END
$$;


-- PUBLIC es todo rol, presente y futuro. Sin esto, cualquier rol que se cree
-- despues puede conectarse sin que nadie se lo haya dado.
REVOKE ALL ON SCHEMA   public FROM PUBLIC;
REVOKE ALL ON DATABASE neondb FROM PUBLIC;

GRANT CONNECT ON DATABASE neondb TO app_migrate, app_rw, outbox_rw;
GRANT USAGE   ON SCHEMA   public TO app_migrate, app_rw, outbox_rw;

-- Solo app_migrate crea estructura. Una inyeccion SQL en un endpoint no
-- alcanza a tirar una tabla, porque app_rw no tiene el permiso.
GRANT CREATE ON SCHEMA public TO app_migrate;

-- PostGIS la lee para transformar coordenadas.
GRANT SELECT ON TABLE spatial_ref_sys TO app_migrate, app_rw;


-- Lo que heredaran las tablas futuras. Un GRANT ON ALL TABLES solo alcanza a
-- las que ya existen, y aqui no hay ninguna todavia: sin esto, cada migracion
-- tendria que acordarse de dar permisos y la aplicacion falla con permission
-- denied el dia que alguien lo olvide.
--
-- ALTER DEFAULT PRIVILEGES FOR ROLE exige ser miembro de ese rol.
GRANT app_migrate TO CURRENT_USER;

ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO app_rw;

ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_rw;

-- Sin DELETE ni TRUNCATE: ninguna celda de la matriz concede el permiso E.


-- La tabla la crea migrar.py antes de aplicar este archivo.
GRANT SELECT, INSERT ON TABLE migraciones_aplicadas TO app_migrate;


-- Quedan dos GRANT pendientes, porque sus tablas no existen todavia:
--
--   003  REVOKE UPDATE ON mediciones FROM app_rw y volver a darlo por columna
--        (estado, revisada_por, motivo_devolucion). Asi la aplicacion no puede
--        tocar biomasa_toneladas: ningun rol tiene M en O3.
--
--   006  GRANT a outbox_rw sobre eventos_pendientes, la unica tabla que ese
--        rol debe ver.
