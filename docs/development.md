# Development

Three modules, three toolchains, no top-level build. Each one runs on its own; the fastest useful
thing you can do with a fresh clone is the detector's dry run (see the
[README](../README.md#quick-start-a-dry-run)), which needs neither of the other two.

Defaults everywhere assume localhost: Kafka `:9092`, MongoDB `:27017`, engine `:8080`, web `:3000`.

## Prerequisites

| module | needs |
|---|---|
| detector | Python 3.11+. For anything beyond the unit tests: the `[cv]` extra (ultralytics, opencv-python, kafka-python-ng) and both `.pt` weight files in `detector/models/` |
| engine | JDK 17, the bundled Maven wrapper. A reachable MongoDB and Kafka to do anything useful. Docker for the integration tier |
| web | Node.js and npm |

Model weights are not in git (`.gitignore` excludes `*.pt`) and are deliberately not downloaded for
you: ultralytics fetches any weights name it recognises, so a mistyped path would silently run a
stock model in place of the one this project trained. The detector refuses to start without them and
prints where to get them.

## Configuration and secrets

Nothing secret is committed. Copy the example files and fill them in:

- [`engine/.env.example`](../engine/.env.example) — four variables are **required** and have no
  fallback, so the application context refuses to start without them: `MAIL_USERNAME`,
  `MAIL_PASSWORD`, `JWT_SECRET`, `PASSWORD_RESET_AES_KEY`. Everything else has a working default.
  That exact split is pinned by `ProductionConfigurationTest`.
- [`detector/.env.example`](../detector/.env.example) — every detector setting can be given as
  `WSM_<SECTION>__<FIELD>`, or in a YAML file, or on the command line. None is required. A
  `WSM_`-prefixed name that matches no setting is **fatal at startup**, naming the key, rather than
  ignored: a misspelled override is one you believe is in force and is not.
- [`web/.env.example`](../web/.env.example) — `VITE_API_URL`, read at build time. Everything
  `VITE_`-prefixed lands in the shipped bundle, so nothing secret belongs there.
- [`.env.example`](../.env.example) at the repository root — what `docker compose` reads, covering
  all three modules plus the demo clip and the host ports.

Read [SECURITY.md](../SECURITY.md) before pointing this at anything real. Three credentials were in
the git history and must be rotated or revoked.

---

## detector

```bash
cd detector
python -m venv .venv
.venv/Scripts/activate                  # Windows; source .venv/bin/activate elsewhere

pip install -e ".[dev]"                 # tests and lint only — no torch, no opencv
pip install -e ".[cv]"                  # add this to actually run the detector
```

Run it:

```bash
python -m worksite_detector --help
python -m worksite_detector --dry-run --source clip.mp4     # no broker, nothing published
python -m worksite_detector --config detector.yaml          # publish to Kafka
python -m worksite_detector --source 0 --no-display         # webcam, no preview frame
```

Settings resolve in four layers, each overriding the last and only where it speaks: built-in
defaults, then `--config`'s YAML, then `WSM_`-prefixed environment variables, then the flags. A key
that names no setting is fatal wherever it appears, and the error names it.
[`config.example.yaml`](../detector/config.example.yaml) documents every setting and is asserted to
parse back equal to the defaults.

Exit codes: `0` clean shutdown, `2` bad configuration, `3` a resource that could not be opened
(camera, broker, weights, missing CV stack), `130` interrupted before the first frame. `SIGINT` and
`SIGTERM` finish the current frame and then run the shutdown flush, so a violation window still open
is published rather than lost.

### Tests

Two tiers, and the split is the point.

```bash
pytest -m "not requires_ultralytics"    # fast tier: 418 tests, ~1.6 s, no torch needed
pytest                                  # everything: 481 tests, ~7 s, needs the [cv] extra
pytest -m requires_ultralytics          # the integration tier alone
pytest tests/test_baseline_differential.py    # the rewrite measured against the original
```

Measured on this repository at the v1.0.0 commit. The fast tier is the whole point of the
architecture boundary: `tests/test_architecture.py` reads the AST of every module and fails if
anything except `adapters.py`, `annotate.py` and `KafkaEventPublisher.connect` imports `cv2`,
`ultralytics`, `kafka`, `torch` or `numpy`. On a machine with only the `[dev]` extra installed, a
plain `pytest` still passes — `tests/integration/conftest.py` calls `importorskip` at module scope,
so that whole directory skips rather than erroring during collection. Tests needing the weights skip
individually.

`tests/data/baseline/` holds a recorded trace of what the two models actually saw on 986 frames of a
real worksite clip — model outputs, never pixels, so it replays without weights, a camera or a GPU.
`PROVENANCE.md` says what is in it, and `DIFFERENTIAL.md` measures the rewrite against a
transcription of the original. Both are frozen at the moment they were taken; where a later
measurement disagreed with them, the correction lives in a test rather than an edit.

### Lint and types

```bash
ruff check src tools                    # clean, and what CI runs
ruff check tests                        # 11 findings today; non-blocking in CI
mypy src
```

`detector/aiModule.py` is the original
implementation, kept verbatim as the artifact the rewrite is measured against; it is not linted and
not maintained. Note that running `mypy` inside a venv that also has the `[cv]` extra can fail
inside numpy's own stubs, because `[tool.mypy]` pins `python_version = "3.11"` while numpy's stubs
use syntax added in 3.12.

---

## engine

```bash
cd engine
./mvnw spring-boot:run          # :8080
./mvnw clean package            # build, plus a JaCoCo report at target/site/jacoco/
```

The four required environment variables must be set or the context will not start — that is
deliberate; see the comments in `src/main/resources/application.yml`, which explain each one at the
point it is read.

Swagger UI: `http://localhost:8080/docs/swagger-ui.html`. OpenAPI JSON: `http://localhost:8080/docs`.

### Tests

```bash
./mvnw test                     # Surefire only: 172 tests, no Docker
./mvnw verify                   # Surefire, then Failsafe — needs a running Docker daemon
```

Surefire owns `*Test` and Failsafe owns `*IT`, both by the plugins' default includes. **A test class
named neither runs nowhere** — that is exactly how two classes named `*TestImpl` were silently
skipped for the whole life of the graduation project. Name new tests accordingly.

The integration tier starts MongoDB and Kafka in Testcontainers as static singletons in one JVM
(`forkCount=1`, `reuseForks=true`), so container startup is paid once for the whole suite rather than
once per class.

Coverage: `target/site/jacoco/` after `test` or `package` (unit only), and
`target/site/jacoco-merged/` after `verify` (unit and integration merged).

Two traps recorded in the commit log, both of which produce a green run that proved nothing:

- **`-Dtest=SomeTest` does not run `@Nested` classes.** A targeted run can report success on tests
  that never executed. Verify with a full run.
- **Testcontainers 1.21.3 negotiates Docker Engine API v1.32, which Docker 29 refuses**, reporting it
  as "Could not find a valid Docker environment" — indistinguishable from an absent daemon. The API
  version is pinned in `AbstractIntegrationTest` so IDE runs work too.

Surefire is deliberately *not* pinned to `-Duser.timezone=UTC`: pinning it would mask the whole class
of day-bucketing defects that `app.timezone` exists to prevent.

### The one-shot data migration

`PeriodicTimePeriodMigration` rewrites pre-existing `NO_HELMET`/`NO_JACKET` documents from seconds to
milliseconds and stamps `schemaVersion = 2`. It is idempotent but **off by default**
(`event.migration.periodic-to-millis.enabled: false`): a data migration must be something an operator
turns on deliberately for one boot, never something that fires because a pod restarted.

If you have data written before this release, the order is: run the migration once, then flip
`event.periodic.input-unit` to `MILLIS` when the rewritten detector is deployed.

---

## web

Vite and Vitest.

```bash
cd web
npm install
npm run dev                     # dev server on :3000 (npm start is an alias)
npm run build                   # emits to web/build/
npm test                        # vitest run
```

The port is pinned: `vite.config.js` sets `port: 3000, strictPort: true`, so a clash fails loudly
rather than drifting to another port. That matters because the engine's CORS list and the host in
every password-reset link both default to `http://localhost:3000` — whatever origin you actually
serve from must be listed in `APP_CORS_ALLOWED_ORIGINS`, which refuses `*`.

`VITE_API_URL` is the base URL of the engine API, read at build time and defaulting to
`http://localhost:8080`; see [`web/.env.example`](../web/.env.example). Only `VITE_`-prefixed
variables reach client code, and every one of them ends up in the shipped bundle — never put a
secret there.

The token lives in `localStorage` under `user` and is rehydrated into Redux as the `user` slice. An
axios request interceptor attaches it to every call, and the response interceptor treats any 403 as
logout-and-redirect; both are in `src/util/axios.js`. The preview page polls
`/event/get_image/{timestamp}` on a 100 ms interval.

---

## Running the whole system

Run by hand, you need: Kafka on `:9092`, MongoDB on `:27017`, the engine on `:8080`, the web app on
`:3000`, and a detector process pointed at a camera or a clip.

`docker-compose.yml` at the repository root brings all of that up together, with a Dockerfile per
module. Copy the root [`.env.example`](../.env.example) to `.env` first — compose reads it
automatically and refuses to start without the four engine secrets — and put a video file where
`DEMO_VIDEO_DIR`/`DEMO_VIDEO` point, because no footage ships with this repository and the detector
service is fed a mounted file rather than a camera device (a device passthrough would be Linux-only).

`demo/make_clip.py` builds one if you have nothing to hand. It assembles a clip from the two sample
photographs inside the `ultralytics` package — two populated stretches with an empty one between
them, so a violation window opens, a person-free stretch closes it, and a second one opens. It
produces genuine detections (a `NO_HELMET` and a `NO_JACKET`, each lasting about eleven seconds,
comfortably past the engine's three-second floor), but it is synthetic and says nothing about real
worksites. It is generated rather than committed on purpose: five megabytes of video that proves
nothing does not belong in a repository whose history was rewritten to get binaries out of it.

```bash
cp .env.example .env
python demo/make_clip.py     # or point DEMO_VIDEO_DIR at your own footage
docker compose up
```

The compose file sets the two halves of the preview path so they agree — the engine's
`EVENT_IMAGE_PATH` and the detector's `WSM_OUTPUT__ANNOTATED_FRAME_PATH` both point into one shared
volume — rather than relying on which directory each process happened to start in.

The stack has been verified end to end, twice, from a cold build cache and no volumes: all services
healthy in about 15 seconds, detections in MongoDB within 35, the preview endpoint serving a real
JPEG, CORS refusing an unlisted origin, and a missing secret failing before any container starts
with a message naming the variable and the command to generate one.

Two caveats that are properties of the demo rather than of the stack. The bundled clip is
**synthetic** — built from the sample images inside the `ultralytics` package, because no real
footage is redistributable — so it exercises the pipeline without saying anything about real
worksites. And a video file's timestamps run from the start of the clip, not the wall clock, so
events captured from a file are stored against 1 January 1970 and a dashboard showing today's range
will look empty while the collection is full. That is the detector's time source, not a compose
setting; live camera input does not have it.

Sanity checks, cheapest first:

1. `python -m worksite_detector --dry-run --source clip.mp4` — the detector works at all.
2. Drop `--dry-run`. The detector logs the topic and broker it is publishing to; the engine logs
   `Listener received: ...` for each event.
3. `GET /event/all-events` with a bearer token — events reached MongoDB.
4. `GET /event/get_image/0` — the preview file is where the engine is looking. A 404 here means
   `event.image.path` does not point at the directory the detector is writing `output_image.jpg`
   into.

---

## Adding a new event type

An event type is one of the few things that genuinely spans all three modules. In order:

1. **detector** — add the member to `EventType` in `events.py`. If it is periodic, `is_periodic`
   must say so; the constructor validation and `PpeViolationTracker` both branch on it. Then emit it:
   a new PPE class goes in `_EVENT_TYPE_BY_LABEL` in `pipeline.py`; a new gesture goes in
   `_DEFAULT_GESTURES` in `config.py`, where `Config` will refuse it if its visibility gate does not
   cover every keypoint it measures.
2. **engine** — add the constant to `EventNameEnum`. `RawEventService` derives its accepted set from
   the enum, so ingest needs nothing further; but `EventService` holds explicit type lists per
   endpoint (countable, pie chart, periodic, all-events), and a type missing from them is stored and
   then invisible. A new periodic type also needs a column in `PeriodicEvents` and its own branch in
   `calculatePeriodicEvents`; a new countable type needs the same in `CountableEvents`.
3. **web** — add it to the chart key/colour arrays in `web/src/pages/ChartsContainer`, or it will be
   aggregated by the API and drawn by nothing.
4. **tests** — `detector/tests/test_events.py` reads `EventNameEnum.java` directly, so the two enums
   are compared for you; it will fail until both sides agree.

A type added to the detector but not the engine is dropped at ingest with a `WARN` naming it — which
is the failure you want, and is why that guard exists.
