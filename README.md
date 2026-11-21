# Poseidon Agent

Poseidón es el motor de ejecución determinista de **Keel Nav**. Orquesta fases descritas en Markdown, inyecta una especificación y delega la inferencia en LiteLLM. **No es un agente autónomo**: no mantiene conversaciones ni conserva estado entre ejecuciones.

## Modelo de memoria

- **Memoria Fría:** instrucciones leídas desde `Path.cwd() / ".meta-skills" / "{phase}.md"`; las fases pertenecen al proyecto objetivo, no a Poseidón.
- **Memoria Caliente:** una lista de mensajes nueva por llamada, sin historial previo.
- **Goldfish Audit:** cualquier fase cuyo nombre contenga `goldfish` o `1b` muestra `Aislando Memoria para Goldfish` y se ejecuta sin historial.

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
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
NVIDIA_NIM_API_KEY=...
```

## Uso

Ejecuta Poseidón desde la raíz del proyecto que contiene `.meta-skills/`. El argumento `--spec` es opcional para fases como Context Bootstrap y 1a:

```bash
poseidon run --phase 00-context-bootstrap --model deepseek/deepseek-chat
poseidon run --phase 1b --spec path/to/spec.md --model deepseek/deepseek-chat
```

También puedes usar, por ejemplo, `openai/gpt-4o-mini` o un modelo compatible con `nvidia_nim/`. Las claves se cargan automáticamente desde `.env`.

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
├── core.py       # PhaseRunner, memoria y comunicación con LiteLLM
├── main.py       # CLI de Typer y manejo de errores
└── __init__.py
```
