# Verdeazul Carbono. Plataforma de certificación

Proyecto 2 de CE-1115 Seguridad de la Información, Grupo 4, Instituto Tecnológico de Costa Rica.

Implementación y despliegue del sistema diseñado en la Parte 1: control de acceso híbrido RBAC2 más ABAC con controles de historial, para una empresa que certifica captura de carbono en fincas forestales.

## Estado

Desplegado en **https://verdeazul-edge-igwgmkeipa-uk.a.run.app**

| Pieza | Estado |
|---|---|
| Servicio de borde en Cloud Run | Desplegado. Es la única dirección pública |
| Backend y motor de políticas en Cloud Run | Desplegados juntos, cerrados a internet |
| Despliegue automático | Cada push a `develop` construye, publica y despliega, sin llaves |
| Secret Manager | Tres secretos, inyectados como variables de entorno |
| Neon, base principal y bitácora | Esquema aplicado: 15 tablas, 7 tipos enumerados, 5 roles |
| Motor de políticas en Rego | Completo: 88 celdas y las condiciones C1 a C11 |
| Pruebas de la matriz | 977, corren en cada pull request contra un OPA real |
| Dependabot | Configurado para los cuatro componentes |
| Autenticación | Sin empezar |
| Endpoints de la matriz | 1 de 57 (`/salud`) |
| Firma de certificados | Sin empezar |
| Transmisor de bitácora | Esqueleto que responde 501 |

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
  workflows/               Integración continua y despliegue
  dependabot.yml           Revisión semanal de dependencias
```

Los cuatro componentes de `services/` corresponden uno a uno con la arquitectura de la Parte 1 y cada uno tiene su propia imagen, como exige §3.2 del enunciado. El motor de políticas y el esquema están completos; el backend todavía no tiene los endpoints de la matriz y el transmisor es un esqueleto.

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

## Desplegar

No se despliega a mano. [.github/workflows/desplegar.yml](.github/workflows/desplegar.yml)
corre solo cuando algo de `services/` entra a `develop`, y también se puede
lanzar desde la pestaña Actions de GitHub.

El workflow se autentica en Google Cloud con federación de identidad: GitHub
firma un token que dice qué repositorio lo pide y Google lo canjea por un
permiso temporal. No existe ningún archivo de credenciales de Google, ni en el
repositorio ni en los secretos de GitHub.

Despliega dos servicios en `us-east4`, proyecto `verdeazul-g4`:

| Servicio | Contenedores | Acceso |
|---|---|---|
| `verdeazul-edge` | `edge` | Público |
| `verdeazul-api` | `api` y `policies`, que comparten red | Solo con credencial de Google |

El backend no acepta invocaciones anónimas. Esa es la frontera de confianza F2
del diseño.

Las imágenes llevan como etiqueta los primeros siete caracteres del commit.
`latest` no se usa, porque se mueve y no permite saber qué está corriendo ni a
qué versión volver.

## Secretos

Ninguna credencial vive en el repositorio, en las imágenes ni en el Dockerfile. Se guardan en Secret Manager y Cloud Run las inyecta como variables de entorno con `--set-secrets`, de modo que la configuración de la revisión guarda una referencia al secreto y no su valor.

Hoy hay tres: la cadena de conexión de la base principal (`verdeazul-db-url`), la de lectura de la bitácora (`verdeazul-bitacora-lectura-url`) y la llave del HMAC de búsqueda de cédulas (`llave-busqueda-cedula`). Faltan la llave privada de firma de certificados y la del HMAC de la cadena de la bitácora, que llegan con esas dos piezas.

El backend corre con su propia cuenta de servicio, que solo puede leer esos secretos. Sin ella, Cloud Run usaría la cuenta por omisión de Compute, que tiene permisos de Editor sobre todo el proyecto.

La capa gratuita permite seis versiones de secreto activas, así que al crear una versión nueva hay que deshabilitar la anterior.

## Versiones publicadas

Cada etiqueta es el commit del que salió la imagen, así que `git show <etiqueta>` lleva al código exacto. Las imágenes viven en `us-east4-docker.pkg.dev/verdeazul-g4/verdeazul`.

| Etiqueta | Imágenes | Fecha | Qué trajo |
|---|---|---|---|
| `bdec178` | api, policies, edge | 2026-11-09 | Despliegue de `develop` con el PR #13. **Es la que corre hoy** |
| `d2f1d2e` | api, policies, edge | 2026-11-09 | El grupo de conexiones aguanta que Cloud Run y Neon se duerman |
| `8653dbb` | api, policies, edge | 2026-11-09 | Primer despliegue del backend con el motor como contenedor adjunto |
| `d4cc04b` | edge | 2026-11-09 | Primer despliegue: solo el borde |

Cada despliegue agrega una fila arriba. La lista completa, por si esta tabla se atrasa:

```bash
gcloud artifacts docker tags list us-east4-docker.pkg.dev/verdeazul-g4/verdeazul
```

La versión que está corriendo sale al pie de cada página del borde («versión bdec178») y en el campo `version` de `/salud` del backend.

## Equipo

Grupo 4: Meibel Ceciliano, Carlos Contreras, Ludwin Ramos, Henry Núñez, Adriel Chaves.

Profesor: MSc. Andrés F. Vargas Rivera.

El trabajo está repartido en cinco partes con un dueño cada una: plataforma y despliegue, identidad y cuentas, motor de autorización, dominio de certificación, y certificados firmados con bitácora. Quién hace qué y qué necesita de los demás está en [contracts/README.md](contracts/README.md). La defensa es individual, así que cada quien le da un recorrido de su parte al resto antes de la presentación.
