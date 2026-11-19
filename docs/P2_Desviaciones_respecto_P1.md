# Desviaciones de la implementación respecto al diseño de la Parte 1

Documento de trabajo del Grupo 4. Alimenta la sección 5 del informe de la Parte 2.

El diseño que entregamos en octubre asumía servidores propios y una restricción del cliente de usar solo software libre. La Parte 2 (Proyecto 2) impone una plataforma concreta: Cloud Run, Neon, Secret Manager y Artifact Registry, con imágenes de Docker. Casi todas las desviaciones que siguen salen de ese cambio de supuesto.

El modelo de control de acceso no cambia. Los ocho roles, los once objetos, las once operaciones y las condiciones C1 a C11 se implementan tal como se diseñaron. Lo que cambia es con qué se construye, y en tres casos eso tiene consecuencias de seguridad que conviene decir en voz alta.

Cada desviación está escrita como un registro de decisión de arquitectura (ADR): el contexto, lo que se decidió y sus consecuencias. Entre paréntesis va su identificador D-XX, que es el que usan el código y los demás documentos.

## Resumen

| ADR | Qué cambió | Origen |
|---|---|---|
| 001 (D-01) | La plataforma de alojamiento es software propietario | Enunciado P2 §3.1 |
| 002 (D-02) | Docker en lugar de Podman sin privilegios | Enunciado P2 §3.2 |
| 003 (D-03) | Secret Manager en lugar de OpenBao | Enunciado P2 §3.1 |
| 004 (D-04) | Cloud Run termina el TLS en lugar de nginx propio | Enunciado P2 §3.1 |
| 005 (D-05) | Autenticación propia con Argon2id en lugar de Keycloak | Decisión del equipo |
| 006 (D-06) | OPA como contenedor adjunto en lugar de servicio en red privada | Restricción de Cloud Run |
| 007 (D-07) | Las reglas de continuidad DI-01 a DI-04 se reescriben | Límites del plan gratuito de Neon |
| 008 (D-08) | Sin restricción de acceso por dirección de origen | Límites del plan gratuito de Neon |
| 009 (D-09) | La verificación de un certificado no exige sesión | Enunciado P2 §2.2 |
| 010 (D-10) | Firma digital de certificados, que P1 no diseñó | Enunciado P2 §2.2 |
| 011 (D-11) | Los trabajos programados se consolidan en un solo servicio | Capa gratuita de Cloud Scheduler |
| 012 (D-12) | El conjunto de herramientas de análisis se reduce | Tiempo disponible |
| 013 (D-13) | El segundo factor es obligatorio solo para cuatro roles | Decisión del equipo |
| 014 (D-14) | El aviso al titular de RC-01 no llega por correo | Alcance |
| 015 (D-15) | Las solicitudes de cambio de cuenta tienen dueño fuera de la matriz | Hueco del diseño |
| 016 (D-16) | Las cuentas nuevas nacen con una contraseña temporal | Hueco del diseño |
| 017 (D-17) | Un período se crea abriéndolo, y `/abrir` reabre uno cerrado | Hueco del diseño |
| 018 (D-18) | El técnico solo registra mediciones en su zona | Refuerzo de la matriz |
| 019 (D-19) | El transmisor corre cada media hora, no casi en tiempo real | Límites del plan gratuito de Neon |
| 020 (D-20) | C9 se ata a la finca, y C6 compara el interior de los polígonos | Hueco del diseño |
| 021 (D-21) | Anular un certificado y autorizar a un tercero piden reautenticación | Refuerzo de la matriz |
| 022 (D-22) | Un solo período de medición abierto a la vez | Hueco del diseño |
| 023 (D-23) | La interfaz son plantillas del servidor, no Angular | Enunciado P2 §2.1 |
| 024 (D-24) | El reporte semanal de HBAC-02 queda fuera de alcance | Alcance |
| 025 (D-25) | Las exportaciones del auditor van en la misma aplicación, en CSV | Alcance |

---

## ADR 001 (D-01)
### La plataforma de alojamiento es software propietario

**Contexto**

El Informe de políticas recoge una restricción explícita de la cliente: presupuesto únicamente para software libre, que quedó como requerimiento R11 y como regla operativa LG-08. Esta parte 2 (Proyecto 2) impone Cloud Run, Neon, Secret Manager y Artifact Registry, que son servicios propietarios.

**Decisión**

El sistema se aloja en esos cuatro servicios del propietario. Todo el software que escribimos y todas sus dependencias siguen teniendo licencia libre: Python, FastAPI, PostgreSQL, PostGIS, OPA. Lo que se volvió propietario es solo la capa de alojamiento (donde se ejecuta).

**Consecuencias**

*Positivas*

- Los cuatro servicios tienen capa gratuita suficiente para este sistema, así que la restricción de presupuesto se respeta aunque la de licencia no (porque el sistema utiliza tecnologías propietarias no libres).
- Las mitigaciones que P1 ya proponía para el riesgo del proveedor siguen aplicando: los datos personales se cifran dentro de la aplicación, de modo que en la base de datos se guarda texto cifrado, y las cuentas de administración de la nube llevan segundo factor.

