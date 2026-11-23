<div align="center">
  <img src="docs/assets/logo.png" alt="Logo de Poseidón Agent" width="220" />
  <h1>🔱 Poseidón Agent</h1>
  <p><strong>The deterministic execution engine for Keel Nav.</strong></p>
  <p>
    <a href="https://github.com/MrErov/poseidon-agent/releases/tag/v1.0.0-alpha">
      <img alt="GitHub release" src="https://img.shields.io/github/v/release/MrErov/poseidon-agent?include_prereleases&amp;sort=semver" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/blob/main/pyproject.toml">
      <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg" />
    </a>
    <a href="https://github.com/MrErov/poseidon-agent/tree/main/tests">
      <img alt="Tests: 47 passed" src="https://img.shields.io/badge/tests-47%20passed-brightgreen.svg" />
    </a>
  </p>
</div>

Poseidón es el motor de ejecución determinista de **Keel Nav**. Orquesta fases descritas en Markdown, inyecta una especificación y delega la inferencia en LiteLLM. **No es un agente autónomo**: no mantiene conversaciones ni conserva estado entre ejecuciones.

## Why Poseidón?

Frente a herramientas autónomas como **Hermes-Agent**, Poseidón no decide su propio rumbo ni improvisa pasos. Es un orquestador que ejecuta exactamente el protocolo Keel Nav y hace explícitas sus restricciones:

- **Memory Flush:** cada fase recibe mensajes nuevos; Goldfish siempre se ejecuta con Memoria Caliente vacía.
- **Gatekeeper:** bloquea la Fase 2 si el spec no alcanzó `audited` o `approved`.
- **State Machine:** solo los veredictos válidos permiten transiciones como `draft → audited → observed → certified`.
- **Ejecución determinista:** carga la Memoria Fría del proyecto objetivo, usa `temperature=0.0` en la API y conserva los artefactos y veredictos como evidencia.

Poseidón no sustituye al Navigator ni a las reglas de Keel Nav: las hace ejecutables y verificables.

## Ecosystem

| Componente | Responsabilidad |
|------------|-----------------|
| **Keel Nav** | Define las fases, plantillas, compuertas y convenciones que forman la Memoria Fría. |
| **Poseidón Agent** | Resuelve fases, aísla memoria, delega inferencia, guarda artefactos y aplica la máquina de estados. |
| **Plugin de DeepSeek** | Proporciona el punto de contacto e invocación desde la experiencia DeepSeek; no sustituye al motor ni implica usar la API de DeepSeek. |
| **NVIDIA NIM o CLIs locales** | Ejecutan la inferencia a través de LiteLLM o de Claude Code, Codex y OpenCode. |
| **Graphify MCP** | Añade opcionalmente contexto dinámico del grafo de código a las fases 1a y 1b. |

Keel Nav aporta el protocolo, Poseidón lo ejecuta y el plugin de DeepSeek facilita su uso dentro del ecosistema, manteniendo cada responsabilidad separada.


## Arquitectura

```mermaid
graph TD
    CLI[poseidon run --phase X] --> Runner[PhaseRunner]
    Runner --> StateMachine[State Machine / Gatekeeper]
    StateMachine --> ColdMemory[Lee .meta-skills/ y specs/]
    ColdMemory --> Decision{¿Executor?}
    Decision -- API --> LiteLLM[LiteLLM / NVIDIA NIM]
    Decision -- CLI Local --> Subprocess[Claude Code / Codex / OpenCode]
    LiteLLM --> Result[Respuesta del LLM]
    Subprocess --> Result
    Result --> AutoSave[Auto-Save de Artefactos]
    Result --> SpecUpdate[Actualizar status: del Spec]
    AutoSave --> Done[Éxito]
    SpecUpdate --> Done
```

## Modelo de memoria

- **Memoria Fría:** instrucciones resueltas desde `.meta-skills/` mediante alias de fase o nombre exacto del archivo; las fases pertenecen al proyecto objetivo, no a Poseidón.
- **Memoria Caliente:** una lista de mensajes nueva por llamada, sin historial previo.
- **Contexto:** el contenido de `--context` se inyecta antes del `--spec` en la Memoria Caliente.
- **Goldfish Audit:** cualquier fase resuelta como `02-egm-goldfish-audit` muestra `Aislando Memoria para Goldfish` y se ejecuta sin historial.

## Alias de fases

| Alias | Archivo en `.meta-skills/` |
|-------|----------------------------|
| `0`, `00`, `context` | `00-context-bootstrap.md` |
| `1a`, `spec` | `01-sdd-spec-writer.md` |
| `1b`, `goldfish` | `02-egm-goldfish-audit.md` |
| `2`, `tdd` | `03-tdd-cycle.md` |
| `3`, `odd` | `04-odd-vertical-slice.md` |
| `4`, `drift` | `05-drift-control.md` |

También puedes pasar el nombre exacto del archivo, con o sin `.md`. Si la fase no coincide con un alias, Poseidón busca un `.md` cuyo nombre empiece por la fase o la contenga; si no encuentra ninguno, termina con un error controlado. Esta resolución se usa tanto para cargar la Memoria Fría como para decidir el guardado de artefactos y la actualización del spec.

## Requisitos e instalación

