# Panel de operación en el dashboard local — diseño

Fecha: 2026-06-11 · Estado: aprobado en conversación

## Qué es

Una sección de operación dentro del dashboard local existente
(`casework/dashboard.py`, http://localhost:8765) desde la cual el operador
controla la frecuencia del monitoreo, programa la actualización completa,
lanza corridas manuales y ve el estado del pipeline. Herramienta personal,
solo localhost; nada de esto se publica en el sitio.

## Metas

- Elegir la frecuencia del poll en vivo (15 min / 30 min / 1 h / 4 h /
  pausado) y que se ejecute aunque el dashboard esté cerrado.
- Programar la actualización completa (descarga de fuentes + detectores +
  export) a una hora del día, o desactivarla.
- Editar los parámetros del monitor: umbral de alerta (`threshold`) y
  presupuesto de detalle (`max_detail`).
- Corridas manuales con un clic: poll ahora, actualización completa,
  reconstruir el sitio.
- Ver de un vistazo: estado de cada agente programado, última corrida y su
  resultado, próxima corrida estimada, frescura de cada fuente (MANIFEST),
  último build del sitio y las últimas 10 alertas.

## No-metas

- Nada multiusuario, remoto ni autenticado: sigue siendo localhost.
- No se toca el sitio público (`web/`).
- No hay seguimiento automático de denuncias en SIDEC (no existe API).
- Sin JavaScript nuevo: la UI sigue el patrón de formularios POST del
  dashboard actual.

## Arquitectura

Dos piezas con frontera clara:

- **`casework/operacion.py` (nuevo)** — toda la lógica, sin HTTP:
  configuración, generación y manejo de LaunchAgents, corridas manuales,
  recolección de estado. `launchctl` se invoca a través de un callable
  inyectable para poder testear sin tocar el sistema.
- **`casework/dashboard.py` (se extiende)** — renderiza la sección de
  operación arriba de la lista de casos y traduce los POST a llamadas de
  `operacion.py`. Reusa `origen_permitido` para los POST.

`realtime/poll.py` aprende a leer sus defaults de la configuración (la CLI
sigue pudiendo sobreescribirlos).

## Componentes

### Configuración — `data/state/operacion.json`

Única fuente de verdad, escrita por el dashboard:

```json
{
  "poll_cada_min": 30,        // 15 | 30 | 60 | 240; null = pausado
  "batch_hora": "07:00",      // HH:MM | null = desactivado
  "threshold": 2,
  "max_detail": 40
}
```

- Escritura atómica (archivo temporal + rename).
- `realtime/poll.py`: si el archivo existe, `threshold` y `max_detail` salen
  de ahí salvo que la CLI los pase explícitos.
- `scripts/realtime_poll.sh` deja de pasar `--max-detail 40 --threshold 2`
  hardcodeados (hoy lo hace), para que la config del panel surta efecto.

### Scheduler — LaunchAgents de launchd

- `~/Library/LaunchAgents/mx.expedienteabierto.poll.plist`
  - `ProgramArguments`: `["/bin/bash", "<ROOT>/scripts/realtime_poll.sh"]`
  - `StartInterval`: `poll_cada_min * 60`
  - `StandardOutPath`/`StandardErrorPath`: `<ROOT>/data/state/poll.log`
- `~/Library/LaunchAgents/mx.expedienteabierto.update.plist`
  - `ProgramArguments`: `["/bin/bash", "<ROOT>/scripts/update_y_build.sh"]`
    (wrapper de una línea: `update.sh` + `cd web && npm run build`)
  - `StartCalendarInterval`: `{Hour, Minute}` de `batch_hora`
  - Log: `<ROOT>/data/state/update.log`

Operaciones (en `operacion.py`):

- `aplicar(config)` — escribe los plists que correspondan y los (re)carga con
  `launchctl bootout` + `bootstrap gui/<uid>`; con `poll_cada_min: null` o
  `batch_hora: null` solo descarga el agente.
- `estado_agente(label)` — parsea `launchctl print gui/<uid>/<label>`:
  cargado o no, último exit code. La próxima corrida del poll se estima como
  última corrida + intervalo (launchd no la expone).

Las corridas encimadas las evita el candado `mkdir` que ya tiene
`realtime_poll.sh` (poll manual vs. programado incluido).

### Corridas manuales

- Tres acciones POST: `poll-ahora`, `update-ahora`, `rebuild-sitio`.
- Cada una lanza el script correspondiente con `subprocess.Popen`, salida
  anexada a su log en `data/state/`.
- Una corrida manual a la vez: si hay un `Popen` vivo, los botones se
  deshabilitan y el panel muestra qué está corriendo.
- El panel muestra las últimas ~20 líneas del log de la corrida más reciente.

### Panel de estado (solo lectura)

| Dato | Fuente |
|---|---|
| Agente poll/update: activo, último exit | `launchctl print` |
| Última corrida del poll | mtime de `data/state/seen.json` + tail del log |
| Próxima corrida estimada | última + intervalo |
| Frescura de fuentes | `read_manifest()` → `retrieved_at` por archivo |
| Último build del sitio | mtime de `web/out/index.html` |
| Últimas 10 alertas | `load_alerts(limit=10)` con score y liga al portal |

## Manejo de errores

- Fallo de `launchctl` (permisos, label inexistente): el mensaje aparece en
  el panel junto al agente; la config no se revierte (el operador reintenta).
- Sistema sin launchd (no-macOS): el panel marca el scheduler como no
  disponible; las corridas manuales y el estado siguen funcionando.
- Script manual que truena: exit code y tail del log visibles en el panel.

## Pruebas

En `tests/test_operacion.py`, con `launchctl` falso inyectado:

- Config: ida y vuelta, escritura atómica, valores inválidos rechazados.
- Plists: XML bien formado, `StartInterval`/`StartCalendarInterval` correctos
  para cada frecuencia, rutas absolutas al repo.
- `aplicar()`: secuencia bootout/bootstrap correcta; pausa = solo bootout.
- `estado_agente()`: parseo de salidas reales de `launchctl print` (fixtures).
- `realtime/poll.py`: toma defaults de `operacion.json`; la CLI gana.
- Dashboard: las rutas POST nuevas pasan por `origen_permitido` (mismo patrón
  de tests que ya existe para estados de caso).
