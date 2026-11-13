# Contratos

Un contrato dice cómo se llama algo y qué devuelve, y se escribe antes de que
exista el código que lo cumple.

Somos cinco trabajando en paralelo durante tres semanas. Sin contratos, cuatro
esperan a que una termine. Con contratos, los cinco escriben código el mismo día
y las piezas encajan al final porque la forma se acordó antes.

| Contrato | Qué congela | Quién lo necesita |
|---|---|---|
| [01-esquema.md](01-esquema.md) | Qué tablas y columnas existen | Todos |
| [02-autorizacion.md](02-autorizacion.md) | Cómo se pregunta si un sujeto puede hacer algo | Personas 1, 2, 4 y 5 |
| [03-evento-bitacora.md](03-evento-bitacora.md) | Qué campos lleva un registro de auditoría | Todos |
| [04-endpoints.md](04-endpoints.md) | Qué ruta implementa cada casilla y dónde vive | Todos |
| [05-sesion.md](05-sesion.md) | Cómo sabe un endpoint quién pregunta, y cómo niega | Todos |

[matriz.md](matriz.md) no es un contrato. Es la matriz de la Parte 1 transcrita
para no tener que abrir el PDF, y es la referencia que se consulta a diario.

## La regla

Un contrato se cambia por pull request, nunca de palabra. Quien lo cambie avisa
en el chat del grupo, porque la gente que ya escribió código contra él se entera
cuando le falla algo, no cuando el archivo cambia.

## Dónde estamos (12 de noviembre)

La entrega es el 19 de noviembre. El plan de las secciones de abajo es el
original; esta sección dice cómo quedó y qué falta.

### Lo que ya está

| Frente | Quién | Qué quedó |
|---|---|---|
| Plataforma | Carlos | Despliegue automático sin llaves, Secret Manager, imágenes versionadas, la base con sus roles y los datos de prueba, el CI |
| Identidad | Henry | Login con Argon2id, segundo factor, sesiones y bloqueo. O6, O9 y O10 |
| Motor | Ludwin | Las 88 celdas y las condiciones C1 a C11 en Rego, con 977 pruebas en el CI |
| Certificación | Henry | O1 fincas, O2 períodos y O3 mediciones |
| Bitácora y transmisor | Adriel | O11, y las cuatro tareas: `transmitir`, `vencer`, `cadena` y `volcado` (migración 014, depósito de Cloud Storage) |
| Enmiendas y asignaciones | Adriel | O4 con C4, C5 y C11; O8 con revocar el mismo día |
| Dependencias | Adriel | Alerta de Dependabot atendida: CVE-2025-62727 ([docs/Dependabot.md](../docs/Dependabot.md)) |

Van **46 de los 57 endpoints** (13 de noviembre). Faltan O5 certificados y O7
consentimientos, que son de Meibel. Cuáles, uno por uno, está en la última
columna de [04-endpoints.md](04-endpoints.md). El material del informe está en
[docs/Informe_P2.md](../docs/Informe_P2.md).

### Lo que falta

Todavía no tiene dueño: Meibel y Adriel se lo reparten. Va en orden de
prioridad. Lo de arriba se muestra en la presentación o vale más puntos; lo de
abajo son celdas de la matriz, que descuentan de a poco.

| # | Qué | Endpoints | Por qué va ahí | Necesita antes |
|---|---|---|---|---|
| 1 | Emitir y verificar certificados (O5) | `POST /certificados/{id}/emitir`, `POST /publico/verificar` | Son los 15 puntos de certificados y §6.4 de la presentación: emitir, verificar, y que un certificado alterado falle | Lista: `config.LLAVE_FIRMA_CERTIFICADOS` |
| 2 | Transmisor: `transmitir` | `POST /tareas/transmitir` | Los eventos ya se registran, pero se quedan en la bandeja de salida y la bitácora está vacía. §6.5 pide mostrarla | Listo: ver [services/transmisor/README.md](../services/transmisor/README.md) |
| 3 | O7 consentimientos | los 4 | Sin esto el tercero autorizado no ve ningún certificado (C9) | — |
| 3 | O11 bitácora | `GET /bitacora`, `GET /bitacora/exportar` | Es donde se ven los eventos | `transmitir` |
| 4 | O4 enmiendas | los 7 | Siete operaciones de la matriz, con C4, C5 y C11 | — (O3 ya existe) |
| 5 | El resto de O5 | listar, ver, anular, exportar | Celdas de la matriz | Emitir |
| 6 | O8 asignaciones | los 4 | Celdas de la matriz | — |
| 7 | Transmisor: `vencer` y `cadena` | 2 tareas | «Revocar el mismo día» de §4, y detectar si alguien alteró la bitácora | `transmitir` |
| — | Transmisor: `volcado` | 1 tarea | Es el respaldo con retención que D-03 y D-07 prometen como compensación (BI-03 y BI-04 de P1). Si no da el tiempo se puede recortar, pero entonces hay que corregir esas dos desviaciones, que hoy lo dan por hecho | — |
| — | `GET /authz/explicar` | 1 | Opcional, para la presentación | — |

