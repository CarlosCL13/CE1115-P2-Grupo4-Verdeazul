# Desviaciones de la implementación respecto al diseño de la Parte 1

Documento de trabajo del Grupo 4. Alimenta la sección 5 del informe de la Parte 2.

El diseño que entregamos en octubre asumía servidores propios y una restricción del cliente de usar solo software libre. La Parte 2 impone una plataforma concreta: Cloud Run, Neon, Secret Manager y Artifact Registry, con imágenes de Docker. Casi todas las desviaciones que siguen salen de ese cambio de supuesto.

El modelo de control de acceso no cambia. Los ocho roles, los once objetos, las once operaciones y las condiciones C1 a C11 se implementan tal como se diseñaron. Lo que cambia es con qué se construye, y en tres casos eso tiene consecuencias de seguridad que conviene decir en voz alta.

## Resumen

| ID | Qué cambió | Origen |
|---|---|---|
| D-01 | La plataforma de alojamiento es software propietario | Enunciado P2 §3.1 |
| D-02 | Docker en lugar de Podman sin privilegios | Enunciado P2 §3.2 |
| D-03 | Secret Manager en lugar de OpenBao | Enunciado P2 §3.1 |
| D-04 | Cloud Run termina el TLS en lugar de nginx propio | Enunciado P2 §3.1 |
| D-05 | Autenticación propia con Argon2id en lugar de Keycloak | Decisión del equipo |
| D-06 | OPA como contenedor adjunto en lugar de servicio en red privada | Restricción de Cloud Run |
| D-07 | Las reglas de continuidad DI-01 a DI-04 se reescriben | Límites del plan gratuito de Neon |
| D-08 | Sin restricción de acceso por dirección de origen | Límites del plan gratuito de Neon |
| D-09 | La verificación de un certificado no exige sesión | Enunciado P2 §2.2 |
| D-10 | Firma digital de certificados, que P1 no diseñó | Enunciado P2 §2.2 |
| D-11 | Los trabajos programados se consolidan en un solo punto de entrada | Capa gratuita de Cloud Scheduler |
| D-12 | El conjunto de herramientas de análisis se reduce | Tiempo disponible |
| D-13 | El segundo factor es obligatorio solo para cuatro roles | Decisión del equipo |
| D-14 | El aviso al titular de RC-01 no llega por correo | Alcance |
| D-15 | Las solicitudes de cambio de cuenta tienen dueño fuera de la matriz | Hueco del diseño |
| D-16 | Las cuentas nuevas nacen con una contraseña temporal | Hueco del diseño |
| D-17 | Un período se crea abriéndolo, y `/abrir` reabre uno cerrado | Hueco del diseño |
| D-18 | El técnico solo registra mediciones en su zona | Refuerzo de la matriz |
| D-19 | El transmisor corre cada media hora, no casi en tiempo real | Límites del plan gratuito de Neon |

## D-01. La plataforma de alojamiento es software propietario

El Informe de políticas recoge una restricción explícita de la cliente: presupuesto únicamente para software libre, que quedó como requerimiento R11 y como regla operativa LG-08. Cloud Run, Neon, Secret Manager y Artifact Registry son servicios propietarios.

Lo conservado es que todo el software que escribimos y todas sus dependencias siguen teniendo licencia libre: Python, FastAPI, PostgreSQL, PostGIS, OPA. Lo que se volvió propietario es la capa de alojamiento, y los cuatro servicios tienen capa gratuita suficiente para este sistema, así que la restricción de presupuesto se respeta aunque la de licencia no.

La implicación de seguridad ya estaba anticipada en el diseño. El riesgo residual RR-02 decía que el proveedor de nube, o una cuenta de administración comprometida, podría acceder a los datos o a las máquinas, y se aceptaba porque la cliente no tiene servidores propios. Ese riesgo crece al pasar de alquilar máquinas a usar servicios gestionados, porque ahora el proveedor también custodia los secretos y ejecuta el motor de base de datos. Las mitigaciones que P1 ya proponía siguen aplicando: cifrado de los datos personales dentro de la aplicación, de modo que la base guarde texto cifrado, y segundo factor en las cuentas de administración de la nube.

## D-02. Docker en lugar de Podman sin privilegios

