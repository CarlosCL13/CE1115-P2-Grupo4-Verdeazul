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
