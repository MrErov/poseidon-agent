# Dependency Map

| Context | Depends on | Depended on by | Coupling |
|---------|-----------|----------------|----------|
| api | FastAPI (fixture mínimo en `examples/health_api/`) | Kubernetes (consumidor externo) | low |

## External services
- Kubernetes — consumirá `GET /health` para comprobar que el servidor está vivo.

## Data stores
- N/A — el fixture no usa persistencia.