El documento de arquitectura eligió Podman y descartó Docker Engine porque su servicio central corre con privilegios de administrador. El enunciado exige imágenes de Docker publicadas en Artifact Registry.

El motivo del descarte desaparece en este despliegue. El demonio de Docker existe solo en la máquina donde se construye la imagen; en producción quien ejecuta el contenedor es Cloud Run, que no usa Docker y aísla cada instancia en su propio entorno. La preocupación real de P1 era el mínimo privilegio en la ejecución, y eso se conserva con una línea del Dockerfile: el contenedor declara un usuario sin privilegios y no corre como root. El enunciado revisa justamente eso.

## D-03. Secret Manager en lugar de OpenBao

Esta es la desviación con más consecuencias y vale la pena desglosarla, porque OpenBao hacía tres cosas que Secret Manager no hace. P1 había descartado explícitamente los gestores de secretos de los proveedores de nube por crear dependencia del proveedor, y el enunciado los impone.

Lo que se mantiene es lo esencial: ninguna credencial vive en el repositorio ni en las imágenes, cada servicio se autentica con su propia identidad y solo puede leer los secretos que necesita, y el acceso queda registrado.

**Credenciales de base de datos estáticas.** OpenBao generaba credenciales con vida limitada que se renovaban solas, de modo que no existía una contraseña fija que robar. Secret Manager guarda valores estáticos. La aplicación usa ahora una contraseña de Neon guardada como secreto, con rotación manual. Si esa credencial se filtra, sigue sirviendo hasta que alguien la cambie, mientras que antes caducaba en 24 horas. Lo compensamos con rotación programada y con que el rol de aplicación tiene privilegios mínimos: no es dueño de las tablas y no puede alterar el esquema.

**El HMAC de la bitácora se calcula en la aplicación.** El motor Transit de OpenBao firmaba cada eslabón de la cadena sin que la llave saliera nunca de él, así que ninguna cuenta de base de datos ni el propio transmisor la conocían. Ahora la llave llega al proceso del transmisor desde Secret Manager y el cálculo ocurre en memoria. Quien comprometa ese proceso puede reescribir la cadena completa y no se notaría. La garantía baja de "nadie con acceso a la base puede falsificar el historial" a "nadie con acceso a la base, pero sí quien controle el transmisor". Lo compensan parcialmente dos cosas que sí se mantienen: la bitácora vive en una instancia de Neon separada donde el transmisor solo puede insertar, y la copia periódica a un almacenamiento externo con retención permite comparar.

**El cifrado de datos personales también pasa a la aplicación.** La cédula y el teléfono se siguen cifrando antes de guardarse, como exige LG-05, y la búsqueda por cédula sigue usando un valor derivado en lugar del dato. La diferencia es la misma: la llave está en el proceso en lugar de estar encerrada en un motor que solo responde operaciones.

## D-04. Cloud Run termina el TLS

La arquitectura ponía nginx como único punto de entrada desde internet, encargado de terminar TLS 1.3, limitar tamaño y tasa de solicitudes y agregar las cabeceras de seguridad. Cloud Run asigna un dominio con TLS automático y termina la conexión antes de que llegue al contenedor.

La frontera F1 se conserva, pero la aplica Google. Lo que sí sigue siendo nuestro son las cabeceras de seguridad, la política CSP y los límites de tamaño, que se mueven al servicio de borde. La frontera F2, entre el borde y el backend, se implementa con los permisos de Cloud Run: el servicio de backend no acepta invocaciones anónimas y solo la cuenta de servicio del borde puede llamarlo. Un navegador que conozca la URL del backend recibe un rechazo antes de que nuestro código se ejecute, que es más fuerte que la separación por red privada que habíamos diseñado.

Queda fuera de nuestro control la versión de TLS y el conjunto de cifrados. Cloud Run acepta TLS 1.2 y 1.3; P1 exigía solo 1.3.

## D-05. Autenticación propia en lugar de Keycloak

P1 eligió Keycloak como único emisor de identidades y argumentó, con razón, que escribir la autenticación uno mismo es un error frecuente y costoso. Lo cambiamos de todas formas, y el argumento es de operación: Keycloak necesita su propia base de datos, arranca lento, consume memoria y expone una consola de administración que había que bloquear. En un servicio que escala a cero y en una capa gratuita, eso es desproporcionado.

