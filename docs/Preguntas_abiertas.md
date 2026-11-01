# Preguntas abiertas y decisiones pendientes

Estado al 26 de octubre de 2026. Nada de esto bloquea el primer commit; todo
esto sí bloquea algo más adelante. Revisar contra la retroalimentación del
profesor antes de tomar las decisiones marcadas como del grupo.

---

## 1. Para preguntar en la retroalimentación

**Los dos proyectos Neon.** El enunciado §5.2 pide explicar "si crearon ramas o
entornos separados". Nosotros no usamos ramas de Neon: usamos dos proyectos
distintos, `verdeazul-app` y `verdeazul-bitacora`, para implementar la frontera
de confianza F6 (la bitácora en una base que la aplicación no puede modificar).
Confirmar que eso satisface el requisito, porque dos proyectos son más
separación que dos ramas, no menos.

**El frontend.** El enunciado dice que lo visual no se evalúa. Confirmar que una
interfaz con plantillas renderizadas en el servidor (sin Angular, sin SPA) no
pierde puntos. De eso depende si dos personas del grupo se dedican a Angular o
se suman al control de acceso.

**Neon está en AWS, no en Google Cloud.** El despliegue pedido es en Google
Cloud, pero la base de datos corre en AWS us-east-1 y se alcanza por internet
con TLS. Confirmar que eso cuenta como despliegue válido, o si espera que la
base también esté en GCP (Cloud SQL, que no es gratuito).

**Cobertura de la matriz.** Son 88 celdas por 11 operaciones, 968 pares. De
esos, 84 están concedidos (47 sin condición y 37 con una de las condiciones
C1-C11) y 884 quedan denegados por omisión. Preguntar si se evalúa la matriz
completa o si se acepta un subconjunto representativo bien argumentado, y si las
denegaciones por omisión cuentan para la cobertura.

**Políticas de P1 que no son celdas.** HBAC-02 (reporte semanal de volumen
anómalo) está en el Informe de políticas de P1 pero no es una celda de la
matriz. Preguntar si implementarlo suma o si se declara fuera de alcance sin
penalización.

**La facturación.** El proyecto `verdeazul-grupo4` existe pero no tiene cuenta de
facturación y Google pide un prepago reembolsable de 30 dólares. Preguntar si el
TEC tiene créditos educativos o alguna alternativa institucional antes de que
alguien ponga su tarjeta.

---

## 2. Decisiones del grupo

**Angular o plantillas.** Tres opciones ya planteadas: (A) plantillas, nadie
dedicado al frontend, recomendada; (B) dos personas dedicadas a Angular; (C) una
dedicada más una que dobla. El riesgo de B es que el 40 % del equipo trabaje en
la parte que no da puntos directos y quede menos expuesto a la matriz y a la
criptografía, que es lo que se defiende individualmente en §6.

**Los cinco usuarios de GitHub.** Hacen falta para invitarlos como
colaboradores del repositorio. Sin eso solo Carlos puede empujar.

**El portal de auditores.** La minuta de P1 prometió un portal propio con
reportes en PDF. El permiso de exportar hay que implementarlo porque es una
celda. Que sea un portal aparte o una sección de la misma aplicación está sin
decidir.

**Alcance de HBAC-02.** Versión mínima o fuera de alcance. Depende de la
respuesta del profesor en el punto anterior.

---

## 3. Preguntas técnicas que bloquean el SQL

Las tres están también en `contracts/01-esquema.md`. Hay que resolverlas antes
de escribir las migraciones, porque cambian la forma de las tablas.

1. **¿`zona` es una tabla o un valor de texto?** C1 compara `finca.zona` contra
   `sujeto.zonas`, en plural, así que un sujeto tiene varias. Si es tabla hay
   una tabla puente; si es texto hay un arreglo o una tabla de asignación.
2. **¿Dónde vive la aprobación previa de la Dirección General que exige C10?**
   ¿Tabla propia de solicitudes de cambio de permisos, o una columna en
   `roles_asignados`? Una tabla propia deja rastro de quién pidió y quién
   aprobó; una columna no.
3. **¿El valor derivado para buscar por cédula es HMAC con llave o hash
   simple?** Hash simple es vulnerable a un ataque de diccionario: las cédulas
   de Costa Rica tienen formato conocido y el espacio es chico. HMAC con llave
   resuelve eso pero hay que decidir dónde vive la llave.

---

## 4. Huecos encontrados al leer la arquitectura de P1

Van en `docs/P2_Desviaciones_respecto_P1.md`, todavía no escritos ahí.

**La frontera F5 desaparece.** Al quitar Keycloak se va el OIDC entero: no hay
PKCE, ni `state`, ni nonce. Las seis fronteras de confianza pasan a cinco y
D-05 no lo dice. Además P1 afirmaba que las contraseñas las guarda solo Keycloak
y que el backend nunca las recibe; con autenticación propia el backend ahora sí
maneja contraseñas en claro antes de hashearlas. Eso cambia el modelo de
amenazas y hay que decirlo.

**BI-03 se debilita.** P1 escribía cada evento a almacenamiento de solo-escritura
en el momento. El volcado periódico de D-07 detecta el borrado de los últimos
registros solo hasta el siguiente volcado. Es una pérdida real de garantía y
conviene declararla antes de que la pregunten.

**RR-05 desaparece, y eso es bueno.** Ya no hay un nodo único de OpenBao como
punto de falla, porque los secretos los guarda Secret Manager.

---

## 5. Verificaciones pendientes

**La versión de OPA.** `services/policies/Dockerfile` y `.github/workflows/ci.yml`
usan `1.4.2`. Ese número lo puse sin comprobarlo. Si no existe, el CI falla en
el primer push y la imagen no construye.

**Las imágenes de Docker.** Los cuatro Dockerfile están escritos y ninguno se ha
construido, porque Docker Desktop está apagado. Hasta que se construyan no
sabemos si compilan.

**Las políticas en Rego.** `autorizacion.rego` y sus tres pruebas no se han
ejecutado; no hay `opa` instalado localmente. La sintaxis puede estar mal.

**Las versiones en los `requirements.txt`.** Están sin fijar. Hay que congelarlas
exactas después del primer build que funcione, o cada quien va a instalar una
versión distinta.
