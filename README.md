# Verdeazul Carbono. Plataforma de certificación

Proyecto 2 de CE-1115 Seguridad de la Información, Grupo 4, Instituto Tecnológico de Costa Rica.

Implementación y despliegue del sistema diseñado en la Parte 1: control de acceso híbrido RBAC2 más ABAC con controles de historial, para una empresa que certifica captura de carbono en fincas forestales.

## Estado

| Pieza | Estado |
|---|---|
| Neon PostgreSQL, base principal y bitácora | Creadas y verificadas |
| Esqueleto del backend con `/salud` | Listo |
| Servicio de borde con plantillas | Esqueleto listo |
| Dockerfile sin root, los cuatro componentes | Listos, pendientes de construir |
| Contratos entre frentes | Escritos, el esquema ya implementado |
| Matriz transcrita y pruebas de cobertura | Armadas: 884 denegaciones pasan, 84 concesiones en espera del motor |
| Dependabot | Configurado para los cuatro componentes |
| Integración continua | Configurada, sin tocar Google Cloud |
| Esquema de base de datos en SQL | Aplicado: 15 tablas, 7 tipos enumerados |
| Motor de políticas en Rego | Relleno que deniega todo |
| Cuenta de facturación de Google Cloud | Bloqueada, esperando resolución |
| Artifact Registry y Cloud Run | Pendientes de la facturación |

## Estructura

```
contracts/                 Los acuerdos que permiten trabajar en paralelo
  matriz.md                La matriz de la Parte 1 transcrita: 88 celdas
db/
  migrations/              Esquema de verdeazul-app
  bitacora/                Esquema de verdeazul-bitacora, instancia separada
  roles/                   los cinco roles de privilegio minimo
docs/                      Desviaciones respecto al diseño de la Parte 1
services/
  api/                     Backend, punto de aplicación (PEP)
  edge/                    Servicio de borde: interfaz y único expuesto a internet
  policies/                Motor de políticas en Rego (PDP)
  transmisor/              Bandeja de salida a bitácora y trabajos programados
tests/matriz/              Una prueba por celda: la tabla de cobertura
.github/
  workflows/               Integración continua
  dependabot.yml           Revisión semanal de dependencias
```

Los cuatro componentes de `services/` corresponden uno a uno con la arquitectura de la Parte 1 y cada uno tiene su propia imagen, como exige §3.2 del enunciado. Hoy son esqueletos: el motor de políticas deniega todo a propósito y el esquema todavía no existe en SQL.

Los documentos de la Parte 1 y el enunciado no se versionan. Están en el disco de cada uno pero fuera de git: el enunciado es material del profesor y este repositorio es público, y los documentos de la Parte 1 pesan 5.9 MB que el profesor ya tiene. Lo que sí se consulta a diario está transcrito en [contracts/matriz.md](contracts/matriz.md).

## Correspondencia con el diseño de la Parte 1

Cada componente de este repositorio corresponde a uno del documento de arquitectura. Las diferencias están documentadas en [docs/P2_Desviaciones_respecto_P1.md](docs/P2_Desviaciones_respecto_P1.md).

| Componente del diseño | Aquí |
|---|---|
| Backend API (PEP) | `services/api` |
| Base de datos (PIP) | Neon, proyecto `verdeazul-app` |
| Bitácora | Neon, proyecto `verdeazul-bitacora`, instancia separada |
| Motor de políticas (PDP) | `services/policies`, contenedor adjunto del backend |
| Proxy inverso | `services/edge` más el TLS de Cloud Run |
| Gestor de secretos | Reemplazado por Secret Manager |

## Correr en local

**Antes que nada hay que armar el `.env`.** El paso a paso está en
[db/README.md](db/README.md): crear los proyectos en Neon, generar las
contraseñas, crear los roles y aplicar el esquema.

Con el `.env` listo:

```bash
.venv/Scripts/python.exe -m pip install -r services/api/requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir services/api --port 8080
```

La comprobación es `http://localhost:8080/salud`.

O en contenedor, que es lo que corre desplegado:

```bash
docker build -t verdeazul-api:dev services/api
docker run --rm -p 8080:8080 --env-file .env verdeazul-api:dev
```

El archivo `.env` está ignorado por git y tiene que seguir estándolo. La cadena de conexión de Neon no se pega en ningún archivo versionado, ni siquiera temporalmente, porque el historial de git conserva lo que se borra después.

## Construir y publicar una imagen

Las imágenes llevan etiqueta de versión explícita. La etiqueta `latest` no se usa, porque se mueve y no permite saber qué está corriendo en producción ni a qué versión volver.

```bash
VERSION=v0.1.0
REGION=us-east4
PROYECTO=verdeazul-grupo4
REPO=verdeazul

docker build -t ${REGION}-docker.pkg.dev/${PROYECTO}/${REPO}/api:${VERSION} services/api
docker push ${REGION}-docker.pkg.dev/${PROYECTO}/${REPO}/api:${VERSION}
```

Cada etiqueta de imagen corresponde a una etiqueta de git del mismo nombre, de modo que se puede ir de la versión que corre en producción al estado exacto del código.

## Desplegar

```bash
gcloud run deploy verdeazul-api \
  --image ${REGION}-docker.pkg.dev/${PROYECTO}/${REPO}/api:${VERSION} \
  --region ${REGION} \
  --set-secrets DATABASE_URL=verdeazul-db-url:latest \
  --set-env-vars APP_VERSION=${VERSION} \
  --no-allow-unauthenticated
```

El backend no acepta invocaciones anónimas. Solo la cuenta de servicio del servicio de borde puede llamarlo, que es como se implementa la frontera de confianza F2 del diseño.

## Secretos

Ninguna credencial vive en el repositorio, en las imágenes ni en el Dockerfile. Se guardan en Secret Manager y Cloud Run las inyecta como variables de entorno con `--set-secrets`, de modo que la configuración de la revisión guarda una referencia al secreto y no su valor.

Los secretos previstos son cuatro: la cadena de conexión de la base principal, la de la bitácora, la llave privada de firma de certificados y la llave del HMAC de la cadena de la bitácora.

La capa gratuita permite seis versiones de secreto activas, así que al crear una versión nueva hay que deshabilitar la anterior.

## Versiones publicadas

| Versión | Imagen | Commit | Desplegada |
|---|---|---|---|
| | | | |

## Equipo

Grupo 4: Meibel Ceciliano, Carlos Contreras, Ludwin Ramos, Henry Núñez, Adriel Chaves.

Profesor: MSc. Andrés F. Vargas Rivera.

El trabajo está repartido en cinco partes con un dueño cada una: plataforma y despliegue, identidad y cuentas, motor de autorización, dominio de certificación, y certificados firmados con bitácora. Quién hace qué y qué necesita de los demás está en [contracts/README.md](contracts/README.md). La defensa es individual, así que cada quien le da un recorrido de su parte al resto antes de la presentación.