Si sirve como punto de partida, una forma pareja de partirlo en dos es por
tema: **certificados** (O5 completo, O7 y O8) y **bitácora y enmiendas** (el
transmisor, O11 y O4). Así cada dependencia queda en manos de la misma persona:
O5 necesita O7, y O11 necesita el transmisor.

Cuando lo decidan, díganlo en el chat del grupo, para que nadie arranque lo
mismo dos veces.

### Lo que ya dejó listo Carlos

- **Para certificados:** la llave privada de firma en Secret Manager, que el
  backend lee como `config.LLAVE_FIRMA_CERTIFICADOS`. En local sirve cualquier
  llave de prueba (ver `.env.example`). La base no deja cambiar lo firmado de
  un certificado, solo lo necesario para anularlo (migración 012). La
  verificación pública recibe el archivo y no consulta la base (D-09).
- **Para la bitácora:** el transmisor con su despliegue, sus conexiones, sus
  permisos y la columna donde lleva la cuenta de la cadena. Cómo debería
  funcionar `transmitir` está en
  [services/transmisor/README.md](../services/transmisor/README.md).

### Lo que sigue haciendo Carlos

- Activa el Scheduler cuando `transmitir` funcione. Corre cada 30 minutos, no
  más seguido: cada corrida despierta a Neon, y el plan gratuito tiene horas
  de cómputo contadas (§3.1). Es una desviación de P1, registrada como D-19.
- Le da al transmisor `log_reader` cuando se escriba `cadena`, y el permiso de
  revocar cuando se escriba `vencer`.
- Aplica las migraciones nuevas, porque `app_migrate` solo lo tiene él. Quien
  necesite una tabla o una columna escribe el archivo en `db/migrations/`
  dentro de su PR y le avisa.

### Cómo arrancar

- **Copiar el patrón de Henry.** El backend en
  `services/api/app/certificacion/` (tiene su propio README): `rutas.py`, las
  consultas aparte, `autorizar()` y `consultar()` de
  `app/auth/dependencias.py`, y una línea en `main.py`. Las pantallas en
  `services/edge/app/certificacion.py` y `services/edge/templates/certificacion/`.
- **Leer los contratos 02 y 05.** El 02 dice qué atributos manda cada
  condición; el 05, cómo sabe un endpoint quién pregunta. Para reautenticar
  antes de una acción grave ya existe `exigir_reautenticacion()`.
- **Usar los datos de prueba.** Al final de `db/semilla.sql` hay una tabla con
  qué fila sirve para probar cada condición. Las fincas 1 y 3 se superponen a
  propósito, para C6.
- **Armar el `.env`** con [db/README.md](../db/README.md). Las cadenas y las
  llaves se leen de Secret Manager, nunca de un chat. Si todavía no tienen
  acceso al proyecto de Google Cloud, pídanselo a Carlos.
- **Pedirle a Henry las cuentas de prueba.** Tiene la contraseña de cada una.
  `dg`, `dc`, `pa`, `vf1` y `vf2` piden además el código del celular: para
  esas Henry tiene una línea `otpauth://` que se carga en cualquier aplicación
  autenticadora, así cada quien genera sus códigos. Sin `vf1` o `vf2` no se
  puede probar emitir, que es del verificador.
- **Todo por rama y pull request a `develop`.** El merge se habilita solo
  cuando los checks pasan.
- **Las pruebas nuevas, en el CI.** El job «Identidad contra PostgreSQL» de
  `.github/workflows/ci.yml` corre solo `tests/identidad` y
  `tests/certificacion`. Si agregan una carpeta de pruebas, agreguen su línea
  ahí; si no, el CI no la corre.

### Lo que hay que leer de cada tema

**Certificados (O5, O7 y O8)**

- Las filas de O5 en [04-endpoints.md](04-endpoints.md). `emitir` es lo más
  delicado del proyecto: C6 se revisa dentro de la transacción con
  `ST_Intersects` y `pg_advisory_xact_lock`, porque dos verificadores emitiendo
  a la vez se pueden colar, y pide reautenticación.
- D-09 y D-10 en
  [docs/P2_Desviaciones_respecto_P1.md](../docs/P2_Desviaciones_respecto_P1.md):
  firma Ed25519, la clave pública dentro del documento, la huella de la clave
  en el evento de emisión, y una verificación que recibe el archivo, no toca la
  base y tiene límite de tasa y de tamaño.
