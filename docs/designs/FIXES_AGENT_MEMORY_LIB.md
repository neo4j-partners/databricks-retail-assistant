# Fixes Applied to neo4j-labs/agent-memory

## 1. Add Connection Liveness and Lifetime Configuration to Neo4j Driver

**Date:** 2026-02-18

**Files changed:**
- `src/neo4j_agent_memory/config/settings.py` — Added 3 fields to `Neo4jConfig`
- `src/neo4j_agent_memory/graph/client.py` — Pass new config fields to `AsyncGraphDatabase.driver()`

### Problem

When deployed to Databricks Model Serving (with scale-to-zero enabled), the Neo4j async driver holds pooled connections that go stale during idle periods. Neo4j Aura closes idle TCP connections after a timeout, but the driver is unaware and attempts to reuse the defunct sockets on the next request.

This produces cascading errors in server logs:

```
neo4j.exceptions.SessionExpired: Failed to read from defunct connection ...
neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information
ConnectionResetError: [Errno 104] Connection reset by peer
```

The agent appears to return empty results or HTTP 400 errors because product search and memory tools silently fail when Neo4j connections are dead.

### Root Cause

The `AsyncGraphDatabase.driver()` call in `graph/client.py` did not configure any connection health or lifetime parameters. The Neo4j Python driver defaults are:

- `max_connection_lifetime`: 3600s (1 hour) — far longer than Aura's idle timeout
- `liveness_check_timeout`: None (disabled) — no pre-use health check
- `keep_alive`: True (but was not explicitly set)

With no liveness check, the driver hands out stale connections from the pool without verifying they are still alive. With a 1-hour max lifetime, connections are never proactively rotated.

### Fix

Added three new configurable fields to `Neo4jConfig`:

| Field | Default | Purpose |
|-------|---------|---------|
| `max_connection_lifetime` | 300s | Proactively close and replace pooled connections older than this. Set shorter than Aura's idle timeout to prevent stale connections. |
| `liveness_check_timeout` | 60s | Before handing out a connection that has been idle longer than this, the driver pings it. If the ping fails, the connection is silently discarded and a fresh one is used. |
| `keep_alive` | True | Enable TCP keep-alive to prevent idle connection drops at the network level. |

These are passed through to `AsyncGraphDatabase.driver()` in `graph/client.py`.

### How It Fixes the Problem

- **`liveness_check_timeout`** catches connections that Aura has already closed. The driver detects the dead connection before your query runs and transparently replaces it. Application code never sees `SessionExpired`.
- **`max_connection_lifetime`** proactively rotates connections before they have a chance to go stale, reducing the window where a liveness check is even needed.
- **`keep_alive`** sends TCP keep-alive packets to prevent intermediate network infrastructure (load balancers, firewalls) from dropping idle connections.

### What This Does NOT Fix

- **Transient Neo4j outages** (server restarts, network partitions) — the driver may still raise `ServiceUnavailable` if Neo4j is genuinely unreachable. A retry/reconnect wrapper in the application layer would be needed for that.
- **Auto-commit transaction retries** — the library uses `session.run()` (auto-commit), not managed transactions (`session.execute_read()`), so the driver's built-in retry logic does not apply. This is a separate concern.

### Rebuild Required

After applying these changes, rebuild the wheel and redeploy:

```bash
cd /path/to/neo4j-labs/agent-memory
make build   # or: uv build
# Upload new wheel to Databricks Volumes or set RETAIL_AGENT_WHEEL_PATH
# Redeploy the agent
```