La autenticación pasa al backend con Argon2id y los mismos parámetros que P1 fijó siguiendo a la OWASP: variante id, sal por usuario, 19 MiB de memoria, dos iteraciones y un hilo. Se conserva también el diseño de sesión, que era lo valioso: cookie opaca con los atributos HttpOnly, Secure y SameSite, sesión en la base de datos, revocación inmediata al dar de baja o cambiar de rol, e identificador nuevo al iniciar sesión. Las reglas de contraseña CO-01 a CO-05 y el bloqueo por intentos fallidos RC-01 se configuran en la aplicación.

Lo que se pierde es el segundo factor. P1 exigía claves de acceso obligatorias para las direcciones, el personal administrativo y los verificadores, y contraseña con TOTP para el resto. Implementar WebAuthn correctamente no cabe en el tiempo disponible. Mantenemos TOTP para los roles que pueden aprobar, emitir o cambiar permisos, y la reautenticación en acciones críticas que P1 pedía; las claves de acceso quedan documentadas como pendientes. Esto deja abierta la amenaza AE-02, el atacante que entra con contraseñas filtradas de otros sitios, mitigada solo por la lista de contraseñas prohibidas de CO-02.

## D-06. OPA como contenedor adjunto

El motor de políticas seguía siendo un componente aparte que solo aceptaba consultas desde la red privada. En Cloud Run no hay red privada entre servicios sin configuración adicional de red que la capa gratuita no cubre bien.

OPA se despliega como contenedor adjunto dentro del mismo servicio que el backend, escuchando en la interfaz local. La separación entre el punto de aplicación y el punto de decisión se conserva, que era lo que importaba del diseño: las políticas siguen siendo código en Rego, versionado, con pruebas propias, y el backend sigue sin poder conceder lo que el motor deniega. El paquete de políticas se construye dentro de la imagen y lleva la misma etiqueta de versión, así que sigue siendo posible saber qué reglas están corriendo.

La frontera F4 cambia de naturaleza: ya no es una frontera de red sino de proceso. Quien comprometa el contenedor del backend está en la misma instancia que el motor.

## D-07. Las reglas de continuidad se reescriben

DI-01 a DI-04 prometían recuperación en dos horas, respaldos al menos cada hora, regla 3-2-1 con una copia aislada que no se puede borrar durante su retención, y pérdida máxima de una hora de registros. Fueron escritas para dos máquinas propias con réplica en espera.

Neon en plan gratuito ofrece restauración continua a cualquier punto de las últimas seis horas. Eso cumple DI-04 con margen, porque dentro de esa ventana la pérdida de datos es prácticamente nula, y cumple DI-01 porque restaurar es inmediato. Lo que no cubre es la retención: seis horas no sirven para BI-04 ni para LG-06, que exigen conservar diez años lo ligado a un certificado. Las instantáneas programadas son de plan pago.

La parte que seguimos debiendo la resolvemos con un volcado periódico de ambas bases a un depósito de Cloud Storage con retención bloqueada. Eso recupera la tercera copia fuera de la cuenta de Neon (DI-02), la copia que no se puede borrar (DI-03) y la copia separada de la bitácora que P1 pedía en BI-03.

Se pierden la réplica en espera y el ensayo semestral de recuperación cronometrado. Neon no expone conmutación manual en plan gratuito, y la disponibilidad del servicio deja de estar bajo nuestro control, lo que ensancha el riesgo residual RR-04.

## D-08. Sin restricción por dirección de origen

La lista de direcciones permitidas y el acceso por red privada virtual son funciones de plan pago en Neon, y el acceso público de internet no se puede apagar sin una de las dos. La base de datos acepta conexiones desde cualquier punto de internet y la única barrera es la credencial.

Vale aclarar que aunque fueran gratuitas tampoco encajarían bien: Cloud Run no sale a internet por direcciones estables sin configurar salida directa a una red virtual y traducción de direcciones, así que una lista de permitidos exigiría infraestructura adicional.

La implicación es directa. No hay segunda línea de defensa a nivel de red, de modo que todo el peso recae sobre que la credencial no se filtre. Eso eleva la importancia de que nada se versione y de que el rol de aplicación tenga privilegios mínimos. Lo que sí protege la plataforma es que exige TLS en toda conexión y autentica con SCRAM, lo que impide capturar la credencial en tránsito.

