from fastapi import FastAPI

from backend.app.config import settings
from backend.app.middleware.logging import JsonLogMiddleware
from backend.app.routers import catalog, events, graph, monitoring, popular, search

app = FastAPI(
    title="Pinakes 2.0 API",
    version="0.1.0",
    description="Polyglot NoSQL library catalog. Endpoints return 501 until implemented.",
)

app.add_middleware(JsonLogMiddleware, log_file=settings.api_log_file)

# All routers are registered here once (Day 1). After that nobody edits this file:
# each member only edits their own router files.
app.include_router(catalog.router)  # A
app.include_router(search.router)  # A
app.include_router(popular.router)  # A
app.include_router(graph.router)  # B
app.include_router(events.router)  # B
app.include_router(monitoring.router)  # B


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
