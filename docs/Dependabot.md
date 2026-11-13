# Dependabot: qué propuso y qué hicimos

El enunciado (§3.3) pide Dependabot activo y, si aparecen alertas durante el
proyecto, atender al menos una y documentarlo. Esto es ese registro.

## Cómo está configurado

`.github/dependabot.yml` revisa cada lunes nueve fuentes de dependencias: los
paquetes de Python de los tres servicios (`pip`), las imágenes base de los
cuatro componentes (`docker`) y las acciones de los workflows
(`github-actions`). Cada directorio tiene su entrada, porque Dependabot no
busca de forma recursiva. Las alertas de seguridad se encienden aparte, en
Settings → Code security del repositorio.

## Lo que propuso (13 de noviembre de 2026)

| PR de Dependabot | Cambio | Decisión |
|---|---|---|
| `pip` en `services/api` | `fastapi` 0.115.6 → 0.162.2, `uvicorn` 0.34.0 → 0.54.0 | **Atendida**: corrige CVE-2025-62727. Se aplicó a los tres servicios en la rama `deps/fastapi-starlette` (abajo) |
| `docker` en `services/policies` | OPA 1.4.2 → 1.22.2 | Se acepta si su CI pasa: el CI corre las 977 pruebas de la matriz y `opa test` con la versión que dice el Dockerfile |
| `github-actions` | `gitleaks-action` v2 → v3 | Se acepta si su CI pasa: es el job que busca credenciales versionadas |
| `docker` en `services/edge` | Python 3.14 → 3.15 | **Pospuesta**: solo movía el borde (los otros tres servicios quedarían en 3.14) y la versión salió en octubre, sin margen para comprobar las ruedas binarias de todas las dependencias antes de la entrega. Se revisa después del 19 de noviembre |

## La alerta atendida: CVE-2025-62727 en Starlette

**Qué era.** `fastapi==0.115.6` trae Starlette 0.41.3. Toda Starlette desde la
0.39.0 hasta antes de la 0.49.1 tiene CVE-2025-62727 (GHSA-7f5h-v6xp-fcq8,
CVSS 7.5): al servir un archivo con `FileResponse` o `StaticFiles`, el
encabezado HTTP `Range` se analiza con una expresión regular y un bucle de
fusión de rangos de costo cuadrático. Un atacante **sin autenticarse** manda un
`Range` armado y agota la CPU.

**Por qué nos afectaba.** El borde es lo único expuesto a internet, y sirve
`/static` con `StaticFiles` (`services/edge/app/main.py`). Cloud Run le da una
CPU a cada instancia: unas pocas peticiones así lo dejan sin responder. Es la
amenaza AE-04 de la Parte 1 (servicio caído más de dos horas) por un camino que
el modelo de amenazas no había previsto: una dependencia.

**Cómo se comprobó.** Con el mismo `StaticFiles` y el mismo directorio del
borde, en local con el cliente de pruebas (sin tocar ningún servidor real), una
sola petición con `Range: bytes=111…` de distinto tamaño:

| Tamaño del encabezado | Starlette 0.41.3 | Starlette 1.10.0 |
|---|---|---|
| 4 KB | 0,13 s | 0,00 s |
| 8 KB | 0,28 s | 0,00 s |
| 16 KB | **1,12 s** de CPU por petición | 0,00 s |

El tiempo crece con el cuadrado del tamaño: el doble de encabezado, cuatro
veces más CPU. Con la versión corregida el analizador rechaza la entrada sin
recorrerla.

**Qué se cambió** (rama `deps/fastapi-starlette`):

- `services/api` y `services/transmisor`: `fastapi==0.162.2` y
  `uvicorn[standard]==0.54.0`, lo que proponía Dependabot.
- `services/edge`: **no fijaba ninguna versión** (`fastapi` a secas). Cada
  construcción bajaba la última, así que no se sabía qué Starlette corría en
  producción y Dependabot no tenía con qué comparar. Ahora fija las mismas
  versiones que los otros dos servicios. Esto también cumple lo que pide §3.2
  sobre saber qué está corriendo.

**Cómo se verificó que nada se rompió.** Starlette pasa de 0.41 a 1.10, un
salto de versión mayor. Con las versiones nuevas:

| Pruebas | Resultado |
|---|---|
| Matriz completa contra OPA real (`tests/matriz`) | 977 pasan |
| Transmisor (`services/transmisor/tests`) | 66 pasan |
| Identidad sin base (`tests/identidad/test_unitarias.py`) | 44 pasan |
| Borde de punta a punta con el backend simulado: redirecciones, páginas, CSRF, reautenticación, `/static` y CSP | Igual que antes |
| Integración contra PostgreSQL (identidad, certificación, enmiendas, asignaciones, bitácora) | En el CI del pull request |

Con esto el PR de Dependabot de `pip` queda resuelto: Dependabot lo cierra
solo cuando la versión que proponía llega a `develop`.

## Lo que queda abierto

- **Python 3.15** en las imágenes: después de la entrega, y en los cuatro
  servicios a la vez.
- **Alertas futuras**: Dependabot sigue revisando cada lunes. El criterio que
  usamos aquí sirve para las siguientes: comprobar si el código vulnerable
  está en un camino expuesto, medirlo si se puede, actualizar en todos los
  servicios que comparten la dependencia, y dejar que el CI confirme que nada
  se rompió.
