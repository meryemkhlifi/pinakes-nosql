import json
import time
from datetime import datetime, timezone
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware


class JsonLogMiddleware(BaseHTTPMiddleware):
    # Writes one JSON line per request. Filebeat ships this file to Logstash.

    def __init__(self, app, log_file: str = "./logs/api.log"):
        super().__init__(app)
        self.path = Path(log_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = request.client.host if request.client else ""
            line = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "client_ip": client_ip,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "user_agent": request.headers.get("user-agent", ""),
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
