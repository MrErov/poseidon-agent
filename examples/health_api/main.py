"""Fixture mínimo de la API del contexto `api`.

La historia US-002 añade ``GET /health`` sobre esta aplicación. El esqueleto
existe para que la Fase 2 no invente la estructura del proyecto.
"""

from fastapi import FastAPI

app = FastAPI(title="Fixture API")