## D-09. La verificación de un certificado no exige sesión

El diseño sostenía el principio de mediación completa: ninguna ruta, trabajo programado ni generación de reportes salta el punto de aplicación. El enunciado pide que cualquiera pueda comprobar un certificado sin acceso al sistema, porque un certificado de carbono circula fuera de Verdeazul y vale dinero.

El punto de verificación es público y no pide sesión. No es una excepción al control de acceso porque no consulta la base de datos ni revela nada: recibe un archivo que trae quien verifica, comprueba la firma con la clave pública incrustada en ese mismo archivo y responde si es válido. No hay objeto protegido en juego.

Las medidas que lo acotan son límite de tasa por origen, tamaño máximo del archivo y una respuesta que solo dice si la firma es válida, sin detalles internos.

## D-10. Firma digital de certificados

P1 no diseñó esto. La Ley 8454 aparecía en el marco regulatorio señalando que los certificados y los reportes se pueden firmar digitalmente, pero no había formato, llave ni procedimiento de verificación. El enunciado lo exige.

Cada certificado se emite como un documento firmado con Ed25519. La clave privada vive en Secret Manager y la pública viaja dentro del documento, de modo que cualquiera puede comprobar que el contenido no fue alterado. El evento de emisión en la bitácora incorpora la huella de la clave usada, que es un campo nuevo respecto a la Tabla 4.2 de P1.

Hay un límite que conviene declarar antes de que lo pregunten. Una clave pública que viaja en el propio documento prueba que el contenido no cambió desde que se firmó, pero no prueba quién firmó: alguien podría generar su propio par de claves y firmar un certificado falso que verificaría igual de bien. Para cerrar eso hace falta publicar la huella de la clave de Verdeazul por un canal independiente, contra el cual el verificador compara. El punto de verificación público lo hace automáticamente; quien verifique con herramientas propias tiene que compararla a mano.

## D-11. Los trabajos programados se consolidan

P1 preveía varios procesos periódicos: el transmisor que copia eventos a la bitácora, la desactivación de asignaciones y autorizaciones vencidas que exige HBAC-03, el reporte semanal de volumen de HBAC-02 y la comprobación mensual de la cadena. En la arquitectura original eran servicios o tareas independientes.

Cloud Run cobra por instancia activa y la capa gratuita de Cloud Scheduler permite pocos trabajos, así que todos cuelgan de un único punto de entrada que el planificador invoca y que ejecuta la tarea que corresponda según la hora. Ese punto exige autenticación de la cuenta de servicio del planificador y no es accesible desde internet.

El efecto es que una falla en ese punto detiene todas las tareas periódicas a la vez, en lugar de una sola. Lo compensa que el patrón de bandeja de salida ya estaba diseñado para tolerarlo: si el transmisor se atrasa, los eventos se acumulan en la tabla de salida sin perderse y el retraso se puede medir.

## D-12. Menos herramientas de análisis

Cada ficha de tecnología de P1 listaba herramientas de análisis: Bandit, Semgrep, pip-audit, Trivy, OWASP ZAP, gitleaks, hadolint, Gixy, Regal y testssl.sh. En tres semanas no se configuran todas con sentido.

Se mantienen tres. Dependabot, que el enunciado exige y que cubre lo que hacían pip-audit y la revisión de dependencias de npm. Un detector de secretos en el repositorio, porque una credencial versionada anula por completo el criterio de gestión de secretos del enunciado y porque el historial de git conserva lo que se borra. Y las pruebas automatizadas de autorización por cada celda de la matriz, que P1 ya exigía y que son la evidencia de la tabla de cobertura.

Las demás quedan documentadas como pendientes para una operación real.

## D-13. El segundo factor es obligatorio solo para cuatro roles

La Tabla 7.1 del Informe de políticas pedía segundo factor a los ocho perfiles, con llave de acceso preferida y TOTP como alternativa. D-05 ya explica por qué no hay llaves de acceso. Esta desviación es la otra mitad.

