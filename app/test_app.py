"""Smoke tests for the notes app. Run: python test_app.py (no Redis needed)."""
import redis
from fastapi.testclient import TestClient

import main


class FakeRedis:
    def __init__(self, up=True):
        self.up, self.data = up, []

    def _check(self):
        if not self.up:
            raise redis.ConnectionError("down")

    def ping(self):
        self._check()
        return True

    def lrange(self, key, start, end):
        self._check()
        return list(self.data)

    def rpush(self, key, value):
        self._check()
        self.data.append(value)


c = TestClient(main.app)

# Redis down -> alive but not ready, API returns 503
main.rdb = FakeRedis(up=False)
assert c.get("/healthz").status_code == 200
assert c.get("/readyz").status_code == 503
assert c.get("/api/notes").status_code == 503

# Redis up -> ready, notes work
main.rdb = FakeRedis(up=True)
assert c.get("/readyz").status_code == 200
assert c.post("/api/notes", json={"text": "hello"}).status_code == 201
assert c.get("/api/notes").json() == {"notes": ["hello"]}
assert "Notes Demo" in c.get("/").text

# Chaos: forced unready toggles
assert c.post("/chaos/unready").json() == {"force_unready": True}
assert c.get("/readyz").status_code == 503
c.post("/chaos/unready")
assert c.get("/readyz").status_code == 200

# Chaos: leak grows, slow sleeps
assert c.post("/chaos/leak?mb=5").json()["leaked_total_mb"] == 5
assert c.post("/chaos/leak?mb=5").json()["leaked_total_mb"] == 10
assert c.get("/chaos/slow?seconds=0.1").status_code == 200

# Metrics exposed
m = c.get("/metrics").text
assert "http_requests_total" in m and "chaos_leaked_megabytes 10.0" in m

print("ALL TESTS PASSED")