*Negativas*

- El riesgo residual RR-02 de P1 crece, que el proveedor de nube o una cuenta de administración comprometida acceda a los datos (abuso de permisos). Al pasar de alquilar máquinas a usar servicios gestionados, el proveedor también custodia los secretos y ejecuta el motor de base de datos.
- R11 y LG-08 (software libre) no se cumplen en la capa de alojamiento.

## ADR 002 (D-02)
### Docker en lugar de Podman sin privilegios

**Contexto**

El documento de arquitectura eligió Podman y descartó Docker Engine porque su servicio central corre con privilegios de administrador. Sin embargo esta parte 2, exige imágenes de Docker publicadas en Artifact Registry.

**Decisión**

Las imágenes se construyen con Docker. Cada Dockerfile declara un usuario sin privilegios, así que ningún contenedor corre como root, incluido el del motor de políticas.

**Consecuencias**

*Positivas*

- El demonio (daemon) de Docker existe solo donde se construye la imagen. En producción quien ejecuta el contenedor es Cloud Run, que no usa Docker y aísla cada instancia en su propio entorno.
- Se conserva el mínimo privilegio en la ejecución, no se ejecuta como root.

*Negativas*

- La construcción depende de un demonio con privilegios de administrador. En este proyecto se crea en los runners de GitHub Actions (CI), no en una máquina nuestra.

## ADR 003 (D-03)
### Secret Manager en lugar de OpenBao

**Contexto**

En el proyecto 1 se había descartado explícitamente los gestores de secretos de los proveedores de nube por crear dependencia del proveedor, pero esta parte 2 los impone. OpenBao hacía tres cosas que Secret Manager no hace: generaba credenciales de base de datos con vida limitada que se renovaban solas, firmaba cada registro de la bitácora con el motor Transit sin que la llave saliera nunca de él, y cifraba los datos personales sin entregarle la llave a nadie.

**Decisión**

Los secretos viven ahora en Secret Manager y se inyectan como variables de entorno. Cada servicio se autentica con su propia cuenta y solo puede leer los secretos que necesita. Las tres funciones de OpenBao pasan a la aplicación:

- La aplicación usa una contraseña de Neon guardada como secreto, con rotación manual.
- La llave del HMAC (el hash) de la bitácora llega al proceso del transmisor y el cálculo ocurre en memoria.
- La cédula y el teléfono se siguen cifrando antes de guardarse, como se exige en LG-05, con la llave en el proceso del backend. La búsqueda por cédula sigue usando un valor derivado en lugar del dato.

**Consecuencias**

*Positivas*

- Ninguna credencial vive en el repositorio ni en las imágenes, y cada servicio solo lee lo suyo.
- Los cambios de configuración y de permisos sobre los secretos quedan en los registros de auditoría de Google Cloud, que vienen activados por defecto.
- El rol de aplicación tiene privilegios mínimos: no es dueño de las tablas y no puede alterar el esquema.
- La bitácora vive en una instancia de Neon separada, donde el transmisor solo puede insertar.
- La tarea `volcado` del transmisor (ADR 007) sube cada semana la bitácora completa, con el registro o fila de cada evento, a un depósito de Cloud Storage donde nada se puede borrar ni reemplazar en diez años. Si alguien con la llave reescribe la cadena en Neon, la versión reescrita deja de coincidir con las copias anteriores, que ya no puede tocar. La tarea `cadena` además recalcula la cadena completa y deja constancia de cada comprobación en la propia bitácora.

*Negativas*

- Si la credencial de la base se filtra, sigue sirviendo hasta que alguien la cambie. Con OpenBao caducaba en 24 horas.
- Quien comprometa el proceso del transmisor puede reescribir la cadena completa y no se notaría en Neon. La garantía baja de «nadie con acceso a la base puede falsificar el historial» a «nadie con acceso a la base, pero sí quien controle el transmisor».
- La llave de los datos personales está en el proceso, en lugar de estar encerrada en un motor que solo responde operaciones.
- Las lecturas de un secreto no quedan registradas. El registro de acceso a datos de Google Cloud viene apagado y no lo activamos, así que no se puede saber quién leyó un secreto ni cuándo.
- El sistema queda atado al proveedor de nube, que era lo que P1 quería evitar.

## ADR 004 (D-04)
### Cloud Run termina el TLS

**Contexto**

La arquitectura ponía nginx como único punto de entrada desde internet, encargado de terminar TLS 1.3, limitar tamaño y tasa de solicitudes y agregar las cabeceras de seguridad. Cloud Run asigna un dominio con TLS automático y termina la conexión antes de que llegue al contenedor.

**Decisión**