El segundo factor es obligatorio para Dirección General, Dirección de Certificación, Personal Administrativo y Verificador, que son los roles que aprueban, emiten o cambian permisos. Sin él no pasan de la pantalla de activación, que es lo que CU-04 pedía ("antes del primer uso registra su segundo factor"). Para técnico de campo, auditor externo, dueño de finca y tercero autorizado es opcional, y una vez que alguien lo activa se le pide siempre.

La razón es el uso real. El técnico trabaja en campo con conexión irregular, y el dueño y el tercero son externos que entran pocas veces al año. La implicación es que en esos cuatro roles una contraseña filtrada basta para entrar (AE-02). Lo acotan la lista de contraseñas prohibidas y la consulta a filtraciones conocidas de CO-02, el bloqueo de RC-01, y que esos roles solo leen lo suyo: ninguno aprueba, emite ni cambia permisos.

Lo que sí se conserva de la Tabla 7.1 es el cierre por inactividad de cada perfil (15, 30 y 60 minutos) y la reautenticación antes de cambiar roles, abrir o cerrar períodos y aprobar. El conjunto de roles obligados es una sola constante en `services/api/app/auth/totp.py`, así que extenderlo a los ocho es cambiar una línea.

Los códigos de recuperación de RC-02 están implementados: ocho de un solo uso al activar el factor, guardados como huella SHA-256. La recuperación por videollamada de RC-03 es un procedimiento humano y queda fuera del sistema.

## D-14. El aviso al titular de RC-01 no llega por correo

RC-01 dice "tras 10 intentos fallidos, bloqueo de 30 minutos y aviso al titular". El bloqueo está implementado tal cual, con la espera creciente desde el quinto intento (15 segundos, que se duplican hasta el noveno). El sistema no envía correos, así que el aviso toma dos formas. Cada bloqueo queda como evento `CUENTA_BLOQUEADA` en la bitácora, y la próxima vez que el titular entra la pantalla le dice cuántos intentos fallidos hubo desde su último ingreso.

La implicación es que el titular se entera cuando vuelve a entrar, no en el momento. Agregar un correo es enviar un mensaje desde el mismo punto donde hoy se registra el evento.

## D-15. Las solicitudes de cambio de cuenta tienen dueño fuera de la matriz

C10 exige que exista una aprobación previa de Dirección General antes de que el Personal Administrativo cree o modifique una cuenta. Esa aprobación vive en la tabla `solicitudes_rol`, que no es un objeto de la matriz, igual que `ventanas_auditoria`. Así que la matriz no dice quién puede crear una solicitud ni quién puede aprobarla.

Lo decidimos con CU-01 y CU-03 de P1. El Personal Administrativo registra la solicitud que hizo la jefatura, la Dirección General la aprueba o la rechaza, y el Personal Administrativo la aplica. La base de datos impide que quien pide apruebe, que quien aprueba aplique, y que nadie pida o apruebe sobre su propia cuenta. El servidor impone quién hace cada paso con la misma regla que el motor, negando por omisión y registrando el intento.

La 004 solo modelaba el cambio de rol de una cuenta existente, pero C10 también gobierna el alta (C) y la baja (M). La migración 011 agrega el tipo de solicitud y deja `cuenta_afectada` vacía hasta que el alta se aplica, porque la cuenta todavía no existe cuando se pide.

Hay una lectura de la matriz que conviene explicar. El Personal Administrativo tiene L·C10 sobre O9, es decir, solo lee cuentas con aprobación previa. Lo implementamos literal, y ese rol ve una cuenta únicamente mientras tiene un cambio aprobado por Dirección General pendiente de aplicar. Para ver el estado de sus solicitudes usa la lista de solicitudes, que no expone las cuentas.

Al aplicar un cambio de rol se revocan las asignaciones de zona de la cuenta, por CU-10 ("primero se revoca y después se asigna"), y en el cambio de rol y en la baja se cierran al instante todas sus sesiones, por SE-01 y CU-11.

## D-16. Las cuentas nuevas nacen con una contraseña temporal

P1 no dijo cómo recibe alguien su primera contraseña. Con Keycloak eso lo resolvía el correo de activación. Aquí el Personal Administrativo, al aplicar el alta, recibe una contraseña temporal aleatoria de 20 caracteres que se muestra una sola vez y que entrega a la persona.