Necesitas Python 3.10 o superior y [uv](https://docs.astral.sh/uv/).

```bash
uv venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
uv pip install -e .
```

Crea un archivo `.env` con las credenciales del proveedor que vayas a usar. Por ejemplo:

```dotenv
NVIDIA_NIM_API_KEY=...

# Opcional: activa Graphify MCP para las fases 1a y 1b.
GRAPHIFY_MCP_URL=https://api.graphify.com/mcp
```

## Uso

Ejecuta Poseidón desde la raíz del proyecto que contiene `.meta-skills/`. El argumento `--spec` es opcional para fases como Context Bootstrap y 1a:

```bash
poseidon run --phase 00-context-bootstrap --model nvidia_nim/<modelo-disponible>
poseidon run --phase 1a --spec specs/US-001.md --context docs/context/api.md --model nvidia_nim/<modelo-disponible>
poseidon run --phase 1b --spec specs/US-001.md --context docs/context/api.md --model nvidia_nim/<modelo-disponible>
```

Sustituye `<modelo-disponible>` por el identificador del modelo que tengas habilitado en NVIDIA NIM. Las credenciales se cargan automáticamente desde `.env`.

### Ejecutores locales (Delegation Engine)

Con `--executor api` (valor predeterminado), Poseidón usa LiteLLM y `--model` es obligatorio. También puedes delegar el prompt a un CLI local ya instalado y autenticado; en ese caso `--model` se omite y la herramienta usa su propia configuración:

```bash
poseidon run --phase 1b --spec specs/US-001.md --context docs/context/api.md --executor claude-code
poseidon run --phase 2 --spec specs/US-001.md --executor codex
poseidon run --phase 0 --executor opencode
```

| Executor | Invocación |
|----------|------------|
| `claude-code` | `claude -p --output-format text`, con el prompt por stdin |
| `codex` | `codex exec -`, con el prompt por stdin |
| `opencode` | `opencode run -`, con el prompt por stdin |

Cada delegación recibe un prompt nuevo, incluida la ejecución aislada de Goldfish. Los tres ejecutores reciben el prompt mediante `stdin`, nunca como argumento posicional, para evitar los límites de longitud de la línea de comandos del sistema operativo. Los subprocesos tienen un timeout de 300 segundos, no usan shell y lanzan un error controlado si el ejecutable no está disponible, exceden el tiempo o terminan con código distinto de cero.

Si el ejecutable no está en `PATH`, puedes indicar su ruta con `POSEIDON_CLAUDE_CODE_BIN`, `POSEIDON_CODEX_BIN` o `POSEIDON_OPENCODE_BIN`.

### Graphify MCP (opcional)

Define `GRAPHIFY_MCP_URL` para enriquecer las fases `1a` y `1b` con contexto del grafo de código. La URL predeterminada sugerida es `https://api.graphify.com/mcp`. Poseidón consulta usando la ruta de `--spec`, o la de `--context` si no hay spec, e inyecta la respuesta entre el contexto y la especificación.

Si la variable no está configurada, está vacía, la petición falla o la respuesta no contiene texto aprovechable, Poseidón continúa sin contexto Graphify y sin interrumpir la ejecución.

### Artefactos automáticos

Las fases que producen Markdown se guardan en `specs/` (relativo al proyecto donde se invoca Poseidón):

| Fase | Archivo generado |
|------|------------------|
| `1a` | `specs/<nombre>.spec.md` |
| `1b` o `goldfish` | `specs/<nombre>.audit.<N>.md` (el siguiente número libre) |
| `2` o `tdd` | Solo consola |
| `3` u `odd` | `specs/<nombre>.observation.md` |
| `4` o `drift` | `specs/<nombre>.drift.<N>.md` (la siguiente ronda libre) |

El nombre se deriva del `--spec` (o del `--context` si no hay spec), eliminando la extensión `.md` o `.spec.md`. Al guardar, Poseidón muestra `✅ Guardado en specs/...` en verde. Un fallo de escritura se reporta como error controlado con código de salida `1`.

### Máquina de estados del spec

Después de una auditoría `1b` o `goldfish`, Poseidón busca `verdict` o `effective_verdict` en el reporte generado:

- `audited`: actualiza únicamente el frontmatter del spec (`status: draft` → `status: audited` y `goldfish_audit: pending` → `specs/<nombre>.audit.<N>.md`) y muestra `✅ Spec actualizado a status: audited`.
- `rejected` o veredicto ausente: no modifica el spec y muestra `⚠️ Auditoría rechazada. El spec sigue en draft.`

La actualización se limita al frontmatter inicial: `us_id`, `created_at` y el resto de campos y del cuerpo Markdown se conservan intactos.

En la Fase 3 (`odd`), Poseidón guarda la observación y, si el reporte declara `verdict: approved`, `effective_verdict: approved` o `status: observed`, actualiza el spec a `status: observed`.

En la Fase 4 (`drift`), `no-drift` y `drifted-accepted` actualizan el spec a `status: certified` y registran `drift_report`. Un veredicto `drifted` conserva el spec intacto y muestra `❌ Drift rechazado. El spec no puede ser certificado`. Si `effective_verdict` está presente, prevalece sobre `verdict`.

### Gatekeeper TDD

La fase `2` y cualquier fase que contenga `tdd` exigen un spec cuyo frontmatter tenga `status: audited` o `status: approved`. Un estado como `draft`, un status ausente o la falta del spec bloquean la ejecución antes de llamar al LLM.

Si una fase requerida o una especificación proporcionada no existe, Poseidón termina con código `1` y muestra un error en rojo.

## Desarrollo

```bash
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check .
```

Estructura principal:

```text
src/poseidon/
├── core.py        # PhaseRunner, memoria y selección de ejecutor
├── delegator.py   # Delegación a CLIs locales con subprocesos
├── main.py        # CLI de Typer y manejo de errores
├── mcp_client.py  # Integración opcional con Graphify MCP
└── __init__.py
```
