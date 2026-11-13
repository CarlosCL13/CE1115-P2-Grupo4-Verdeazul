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
| Secret Manager | Ocho secretos, inyectados como variables de entorno |
| Neon, base principal y bitácora | Esquema aplicado: 15 tablas, 7 tipos enumerados, 5 roles |
| Motor de políticas en Rego | Completo: 88 celdas y las condiciones C1 a C11 |
| Pruebas de la matriz | 977, corren en cada pull request contra un OPA real |
| Pruebas de integración | Identidad, certificación, enmiendas, asignaciones y bitácora, en cada pull request contra un PostgreSQL desechable con el mismo esquema |
| Dependabot | Configurado para los cuatro componentes. Alerta atendida: CVE-2025-62727 en Starlette ([docs/Dependabot.md](docs/Dependabot.md)) |
| Autenticación | Completa: Argon2id, sesión en la base, segundo factor TOTP, bloqueo RC-01, reautenticación |
| Endpoints de la matriz | 46 de 57: identidad (O6, O9, O10), certificación (O1, O2, O3), O4 enmiendas, O8 asignaciones, O11 bitácora y las cuatro tareas del transmisor. **Faltan O5 certificados y O7 consentimientos** |
| Firma de certificados | Pendiente (O5): la llave ya está en Secret Manager |
| Bitácora | Completa: bandeja de salida, transmisor cada 30 minutos con cadena HMAC, comprobación de la cadena (`cadena`), revocación de lo vencido (`vencer`) y copia semanal a Cloud Storage con retención de diez años (`volcado`) |
| Informe | Material completo en [docs/Informe_P2.md](docs/Informe_P2.md) |

## Estructura

```
contracts/                 Los acuerdos que permiten trabajar en paralelo
  matriz.md                La matriz de la Parte 1 transcrita: 88 celdas
  05-sesion.md             Cómo usa cada endpoint la sesión y el motor
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
tests/identidad/           Contraseñas, sesión, segundo factor, C10 y datos personales
tests/certificacion/       Fincas, períodos y mediciones
tests/enmiendas/           O4: C4, C5, C11 y la máquina de estados
tests/asignaciones/        O8: quién asigna, C1 y revocar el mismo día
tests/bitacora/            O11: lectura, exportación, C7 y que log_reader no escribe
.github/
  workflows/               Integración continua y despliegue
  dependabot.yml           Revisión semanal de dependencias
```

Los cuatro componentes de `services/` corresponden uno a uno con la arquitectura de la Parte 1 y cada uno tiene su propia imagen, como exige §3.2 del enunciado. El motor de políticas, el esquema, el transmisor y la bitácora están completos, y el backend tiene identidad, certificación, enmiendas y asignaciones. Faltan O5 certificados y O7 consentimientos. Lo que falta para la entrega está en [docs/Informe_P2.md](docs/Informe_P2.md), §7 y §8, y en la sección «Dónde estamos» de [contracts/README.md](contracts/README.md).

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

Despliega tres servicios en `us-east4`, proyecto `verdeazul-g4`:

| Servicio | Contenedores | Acceso |
|---|---|---|
| `verdeazul-edge` | `edge` | Público |
| `verdeazul-api` | `api` y `policies`, que comparten red | Solo con credencial de Google |
| `verdeazul-transmisor` | `transmisor` | Solo Cloud Scheduler. Una instancia y una petición a la vez |

El backend no acepta invocaciones anónimas. Esa es la frontera de confianza F2
del diseño. El borde lo invoca con su propia cuenta de servicio,
`verdeazul-edge`, cuyo único permiso es ese.

### Configuración de una sola vez para identidad

Antes del primer despliegue con identidad hay que crear dos cosas en Google
Cloud. Las dos se hacen una vez y no viven en el repositorio.

La llave de cifrado de datos personales. Se genera, se guarda en el `.env` de
quien vaya a cargar las credenciales de prueba, y se sube con el **mismo
valor**:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# copiar el valor al .env como LLAVE_CIFRADO_DATOS=... y luego:
printf '%s' 'EL-VALOR' | gcloud secrets create llave-cifrado-datos \
  --project=verdeazul-g4 --replication-policy=automatic --data-file=-
gcloud secrets add-iam-policy-binding llave-cifrado-datos --project=verdeazul-g4 \
  --member=serviceAccount:verdeazul-api@verdeazul-g4.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

La cuenta de servicio del borde, con permiso de invocar al backend y nada más,
y el permiso para que el despliegue la use:

