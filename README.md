# URL Shortener

[![CI](https://github.com/liguebez/url-shortener/actions/workflows/ci.yml/badge.svg)](https://github.com/liguebez/url-shortener/actions/workflows/ci.yml)

Shorten a long URL, redirect a short one. I built this to implement a system
design I had studied, so the decisions below matter more than the code volume.

Keys are 7 base62 characters. 62^7 is about 3.5 trillion, which covers 1000
writes/sec for 10 years. Reads are assumed at roughly 10x writes.

Python 3.14, FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, Postgres 17,
Redis 8, Docker Compose.

## Endpoints

| Method | Path                   | Behaviour |
|--------|------------------------|-----------|
| POST   | `/api/urls`            | `{long_url}` -> `201 {short_id, short_url}`, `400` if rejected |
| GET    | `/{short_id}`          | `302` to the long URL, `404` unknown, `410` expired or deleted |
| GET    | `/api/urls/{short_id}` | `200` metadata |
| GET    | `/healthz`             | pings Postgres and Redis |

Swagger UI at `/docs`.

## Running it

```bash
cp .env.example .env      # set POSTGRES_PASSWORD, update DATABASE_URL to match
docker compose up -d
curl localhost:8000/healthz
```

Migrations run from the container entrypoint, so nothing else is needed.

```bash
curl -s -X POST localhost:8000/api/urls \
  -H 'content-type: application/json' \
  -d '{"long_url":"https://example.com/some/long/path"}'
# {"short_id":"mvvNtWx","short_url":"http://localhost:8000/mvvNtWx"}

curl -i localhost:8000/mvvNtWx
# HTTP/1.1 302 Found
# location: https://example.com/some/long/path
# cache-control: no-store
```

Use `curl -i`, not `curl -L`. The body is empty and `-L` follows the redirect
off to the target instead of showing you the 302.

### Without Docker for the app

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload
```

`alembic upgrade head` is manual here. The entrypoint only runs inside the api
container, so starting `db` and `redis` alone leaves the schema unmigrated.

`DATABASE_URL` and `REDIS_URL` in `.env` point at `127.0.0.1` for this workflow.
Compose overrides both with the service names `db` and `redis` when the api runs
in a container.

## Tests

```bash
docker compose up -d db redis
docker compose exec db createdb -U shortener shortener_test
pytest
```

284 tests. Redis is faked with `fakeredis`, so only Postgres has to be running.
CI needs one service container instead of two for the same reason.

Each test runs inside a transaction that is rolled back afterwards. This needed
`join_transaction_mode="create_savepoint"` on the test session, because
`create_short_url` calls `session.commit()` and that would otherwise write for
real.

## Design decisions

### Random keys instead of an encoded counter

Base62-encoding an auto-increment id is compact and cannot collide. It is also
enumerable: given one short id you can decrement it and walk every link in the
system.

So keys are 7 random base62 characters from `secrets`, with `short_id` as the
primary key and a bounded retry on unique violation. `random` is not used, it is
seeded predictably.

Each attempt runs inside `begin_nested()`. Without the savepoint a collision
poisons the transaction and the retry raises instead of retrying. I found this
by writing the test for it.

Five attempts, then `503`. At 3.5 trillion keys, hitting that means something
else is wrong.

### 302 instead of 301

301s get cached by browsers and proxies, often permanently. A cached 301 cannot
be revoked, expired, or counted, because those requests never reach the service
again.

302 plus `Cache-Control: no-store` costs a round trip per click and keeps every
resolution under the service's control.

### Caching misses as well as hits

Plain cache-aside leaves a hole. Lookups for ids that do not exist miss the cache
every time and go straight to Postgres, so scanning random 7-character strings
bypasses Redis entirely. That is cache penetration.

Misses are cached as sentinels, `\x00missing` and `\x00gone`. They cannot collide
with a stored URL because they have no scheme and the validator rejects them.

Negative entries get 60s against 3600s for real entries, so a link created just
after someone probed for it is not invisible for an hour. Creation also deletes
the key, so usually the wait is zero.

### allkeys-lru and per-entry TTL together

TTL bounds staleness. A link deleted out of band stops being served when its
entry expires.

LRU bounds memory. Past `maxmemory` Redis evicts cold keys instead of rejecting
writes.

TTL alone lets the cache outgrow its budget. LRU alone can keep a hot stale key
indefinitely. The cached TTL is also clamped to the URL's own `expires_at`, so an
entry never outlives what it points at.

### The same URL twice gives two different ids

Deduplicating with a unique index on `long_url` would save rows and couple
unrelated users. One person's deletion would break the link for everyone who
shortened the same target, and ownership becomes unattributable. Rows are cheap.

### Migrations in the container entrypoint

`alembic upgrade head` runs before uvicorn starts, so a fresh environment
converges with one `docker compose up`.

With N replicas all N race to migrate and Alembic takes no advisory lock.
Transactional DDL means this produces one winner and N-1 errors rather than a
broken schema, but it is not clean. The alternative is a one-shot migrate service
gated on `depends_on: {condition: service_completed_successfully}`. At one replica
the entrypoint is simpler.

### `--only-binary=:all:` and no compiler in the image

Every dependency ships a manylinux wheel for cp314, so the runtime image has no
build toolchain. I had `build-essential` in a builder stage as insurance first,
and it added minutes to every build while compiling nothing.

`--only-binary=:all:` makes that explicit. A future dependency without a wheel
fails on resolution instead of dying inside `gcc: not found`.

## Benchmark

`hey -disable-redirects -n 5000 -c 50`, after a 500 request warm-up, against the
compose stack. Redirect following has to be off or `hey` benchmarks the target
site and reports `NaN`.

Apple Silicon, 10 cores, all containers on one host, one uvicorn worker,
SQLAlchemy pool of 10 plus 5 overflow, one row in the table.

| Scenario | req/s | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| Redirect, cache hit | 3442 | 14.5 ms | 16.0 ms | 17.4 ms |
| Metadata endpoint, never cached | 2885 | 15.8 ms | 41.3 ms | 65.1 ms |
| Redirect, key deleted continuously | 1658 | 32.5 ms | 48.5 ms | 71.1 ms |
| Redirect, Redis stopped | 435 | 114.0 ms | 120.2 ms | 126.7 ms |

The cache looks much weaker than expected. During the cached run the api
container sat at 125% CPU and Postgres at 0.00%, so the bottleneck is the Python
process, not the database. A cache cannot help when nothing is waiting on the
thing being cached.

That is the setup, not the design:

- One row in the table, so the lookup is served from Postgres's buffer cache. At
  millions of rows with a cold cache it becomes a disk read.
- Postgres is on localhost. In a real deployment it is across a network.
- One uvicorn worker caps throughput near 3000 req/s regardless of the handler.

The percentiles are the useful column. Uncached is 2.6x worse at p95 and 3.7x
worse at p99 even here. Cache-aside buys tail latency and database load before it
buys throughput.

The Redis-stopped row is not a fair comparison, since every request also pays two
refused TCP connections. It is included because it shows the service still
returns correct 302s with Redis gone. `get_cached` and `set_cached` catch
`RedisError` and log it, so Redis is an optimisation rather than a dependency.
`/healthz` reports `degraded` while redirects keep working.

### Reproducing

```bash
docker compose up -d
SHORT=$(curl -s -X POST localhost:8000/api/urls \
  -H 'content-type: application/json' \
  -d '{"long_url":"https://example.com/benchmark-target"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["short_id"])')

curl -s -o /dev/null "localhost:8000/$SHORT"
hey -disable-redirects -n 5000 -c 50 "http://localhost:8000/$SHORT"

docker compose stop redis
hey -disable-redirects -n 5000 -c 50 "http://localhost:8000/$SHORT"
docker compose start redis
```

## Known gaps

**`/healthz` checks liveness, not readiness.** It runs `SELECT 1`, which proves a
connection exists and nothing about the schema. I hit this after a
`docker compose down -v`: healthz reported `"database":"ok"` while every write
returned 500, because the `urls` table did not exist. Checking
`to_regclass('public.urls')` would catch it. With migrations in the entrypoint a
container that reaches serving has migrated, so this only shows up in the
host-uvicorn workflow.

**The test fixture hardcodes `decode_responses=True`** instead of deriving it
from `create_redis`. Tests never call `create_redis`, so flipping that flag in
`app/cache.py` would keep the suite green while the sentinel comparisons silently
stopped matching in production.

**Tests use `create_all`, not the migrations.** Faster, but it means the suite
exercises the model rather than the migration chain. `alembic check` runs in CI to
catch drift between the two.

**`docker compose down -v` drops every database in the volume.** Recreating the
app schema with `alembic upgrade head` does not bring `shortener_test` back, since
Alembic only migrates what `DATABASE_URL` points at. You need `createdb` as well.
CI does not notice, because the service container creates it from `POSTGRES_DB`
on every run.

**Alternate IP encodings are not blocked.** Decimal and octal forms of loopback
and private addresses pass validation. Tests name this as `known_gap_`.

## Not built

**Sharding.** One Postgres handles 1000 writes/sec. If it were needed, random keys
make it straightforward: hash `short_id` to a shard. Every operation is a single
key lookup with no joins or range scans. The counter scheme rejected above would
have made this harder.

**Read replicas.** At 10:1 reads with a cache in front, replicas mostly serve
traffic Redis already absorbs. They matter for surviving a primary failure, and
the problem there is replication lag: a link created and clicked immediately can
404 against a stale replica. Read from the primary for a window after a write, or
treat a replica miss as a reason to check the primary.

**Click analytics.** Counting inline puts a write on the hottest path and undoes
the cache. It belongs on a queue, aggregated separately, which is a second system.

**Custom aliases, accounts, rate limiting.** All doable, none of them exercise a
decision not already made somewhere else.

## Layout

```
app/
  main.py           lifespan, routers, 400 handler for validation errors
  config.py         pydantic-settings
  db.py             engine, session factory, per-request session
  cache.py          Redis client, sentinels, TTL clamping, error swallowing
  models.py         Url model
  schemas.py        request and response models
  routes/           health, urls, redirect
  services/urls.py  create with retry, resolve through the cache
  utils/            base62, URL validation
alembic/            async migration setup
tests/              fixtures, cache, API, redirect, collision tests
docker/entrypoint.sh
.github/workflows/  lint, tests, migration drift, image build
```