- Qué manda cada condición, en el [contrato 02](02-autorizacion.md). C6:
  `medicion.estado`, `medicion.autor_id` y
  `contexto.poligono_traslapa_certificado_vigente`. C9:
  `autorizacion.tercero_id` y `autorizacion.vence`, que salen de
  `consentimientos`.
- O7 y O8 usan las tablas `consentimientos` y `asignaciones_zona` (migración
  007). C8 manda `finca.propietario_id`; C1 en O8 manda `finca.zona` con la zona
  de la asignación.
- Datos de prueba: la medición 5 es de la finca 3, que se cruza con la 1. El
  consentimiento 1 está vigente y el 2 vencido.

**Bitácora y enmiendas (transmisor, O11 y O4)**

- El transmisor: [services/transmisor/README.md](../services/transmisor/README.md),
  sobre todo «Cómo debería funcionar `transmitir`».
- O11: el backend ya tiene `bd.lectura_bitacora()`, que entra a la bitácora con
  `log_reader`, solo lectura. El auditor filtra con C7: `auditoria.inicio` y
  `auditoria.fin`.
- O4: las filas de O4 en [04-endpoints.md](04-endpoints.md). La máquina
  `SOLICITADA → REVISADA → CERRADA | DEVUELTA` va en `enmiendas/estados.py`, y
  el servidor no deja cerrar lo que no esté REVISADA. C4 manda
  `enmienda.solicitante_id`; C5, `enmienda.estado`, `enmienda.solicitante_id` y
  `enmienda.revisor_id`; C11, `medicion.autor_id` y `periodo.estado`. Aprobar
  pide reautenticación.
- Datos de prueba: la enmienda 1 está REVISADA, la pidió `tc1` y la revisó
  `vf1`. Para cerrarla hace falta una tercera persona.

### Revisión

**Sábado 15 de noviembre.** Para ese día, la emisión con firma en una rama, y
`transmitir` funcionando en local. Lo que no haya arrancado se reasigna ese
mismo día, porque después ya no hay margen.

## Cómo está dividido el trabajo

La división cambia a la mitad del proyecto. En la primera semana cada quien
levanta una pieza distinta, y casi nadie depende de nadie. De la segunda en
adelante todos hacen el mismo trabajo sobre objetos distintos: por cada objeto,
su tabla, sus endpoints, sus casillas de la matriz, sus pantallas, sus eventos
de bitácora y sus pruebas.

| | Semana 1 | Después |
|---|---|---|
| Persona 1 | Desplegar | O7 consentimientos, O8 asignaciones, O4 enmiendas |
| Persona 2 | Entrar | O6 datos personales, O9 cuentas, O10 credenciales |
| Persona 3 | Decidir | las condiciones C1 a C11 |
| Persona 4 | Guardar | O1 fincas, O2 períodos, O3 mediciones |
| Persona 5 | Firmar y registrar | O5 certificados, O11 bitácora |

## Persona 1: plataforma

Hace que lo que los demás escriben en su computadora funcione en internet, sin
que haya una sola contraseña escrita en un archivo. Crea el repositorio, arma el
proceso que al hacer `push` construye las imágenes y las sube, levanta los tres
servicios en Cloud Run, guarda las credenciales en Secret Manager y crea los
roles de base de datos para que la aplicación entre con permisos mínimos y nunca
como dueña.

Sus carpetas son `.github/`, `db/roles/`, los `Dockerfile`, y
`services/api/app/` en los archivos `main.py`, `config.py` y `bd.py`. Más tarde
`concesiones/` y `enmiendas/`.

Lo que los demás necesitan de ella: `config.py` y `bd.py` desde el primer día,
porque los cinco van a importarlos y no puede haber dos formas de abrir una
conexión. Y el despliegue funcionando antes de que nadie tenga mucho código, que
es la advertencia del enunciado y la razón de que esta parte vaya primero.

Lo que ella necesita: las tablas `periodo` y `medicion` de la persona 4 antes de
poder escribir O4 enmiendas. Mientras tanto trabaja contra el contrato 01.

## Persona 2: identidad

Se encarga de que el sistema sepa quién está del otro lado, y de que las
contraseñas no se puedan leer ni robándose la base de datos. Guarda las
contraseñas con Argon2id y sal, mantiene la sesión, pide un código de seis
dígitos del celular a los roles que aprueban o emiten, vuelve a pedir la
contraseña antes de las acciones graves y bloquea tras varios intentos fallidos.
También maneja los datos personales de los dueños de finca, que es lo más
delicado que guarda el sistema.

Sus carpetas son `services/api/app/auth/`, `personas/` y `cuentas/`, con sus
plantillas en `services/edge/templates/`.

Lo que los demás necesitan de ella: el objeto `Sujeto` del contrato 02, con id,
rol y zonas. Sin eso la persona 3 no tiene contra qué decidir. Puede entregarlo
con usuarios inventados a mano mientras la autenticación de verdad no esté.