La cuenta nace marcada con `debe_cambiar`. Con la contraseña temporal se puede entrar, pero la sesión solo sirve para activar el segundo factor (si el rol lo exige) y cambiarla. El administrativo conoce la temporal pero no la definitiva, y tampoco tiene el segundo factor, así que no puede usar la cuenta que creó.

## D-17. Un período se crea abriéndolo

La matriz le da a Dirección de Certificación las operaciones Ab (abrir) y Cr (cerrar) sobre O2, y el contrato 04 listaba `POST /periodos/{id}/abrir`. Pero un período no se puede abrir si no existe, y ningún endpoint lo creaba.

`POST /periodos` crea un período nuevo y nace ABIERTO, bajo la operación Ab. `POST /periodos/{id}/abrir` queda para reabrir uno cerrado, y falla con 409 si ya está abierto. Las dos piden reautenticación (Tabla 7.1 de P1), igual que cerrar. Cerrar solo se permite cuando no quedan mediciones REGISTRADAS en el período. Las DEVUELTAS no cuentan, porque su autor no puede corregirlas (no se modifican, se enmiendan) y esperarlas bloquearía el cierre para siempre.

Ninguna celda de la matriz cambia, y la operación sigue siendo Ab para el mismo rol. La implicación es que reabrir un período cerrado vuelve a habilitar C2 y deja de cumplirse C11 mientras tanto, así que quien lo reabre tiene que saber que hay enmiendas en curso. Queda registrado como `PERIODO_ABIERTO` en la bitácora, con la etiqueta.

## D-18. El técnico solo registra mediciones en su zona

La matriz le da al Técnico de campo C sobre O3 con la condición C2 (período abierto) y no menciona C1. Leída literal, un técnico podría registrar una medición de una finca de una zona que no tiene asignada, y solo el verificador lo vería después.

Lo reforzamos. Al registrar, el servidor además le pregunta al motor si el técnico puede leer esa finca (L sobre O1, que sí lleva C1), y si no, niega y registra el intento. No amplía ningún permiso, solo agrega una restricción, que es la dirección que la matriz permite (ABAC quita permisos, nunca los agrega). La implicación de seguridad es que una cuenta de técnico comprometida no puede inyectar mediciones en fincas ajenas.

## D-19. El transmisor corre cada media hora

P1 describía un transmisor que copia cada evento a la bitácora apenas ocurre, con un aviso si el retraso pasaba de cinco minutos.

Aquí lo invoca Cloud Scheduler cada 30 minutos. Cada corrida despierta el cómputo de las dos bases de Neon, que después tarda cinco minutos en volver a dormirse. Con una corrida cada cinco minutos las bases no se dormirían nunca, y una base despierta todo el mes gasta unas 180 horas de cómputo, cuando el plan gratuito da 100 por proyecto. Al agotarlas, Neon suspende la base y el sistema deja de abrir.

La implicación es que un evento puede tardar hasta media hora en aparecer en la bitácora. No se pierde: queda en la bandeja de salida, que se escribe en la misma transacción que la operación, y la hora que se registra es la de la operación, no la de la copia. Lo que se pierde es la detección temprana: durante esa media hora, alguien con acceso a la base principal podría intentar alterar un evento antes de que se selle. Lo acota la migración 012, que le quita a la aplicación el permiso de modificar la bandeja, y para la presentación el transmisor se puede invocar a mano.

## Decisiones aún abiertas

Estas no son desviaciones todavía. Hay que resolverlas y moverlas arriba o descartarlas.

**La interfaz.** P1 eligió Angular. El enunciado dice que la interfaz no se evalúa y que conviene invertir el tiempo en seguridad. Servir plantillas desde el servicio de borde eliminaría la cadena de dependencias de npm y una imagen completa, a costa de la usabilidad que motivó la elección original.

**Alcance de HBAC-02.** El reporte semanal de volumen anómalo no es una celda de la matriz, así que no cuenta para la cobertura, pero sí es una política documentada en P1 y en el Informe de políticas. Hay que decidir si se implementa en versión mínima o se declara fuera de alcance.

**El portal de auditores.** La minuta comprometió un portal propio con reportes en PDF. El permiso de exportar sí hay que implementarlo porque es una celda de la matriz. Que sea un portal separado o una sección de la misma aplicación está por decidir.