```bash
gcloud iam service-accounts create verdeazul-edge --project=verdeazul-g4 \
  --display-name="Borde de Verdeazul"
gcloud run services add-iam-policy-binding verdeazul-api --project=verdeazul-g4 \
  --region=us-east4 --role=roles/run.invoker \
  --member=serviceAccount:verdeazul-edge@verdeazul-g4.iam.gserviceaccount.com
gcloud iam service-accounts add-iam-policy-binding \
  verdeazul-edge@verdeazul-g4.iam.gserviceaccount.com --project=verdeazul-g4 \
  --role=roles/iam.serviceAccountUser \
  --member=serviceAccount:ci-despliegue@verdeazul-g4.iam.gserviceaccount.com
```

Y la migración nueva en Neon: `python db/migrar.py app` aplica la 011.

Las imágenes llevan como etiqueta los primeros siete caracteres del commit.
`latest` no se usa, porque se mueve y no permite saber qué está corriendo ni a
qué versión volver.

## Secretos

Ninguna credencial vive en el repositorio, en las imágenes ni en el Dockerfile. Se guardan en Secret Manager y Cloud Run las inyecta como variables de entorno con `--set-secrets`, de modo que la configuración de la revisión guarda una referencia al secreto y no su valor.

Son ocho, y cada servicio lee solo los suyos:

| Secreto | Qué es | Lo lee |
|---|---|---|
| `verdeazul-db-url` | Cadena de `app_rw` en la base principal | backend |
| `verdeazul-bitacora-lectura-url` | Cadena de `log_reader` en la bitácora | backend |
| `llave-busqueda-cedula` | HMAC para buscar por cédula sin guardarla en claro | backend |
| `llave-cifrado-datos` | AES-256-GCM para cédula, teléfono y secreto TOTP | backend |
| `llave-firma-certificados` | Llave privada Ed25519 de los certificados | backend |
| `verdeazul-outbox-url` | Cadena de `outbox_rw` en la base principal | transmisor |
| `verdeazul-bitacora-escritura-url` | Cadena de `log_writer` en la bitácora | transmisor |
| `llave-cadena-bitacora` | HMAC de la cadena de la bitácora | transmisor |

El backend y el transmisor corren cada uno con su propia cuenta de servicio, que solo puede leer sus secretos. Sin ella, Cloud Run usaría la cuenta por omisión de Compute, que tiene permisos de Editor sobre todo el proyecto.

La capa gratuita cubre seis versiones de secreto activas. Las dos de más cuestan unos centavos al mes y salen de los créditos; el enunciado pide la capa gratuita para Cloud Run y Neon. Al crear una versión nueva de un secreto hay que deshabilitar la anterior, para no sumar más.

## Versiones publicadas

Cada etiqueta es el commit del que salió la imagen, así que `git show <etiqueta>` lleva al código exacto. Las imágenes viven en `us-east4-docker.pkg.dev/verdeazul-g4/verdeazul`.

| Etiqueta | Imágenes | Fecha | Qué trajo |
|---|---|---|---|
| `72ba002` | api, policies, edge | 2026-11-10 | PR #17: el verificador ve las mediciones. **Es la que corre hoy** |
| `129ffba` | api, policies, edge | 2026-11-10 | PR #16: certificación, O1 fincas, O2 períodos y O3 mediciones |
| `8a1cd06` | api, policies, edge | 2026-11-10 | PR #15: identidad, O6, O9 y O10, y el borde con su propia cuenta de servicio |
| `bdec178` | api, policies, edge | 2026-11-09 | Despliegue de `develop` con el PR #13 |
| `d2f1d2e` | api, policies, edge | 2026-11-09 | El grupo de conexiones aguanta que Cloud Run y Neon se duerman |
| `8653dbb` | api, policies, edge | 2026-11-09 | Primer despliegue del backend con el motor como contenedor adjunto |
| `d4cc04b` | edge | 2026-11-09 | Primer despliegue: solo el borde |

Cada despliegue agrega una fila arriba. La lista completa, por si esta tabla se atrasa:

```bash
gcloud artifacts docker tags list us-east4-docker.pkg.dev/verdeazul-g4/verdeazul
```

La versión que está corriendo sale al pie de cada página del borde («versión» y la etiqueta) y en el campo `version` de `/salud` del backend.

## Equipo

Grupo 4: Meibel Ceciliano, Carlos Contreras, Ludwin Ramos, Henry Núñez, Adriel Chaves.

Profesor: MSc. Andrés F. Vargas Rivera.

El trabajo está repartido en cinco partes con un dueño cada una: plataforma y despliegue, identidad y cuentas, motor de autorización, dominio de certificación, y certificados firmados con bitácora. Quién hace qué y qué necesita de los demás está en [contracts/README.md](contracts/README.md). La defensa es individual, así que cada quien le da un recorrido de su parte al resto antes de la presentación.