Lo que ella necesita: casi nada. Es la parte que más temprano puede arrancar
sola, junto con la 5.

## Persona 3: autorización

Es el portero. Cada vez que alguien quiere hacer algo, su función responde sí o
no, y por qué. Traduce la matriz a código: 88 casillas, de las cuales 84 conceden
algo y 37 de esas lo conceden con una condición. Su regla es que lo que no está
concedido se niega, y que si el motor se cae la respuesta es no.

Sus carpetas son `services/api/app/authz/`, `services/policies/rego/` y
`tests/matriz/`. Es la única persona que casi no escribe SQL ni HTML.

Lo que los demás necesitan de ella: la función de autorización del contrato 02.
Ya está entregada como `servicio_consulta_autorizacion()`, con el motor
completo en Rego y las 968 combinaciones de la matriz probadas.

Lo que ella necesita: el `Sujeto` de la persona 2 para saber quién pregunta, y
los nombres de estado de la persona 4 para escribir las condiciones. C2 y C11
miran `periodo.estado`, C3 y C6 miran `medicion.estado`, C5 mira
`enmienda.estado`. Esos tres nombres se acuerdan una vez y no se cambian.

## Persona 4: certificación

Decide dónde viven los datos y escribe el flujo de trabajo de la empresa. Las
tablas de los once objetos con sus llaves e índices, y después la secuencia: se
registra una finca con su polígono, se abre un período de medición, un técnico
registra cuánta biomasa midió, un verificador la aprueba o la devuelve, y el
período se cierra. Cada paso tiene reglas. No se puede registrar una medición en
un período cerrado, ni cerrar un período con mediciones sin aprobar.

Sus carpetas son `services/api/app/certificacion/` y `db/migrations/`.

Lo que los demás necesitan de ella: las tablas, y rápido. Tres personas esperan.
La tabla `finca` con su columna `geometry(Polygon, 4326)` y su índice GiST tiene
que estar desde el principio, porque la condición C6 de la persona 5 depende de
ellos. Si la migración se atrasa, la semana 2 se convierte en semana 1 para tres
personas, y por eso esta parte la toma quien avance más rápido.

Lo que ella necesita: `bd.py` de la persona 1 y poco más.

## Persona 5: certificados y bitácora

Hace dos cosas que se parecen. Una prueba que un certificado es auténtico y la
otra prueba que nadie borró nada de la bitácora.

El certificado lo firma con una llave privada cuando Verdeazul lo emite.
Cualquiera de afuera verifica esa firma sin tener que confiar en Verdeazul ni
pedirle permiso, y si alguien le cambia una letra al documento la verificación
falla. En la bitácora, cada registro lleva un sello calculado a partir del
anterior, como eslabones de una cadena, así que borrar o editar uno del medio
hace que la cadena deje de cuadrar. También escribe el proceso que corre solo y
copia los eventos a la otra base de datos, la que la aplicación no puede
modificar.

Sus carpetas son `services/api/app/certificados/` y `bitacora/`,
`services/transmisor/` y `db/bitacora/`.

Lo que los demás necesitan de ella: `bitacora/registrar.py`, también el día uno
y también con el cuerpo vacío. Es la función que los otros cuatro llaman cada vez
que su código hace algo que deja rastro. Si llega tarde, los demás escriben
código que después hay que reescribir.

Lo que ella necesita: la tabla de bandeja de salida acordada en el contrato 03,
un cuarto rol de base de datos de la persona 1 para que el transmisor pueda leer
esa bandeja y marcar los eventos como enviados, y las tablas de O7 y O8 de la
persona 1 para la tarea que vence asignaciones y autorizaciones.

## Lo que hacen los cinco

Nadie tiene una parte de interfaz. Cada quien escribe las pantallas de sus
propios objetos, que son cuatro o cinco páginas HTML sencillas. El enunciado dice
que el diseño visual no se evalúa y que basta «una interfaz sobria que permita
ejercitar todos los permisos de la matriz».

Cada quien escribe las pruebas de lo suyo y su sección del informe. El atributo
que se evalúa este semestre es el uso de herramientas de ingeniería, y eso se
demuestra contando qué herramienta se usó y por qué.

## Dónde se chocan

Tres archivos los tocan varias personas, y conviene saberlo antes de que pase.

En `services/api/app/main.py` cada módulo expone una variable `router` y cada
quien agrega una sola línea para registrarlo. Un conflicto de una línea se
resuelve en diez segundos.

En `services/api/requirements.txt` las bibliotecas se agregan una por línea, en
orden alfabético, sin reordenar lo que ya está.

En `db/migrations/` escriben cuatro personas. El número del archivo lo toma quien
lo crea, y un archivo ya aplicado no se edita nunca. Si hace falta cambiar algo,
se escribe el siguiente.