La frontera F1 la aplica Google. Las cabeceras de seguridad (la política CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` y `Strict-Transport-Security`) y los límites de tamaño se mueven al servicio de borde. La frontera F2, entre el borde y el backend, se implementa con los permisos de Cloud Run: el backend no acepta invocaciones anónimas y solo la cuenta de servicio del borde puede llamarlo.

**Consecuencias**

*Positivas*

- No hay que gestionar ni renovar certificados.
- F2 es más fuerte que la separación por red privada que habíamos diseñado: un navegador que conozca la URL del backend recibe un rechazo antes de que nuestro código se ejecute.

*Negativas*

- La versión de TLS y el conjunto de cifrados quedan fuera de nuestro control. Cloud Run acepta TLS 1.2 y 1.3; P1 exigía solo 1.3.
- El límite de tasa general de nginx no se reimplementó. Solo la verificación pública tiene uno (ADR 009), y el inicio de sesión queda acotado por el bloqueo de RC-01.

## ADR 005 (D-05)
### Autenticación propia en lugar de Keycloak

**Contexto**

P1 eligió Keycloak como único emisor de identidades y argumentó, con razón, que escribir la autenticación uno mismo es un error frecuente y costoso. Pero Keycloak necesita su propia base de datos, arranca lento, consume memoria y expone una consola de administración que había que bloquear. En un servicio que escala a cero y en una capa gratuita, eso es desproporcionado.

**Decisión**

La autenticación pasa al backend, con Argon2id y los mismos parámetros que P1 fijó siguiendo a la OWASP: variante id, sal por usuario, 19 MiB de memoria, dos iteraciones y un hilo. Se conserva el diseño de sesión de P1: cookie opaca con los atributos HttpOnly, Secure y SameSite, sesión en la base de datos, revocación inmediata al dar de baja o cambiar de rol, e identificador nuevo al iniciar sesión. Las reglas de contraseña CO-01 a CO-05 y el bloqueo por intentos fallidos RC-01 se configuran en la aplicación. El segundo factor es TOTP para los roles que pueden aprobar, emitir o cambiar permisos (ADR 013), con la reautenticación en acciones críticas que P1 pedía.

**Consecuencias**

*Positivas*

- Un componente menos que operar, y ninguna consola de administración expuesta.
- Se conserva lo valioso del diseño, que era la sesión.

*Negativas*

- Se pierden las llaves de acceso. P1 las exigía para las direcciones, el personal administrativo y los verificadores, e implementar WebAuthn correctamente no cabe en el tiempo disponible. Quedan documentadas como pendientes.
- La amenaza AE-02, el atacante que entra con contraseñas filtradas de otros sitios, queda mitigada solo por la lista de contraseñas prohibidas de CO-02.
- El código de autenticación es nuestro, que es justo el riesgo que P1 advertía.

## ADR 006 (D-06)
### OPA como contenedor adjunto

**Contexto**

El motor de políticas era un componente aparte que solo aceptaba consultas desde la red privada. En Cloud Run no hay red privada entre servicios sin configuración adicional de red que la capa gratuita no cubre bien.

**Decisión**

OPA se despliega como contenedor adjunto dentro del mismo servicio que el backend, escuchando en la interfaz local. El paquete de políticas se construye dentro de la imagen y lleva la misma etiqueta de versión.

**Consecuencias**

*Positivas*

- La separación entre el punto de aplicación y el punto de decisión se conserva: las políticas siguen siendo código en Rego, versionado, con pruebas propias, y el backend sigue sin poder conceder lo que el motor deniega.
- Se puede saber qué reglas están corriendo, porque van con la etiqueta de la imagen.

*Negativas*

- La frontera F4 deja de ser una frontera de red y pasa a ser de proceso. Quien comprometa el contenedor del backend está en la misma instancia que el motor.

## ADR 007 (D-07)
### Las reglas de continuidad se reescriben

**Contexto**

DI-01 a DI-04 prometían recuperación en dos horas, respaldos al menos cada hora, regla 3-2-1 con una copia aislada que no se puede borrar durante su retención, y pérdida máxima de una hora de registros. Fueron escritas para dos máquinas propias con réplica en espera. Neon en plan gratuito ofrece restauración continua a cualquier punto de las últimas seis horas, y las instantáneas programadas son de plan pago. Seis horas no sirven para BI-04 ni para LG-06, que exigen conservar diez años lo ligado a un certificado.

**Decisión**

DI-01 y DI-04 se cubren con la restauración de Neon. La retención se resuelve con la tarea `volcado` del transmisor, que cada semana copia **la bitácora** a un depósito de Cloud Storage con una política de retención de diez años: ningún objeto se puede borrar ni reemplazar antes de ese plazo, y la cuenta del transmisor solo puede crear objetos, no leerlos ni borrarlos. La copia lleva el eslabón de cada evento y un manifiesto con su SHA-256.

**Consecuencias**

*Positivas*

- La restauración de Neon cumple DI-04 con margen, porque dentro de esa ventana la pérdida de datos es prácticamente nula, y cumple DI-01 porque restaurar es inmediato.
- El volcado recupera la copia separada de la bitácora que P1 pedía en BI-03, su retención de diez años (BI-04, LG-06) y, para la bitácora, la copia fuera de la cuenta de Neon (DI-02) que no se puede borrar (DI-03).
- La copia se puede verificar sin acceso a Neon.

*Negativas*

- **Solo la bitácora, no la base principal.** Copiar la base principal exigía un rol nuevo con lectura sobre todo el esquema, incluidos los datos personales cifrados, solo para respaldarlos. Lo que exige diez años es la trazabilidad, y esa está entera en la bitácora: quién midió, aprobó, enmendó, emitió y anuló, y cuándo. La base principal queda con la restauración de seis horas de Neon. Si se perdiera más allá de esa ventana, los datos vigentes (fincas, mediciones, certificados) habría que reconstruirlos, pero la historia de qué pasó con ellos no se pierde. DI-02 y DI-03 quedan cumplidas para la bitácora y no para la base principal.
- **La retención no está bloqueada.** Bloquearla es irreversible: el depósito no se podría borrar en diez años y Google le pone un gravamen al proyecto para que tampoco se pueda borrar. En un proyecto académico no lo hacemos. Un administrador del proyecto de Google Cloud podría quitar la política y después borrar las copias. Es el riesgo residual RR-02 de P1, y en producción se cierra con un comando (`--lock-retention-period`).
- Se pierden la réplica en espera y el ensayo semestral de recuperación cronometrado. Neon no expone conmutación manual en plan gratuito, y la disponibilidad del servicio deja de estar bajo nuestro control, lo que ensancha el riesgo residual RR-04.

## ADR 008 (D-08)
### Sin restricción por dirección de origen

**Contexto**

La lista de direcciones permitidas y el acceso por red privada virtual son funciones de plan pago en Neon, y el acceso público de internet no se puede apagar sin una de las dos. Aunque fueran gratuitas tampoco encajarían bien: Cloud Run no sale a internet por direcciones estables sin configurar salida directa a una red virtual y traducción de direcciones, así que una lista de permitidos exigiría infraestructura adicional.

**Decisión**

La base de datos acepta conexiones desde cualquier punto de internet, y la única barrera es la credencial.

**Consecuencias**

*Positivas*

- La plataforma exige TLS en toda conexión y autentica con SCRAM, lo que impide capturar la credencial en tránsito.
- La aplicación además exige `sslmode=verify-full`, así que también verifica que el servidor sea el de Neon.

*Negativas*

- No hay segunda línea de defensa a nivel de red: todo el peso recae sobre que la credencial no se filtre.
- Eso eleva la importancia de que nada se versione y de que el rol de aplicación tenga privilegios mínimos.

## ADR 009 (D-09)
### La verificación de un certificado no exige sesión

**Contexto**

El diseño sostenía el principio de mediación completa: ninguna ruta, trabajo programado ni generación de reportes salta el punto de aplicación. El enunciado pide que cualquiera pueda comprobar un certificado sin acceso al sistema, porque un certificado de carbono circula fuera de Verdeazul y vale dinero.

**Decisión**

El punto de verificación es público y no pide sesión. No consulta la base de datos: recibe el archivo que trae quien verifica, comprueba la firma con la clave pública incrustada en ese mismo archivo y compara su huella con la de Verdeazul (ADR 010). Lo acotan tres medidas:

- tamaño máximo de 64 KB, en el borde y otra vez en el backend;
- límite de 10 verificaciones por minuto por dirección de origen, en el borde;
- una respuesta que solo dice si es válido, si la llave es la de Verdeazul y las dos huellas.

La huella de la llave de producción es `SHA256:203b7265f5b57cbe0aed5ef62cb74a56e2731c5185675e8742203dfbd3df811d`. La página `/verificar` la muestra junto a la huella del archivo, y es la que se compara por fuera del sistema.

**Consecuencias**

*Positivas*

- No hay objeto protegido en juego, así que no es una excepción al control de acceso: la verificación no revela nada.
- Un tercero puede confiar en el certificado sin acceso al sistema. Se comprobó en producción el 17 de noviembre: un certificado firmado con una llave generada en otra máquina tiene firma válida y aun así se rechaza, porque su huella es otra.

*Negativas*

- El límite de tasa vive en la memoria de cada instancia del borde: si Cloud Run levanta varias, el límite efectivo se multiplica. Se acepta por el volumen del sistema; en una operación real iría en un almacén compartido.
- Una verificación válida no dice si el certificado se anuló después, porque la verificación no consulta la base y un anulado conserva su firma. Para saberlo hay que preguntarle a Verdeazul.

## ADR 010 (D-10)
### Firma digital de certificados

**Contexto**

P1 no diseñó esto. La Ley 8454 aparecía en el marco regulatorio señalando que los certificados y los reportes se pueden firmar digitalmente, pero no había formato, llave ni procedimiento de verificación. El enunciado lo exige.

**Decisión**

Cada certificado se emite como un documento firmado con Ed25519. La clave privada vive en Secret Manager y la pública viaja dentro del documento. El evento de emisión en la bitácora incorpora la huella de la clave usada, que es un campo nuevo respecto a la Tabla 4.2 de P1.

**Consecuencias**

*Positivas*

- Cualquiera puede comprobar que el contenido no fue alterado desde que se firmó.
- La clave privada no sale de Secret Manager: en local se firma con cualquier llave de prueba.

*Negativas*

- Una clave pública que viaja en el propio documento prueba que el contenido no cambió, pero no prueba quién firmó: alguien podría generar su propio par de claves y firmar un certificado falso que verificaría igual de bien. Se cierra publicando la huella de la clave de Verdeazul por un canal independiente. El punto de verificación público la compara automáticamente; quien verifique con herramientas propias tiene que compararla a mano.

## ADR 011 (D-11)
### Los trabajos programados se consolidan en un solo servicio

**Contexto**

P1 preveía varios procesos periódicos: el transmisor que copia eventos a la bitácora, la desactivación de asignaciones y autorizaciones vencidas que exige HBAC-03, el reporte semanal de volumen de HBAC-02 y la comprobación mensual de la cadena. En la arquitectura original eran servicios o tareas independientes. Cloud Run cobra por instancia activa, y la capa gratuita de Cloud Scheduler cubre tres trabajos.

**Decisión**

Todas las tareas viven en un solo servicio, el transmisor, con un punto de entrada por tarea (`POST /tareas/{nombre}`). El servicio exige la cuenta del planificador y no es accesible desde internet. Hay dos trabajos programados: `transmitir` cada 30 minutos (ADR 019) y `volcado` los lunes. `vencer` y `cadena` se lanzan a mano.

**Consecuencias**

*Positivas*

- Un solo servicio y dos trabajos, dentro de la capa gratuita.
- El patrón de bandeja de salida tolera que el transmisor se atrase: los eventos se acumulan en la tabla de salida sin perderse, y el retraso se puede medir.
- Que `vencer` no corra sola no abre ningún acceso: C1 lee en cada petición solo las asignaciones vigentes, y el vencimiento de C9 lo compara el motor.

*Negativas*

- Una falla en ese servicio detiene todas las tareas periódicas a la vez, en lugar de una sola.
- Hasta que alguien lanza `vencer`, una asignación o autorización vencida no queda marcada como revocada ni deja su evento en la bitácora.
- La comprobación mensual de la cadena que pide BI-02 no es automática: depende de lanzar `cadena` a mano.
- El reporte de HBAC-02 no se implementó (ADR 024).

## ADR 012 (D-12)
### Menos herramientas de análisis

**Contexto**

Cada ficha de tecnología de P1 listaba herramientas de análisis: Bandit, Semgrep, pip-audit, Trivy, OWASP ZAP, gitleaks, hadolint, Gixy, Regal y testssl.sh. En tres semanas no se configuran todas con sentido.

**Decisión**

Se mantienen tres. Dependabot, que el enunciado exige y que cubre lo que hacían pip-audit y la revisión de dependencias de npm. Un detector de secretos, gitleaks, que corre en cada pull request sobre todo el historial. Y las pruebas automatizadas de autorización por cada celda de la matriz, que P1 ya exigía.

**Consecuencias**

*Positivas*

- Cubren lo que el enunciado más castiga: una credencial versionada anula por completo el criterio de gestión de secretos, y el historial de git conserva lo que se borra.
- Las pruebas de la matriz son la evidencia de la tabla de cobertura.

*Negativas*

- No hay análisis estático del código, ni de las imágenes, ni dinámico de la aplicación desplegada. Las demás herramientas quedan como pendientes para una operación real.

## ADR 013 (D-13)
### El segundo factor es obligatorio solo para cuatro roles

**Contexto**

La Tabla 7.1 del Informe de políticas pedía segundo factor a los ocho perfiles, con llave de acceso preferida y TOTP como alternativa. El ADR 005 explica por qué no hay llaves de acceso; esta es la otra mitad.

**Decisión**

El segundo factor es obligatorio para Dirección General, Dirección de Certificación, Personal Administrativo y Verificador, que son los roles que aprueban, emiten o cambian permisos. Sin él no pasan de la pantalla de activación, que es lo que CU-04 pedía («antes del primer uso registra su segundo factor»). Para técnico de campo, auditor externo, dueño de finca y tercero autorizado es opcional, y una vez que alguien lo activa se le pide siempre. El conjunto de roles obligados es una sola constante en `services/api/app/auth/totp.py`. Los códigos de recuperación de RC-02 están implementados: ocho de un solo uso al activar el factor, guardados como huella SHA-256.

**Consecuencias**

*Positivas*

- Responde al uso real: el técnico trabaja en campo con conexión irregular, y el dueño y el tercero son externos que entran pocas veces al año.
- Se conserva lo demás de la Tabla 7.1: el cierre por inactividad de cada perfil (15, 30 y 60 minutos) y la reautenticación antes de cambiar roles, abrir o cerrar períodos y aprobar.
- Extenderlo a los ocho roles es cambiar una línea.

*Negativas*

- En esos cuatro roles una contraseña filtrada basta para entrar (AE-02). Lo acotan la lista de contraseñas prohibidas y la consulta a filtraciones conocidas de CO-02, el bloqueo de RC-01, y que esos roles solo leen lo suyo: ninguno aprueba, emite ni cambia permisos.
- La recuperación por videollamada de RC-03 es un procedimiento humano y queda fuera del sistema.

## ADR 014 (D-14)
### El aviso al titular de RC-01 no llega por correo

**Contexto**

RC-01 dice «tras 10 intentos fallidos, bloqueo de 30 minutos y aviso al titular». El sistema no envía correos.

**Decisión**

El bloqueo está implementado tal cual, con la espera creciente desde el quinto intento (15 segundos, que se duplican hasta el noveno). El aviso toma dos formas: cada bloqueo queda como evento `CUENTA_BLOQUEADA` en la bitácora, y la próxima vez que el titular entra, la pantalla le dice cuántos intentos fallidos hubo desde su último ingreso.

**Consecuencias**

*Positivas*

- Cada bloqueo deja rastro en la bitácora.
- Agregar un correo es enviar un mensaje desde el mismo punto donde hoy se registra el evento.

*Negativas*

- El titular se entera cuando vuelve a entrar, no en el momento.

## ADR 015 (D-15)
### Las solicitudes de cambio de cuenta tienen dueño fuera de la matriz

**Contexto**

C10 exige que exista una aprobación previa de Dirección General antes de que el Personal Administrativo cree o modifique una cuenta. Esa aprobación vive en la tabla `solicitudes_rol`, que no es un objeto de la matriz, igual que `ventanas_auditoria`. Así que la matriz no dice quién puede crear una solicitud ni quién puede aprobarla. Además, la migración 004 solo modelaba el cambio de rol de una cuenta existente, pero C10 también gobierna el alta (C) y la baja (M).

**Decisión**

Lo decidimos con CU-01 y CU-03 de P1. El Personal Administrativo registra la solicitud que hizo la jefatura, la Dirección General la aprueba o la rechaza, y el Personal Administrativo la aplica. La base de datos impide que quien pide apruebe, que quien aprueba aplique, y que nadie pida o apruebe sobre su propia cuenta. El servidor impone quién hace cada paso con la misma regla que el motor: niega por omisión y registra el intento. La migración 011 agrega el tipo de solicitud y deja `cuenta_afectada` vacía hasta que el alta se aplica, porque la cuenta todavía no existe cuando se pide.

L·C10 sobre O9 se implementa literal: el Personal Administrativo ve una cuenta únicamente mientras tiene un cambio aprobado por Dirección General pendiente de aplicar. Para ver el estado de sus solicitudes usa la lista de solicitudes, que no expone las cuentas. Al aplicar un cambio de rol se revocan las asignaciones de zona de la cuenta, por CU-10 («primero se revoca y después se asigna»), y en el cambio de rol y en la baja se cierran al instante todas sus sesiones, por SE-01 y CU-11.

**Consecuencias**

*Positivas*

- C10 cubre el alta y la baja, no solo el cambio de rol.
- La separación de deberes la impone la base, no solo el código.

*Negativas*

- Quién puede tocar las solicitudes se decide en el servidor y no en el motor de políticas, así que no lo cubren las pruebas de la matriz sino las de identidad.
- El Personal Administrativo no ve las cuentas fuera de ese momento, que es la lectura literal de la matriz.

## ADR 016 (D-16)
### Las cuentas nuevas nacen con una contraseña temporal

**Contexto**

P1 no dijo cómo recibe alguien su primera contraseña. Con Keycloak eso lo resolvía el correo de activación.

**Decisión**

El Personal Administrativo, al aplicar el alta, recibe una contraseña temporal aleatoria de 20 caracteres que se muestra una sola vez y que entrega a la persona. La cuenta nace marcada con `debe_cambiar`: con la contraseña temporal se puede entrar, pero la sesión solo sirve para activar el segundo factor (si el rol lo exige) y cambiarla.

**Consecuencias**

*Positivas*

- El administrativo conoce la temporal pero no la definitiva, y tampoco tiene el segundo factor, así que no puede usar la cuenta que creó.

*Negativas*

- Hasta que la persona la cambia, la contraseña temporal pasó por las manos del administrativo.

## ADR 017 (D-17)
### Un período se crea abriéndolo

**Contexto**

La matriz le da a Dirección de Certificación las operaciones Ab (abrir) y Cr (cerrar) sobre O2, y el contrato 04 listaba `POST /periodos/{id}/abrir`. Pero un período no se puede abrir si no existe, y ningún endpoint lo creaba.

**Decisión**

`POST /periodos` crea un período nuevo y nace ABIERTO, bajo la operación Ab. `POST /periodos/{id}/abrir` queda para reabrir uno cerrado, y falla con 409 si ya está abierto. Las dos piden reautenticación (Tabla 7.1 de P1), igual que cerrar. Cerrar solo se permite cuando no quedan mediciones REGISTRADAS en el período. Las DEVUELTAS no cuentan, porque su autor no puede corregirlas (no se modifican, se enmiendan) y esperarlas bloquearía el cierre para siempre.

**Consecuencias**

*Positivas*

- Ninguna celda de la matriz cambia, y la operación sigue siendo Ab para el mismo rol.
- Cada apertura queda registrada como `PERIODO_ABIERTO` en la bitácora, con la etiqueta.

*Negativas*

- Reabrir un período cerrado vuelve a habilitar C2 y deja de cumplirse C11 mientras tanto, así que quien lo reabre tiene que saber si hay enmiendas en curso.

## ADR 018 (D-18)
### El técnico solo registra mediciones en su zona

**Contexto**

La matriz le da al Técnico de campo C sobre O3 con la condición C2 (período abierto) y no menciona C1. Leída literal, un técnico podría registrar una medición de una finca de una zona que no tiene asignada, y solo el verificador lo vería después.

**Decisión**

Al registrar, el servidor además le pregunta al motor si el técnico puede leer esa finca (L sobre O1, que sí lleva C1), y si no, niega y registra el intento.

**Consecuencias**

*Positivas*

- Una cuenta de técnico comprometida no puede inyectar mediciones en fincas ajenas.
- No amplía ningún permiso, solo agrega una restricción, que es la dirección que la matriz permite: ABAC quita permisos, nunca los agrega.

*Negativas*

- La condición se aplica en un lugar donde la matriz no la puso, así que quien lea la matriz al pie de la letra no la ve.

## ADR 019 (D-19)
### El transmisor corre cada media hora

**Contexto**

P1 describía un transmisor que copia cada evento a la bitácora apenas ocurre, con un aviso si el retraso pasaba de cinco minutos. Cada corrida despierta el cómputo de las dos bases de Neon, que después tarda cinco minutos en volver a dormirse. Con una corrida cada cinco minutos las bases no se dormirían nunca, y una base despierta todo el mes gasta unas 180 horas de cómputo, cuando el plan gratuito da 100 por proyecto. Al agotarlas, Neon suspende la base y el sistema deja de abrir.

**Decisión**

Cloud Scheduler invoca al transmisor cada 30 minutos. La hora que queda en la bitácora es la de la operación, copiada de la bandeja de salida, no la de la copia.

**Consecuencias**

*Positivas*

- Las horas de cómputo de Neon alcanzan, y el sistema no corre el riesgo de quedar suspendido.
- Ningún evento se pierde: queda en la bandeja de salida, que se escribe en la misma transacción que la operación.

*Negativas*

- Un evento puede tardar hasta media hora en aparecer en la bitácora, y los de los últimos dos minutos esperan a la corrida siguiente. Para la presentación, el transmisor se puede invocar a mano.
- Se pierde la detección temprana: durante esa media hora, alguien con acceso a la base principal podría intentar alterar un evento antes de que se selle. Lo acota la migración 012, que le quita a la aplicación el permiso de modificar la bandeja.

## ADR 020 (D-20)
### C9 se ata a la finca, y C6 compara el interior de los polígonos

**Contexto**

Dos reglas de la matriz, tal como se escribieron en P1, dejaban un hueco al construirlas.

C9 dice `autorizacion.tercero = sujeto.id ∧ hoy < autorizacion.vence`. No dice de qué finca es la autorización. Escrita así, un tercero con cualquier autorización vigente vería los certificados de todas las fincas, y los dueños son competencia entre sí: es justo lo que la carta pide evitar y lo que la regla LG-03 prohíbe. Tampoco dice nada de una autorización revocada, que CU-09 exige que deje de servir.

C6 dice «ningún certificado vigente tiene un polígono que se superponga». Con `ST_Intersects` solo, dos fincas vecinas que comparten un lindero se «intersecan» en el borde, y certificar una impediría para siempre certificar la vecina. Lo que la minuta B4 prohíbe es certificar dos veces el mismo terreno.

**Decisión**

Para C9, el motor evalúa la condición como está escrita, pero el backend solo le manda la autorización que es **de la finca del certificado** y **no está revocada** (`services/api/app/certificados/consultas.py`, `autorizaciones_del_tercero`). Si no existe ninguna, no manda nada y C9 no se cumple. La fecha la sigue decidiendo el motor, así que una autorización vencida llega al motor y el motor la niega.

Para C6, se exige que los interiores se crucen: `ST_Intersects` y no solo `ST_Touches`.

**Consecuencias**

*Positivas*

- Un tercero ve solo los certificados de la finca que le autorizaron, y una autorización revocada deja de servir. Lo cubre `test_una_autorizacion_de_otra_finca_no_sirve`.
- Dos fincas vecinas se pueden certificar las dos. Lo cubre `test_dos_fincas_vecinas_si`.

*Negativas*

- Una parte de C9 vive en una consulta SQL y no en Rego.

## ADR 021 (D-21)
### Anular un certificado y autorizar a un tercero piden reautenticación

**Contexto**

P1 (Tabla 7.1) vuelve a pedir el factor antes de aprobar, emitir, abrir y cerrar períodos y cambiar roles. Hay dos acciones más con el mismo peso:

- **Anular un certificado** (An sobre O5). C6 solo compara contra los vigentes, así que anular libera el terreno para una emisión nueva. Con una sesión robada, anular y volver a emitir es un camino para cambiar un certificado.
- **Autorizar a un tercero o extender una autorización** (C y M sobre O7). Es entregarle información del dueño a otra persona (Ley 8968, art. 14).

**Decisión**

Esas dos acciones piden reautenticación. Revocar una autorización no la pide, a propósito: es la acción que protege al dueño y no debe costarle nada.

**Consecuencias**

*Positivas*

- Una sesión robada ya no alcanza para anular y reemitir un certificado, ni para entregarle los datos de un dueño a un tercero.
- No cambia ninguna celda de la matriz.

*Negativas*

- Un paso más para el dueño y para la Dirección de Certificación en esas acciones.

## ADR 022 (D-22)
### Un solo período de medición abierto a la vez

**Contexto**

P1 define los períodos como «ventanas de registro, con su estado abierto o cerrado», y la única regla sobre ellos es C2: solo se registran mediciones en uno abierto. No dice cuántos puede haber abiertos a la vez, y el sistema dejaba abrir varios. Con dos abiertos, un técnico podía registrar la misma finca en las dos ventanas al mismo tiempo, y quedaba ambiguo a qué período pertenecía cada medición.

**Decisión**

Solo puede haber uno abierto. Crear un período o reabrir uno cerrado responde 409 si ya hay otro abierto, y las dos operaciones toman primero el mismo candado, para que dos aperturas simultáneas no dejen dos abiertos. La regla vive en el servidor y no en la base: un índice único sería más fuerte, porque la impondría aunque el código tuviera un error, pero las pruebas de integración crean períodos abiertos directo en una base compartida, y habría que rehacerlas en cinco módulos.

**Consecuencias**

*Positivas*

- Cada medición pertenece a una sola ventana de registro, sin ambigüedad.
- Ninguna celda de la matriz cambia.

*Negativas*

- Con la credencial de `app_rw`, que solo tiene la aplicación, se podría abrir un segundo período por SQL saltándose la regla.
- El período nuevo no se puede abrir hasta cerrar el anterior, y cerrar exige que no queden mediciones sin revisar. Si la verificación se atrasa, frena el registro del período siguiente.

## ADR 023 (D-23)
### La interfaz son plantillas del servidor, no Angular

**Contexto**

P1 eligió Angular para la interfaz. El enunciado dice que la interfaz no se evalúa, que basta «una interfaz sobria que permita ejercitar todos los permisos de la matriz», y que conviene invertir el tiempo en seguridad.

**Decisión**

El servicio de borde arma las páginas en el servidor con plantillas Jinja, sin un marco de JavaScript: una hoja de estilos y formularios que se envían al borde, que a su vez llama al backend.

**Consecuencias**

*Positivas*

- Desaparece la cadena de dependencias de npm, con todo lo que Dependabot y el análisis tendrían que vigilar.
- La política CSP puede ser estricta (`script-src 'self'`) sin excepciones.
- La protección contra CSRF es un token en cada formulario, verificado en el borde.

*Negativas*

- Se pierde la usabilidad que motivó la elección de P1: cada acción recarga la página completa.

## ADR 024 (D-24)
### El reporte semanal de HBAC-02 queda fuera de alcance

**Contexto**

HBAC-02 pide un reporte semanal de volumen anómalo de actividad, combinado con la zona. No es una celda de la matriz, así que no cuenta para la cobertura, pero sí es una política documentada en P1 y en el Informe de políticas. El enunciado (§2.1) dice que, si hay que recortar, se recorte en funcionalidad accesoria y nunca en la matriz ni en los controles.

**Decisión**

No se implementa.

**Consecuencias**

*Positivas*

- El tiempo fue a la matriz completa y a los controles obligatorios.
- Los datos para hacerlo están en la bitácora: cada operación queda con quién la hizo, sobre qué objeto y cuándo.

*Negativas*

- Un volumen anómalo, como un técnico que registra muchas más mediciones de lo normal, no se detecta automáticamente. Lo acota la separación de deberes: cada medición tiene que aprobarla otra persona (C3).

## ADR 025 (D-25)
### Las exportaciones del auditor van en la misma aplicación, en CSV

**Contexto**

La minuta comprometió un portal propio para auditores con reportes en PDF. La matriz da la operación X (exportar) sobre mediciones, enmiendas, certificados y la bitácora, y esas celdas sí hay que implementarlas.

**Decisión**

Las exportaciones son cuatro rutas de la misma aplicación (`/mediciones/exportar`, `/enmiendas/exportar`, `/certificados/exportar` y `/bitacora/exportar`) que devuelven un CSV. El auditor entra con su cuenta, como los demás roles, y C7 limita las exportaciones a su ventana de auditoría.

**Consecuencias**

*Positivas*

- Las celdas X de la matriz están implementadas, con el mismo control de acceso que el resto.
- Un componente menos que construir, desplegar y proteger.

*Negativas*

- No hay portal separado ni reportes en PDF: el auditor recibe datos tabulares y los procesa con sus herramientas.
