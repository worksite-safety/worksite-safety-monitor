# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

A worksite-safety monitoring system: three independently-run modules that communicate over Kafka
and HTTP.

```
detector (Python/YOLOv8)  --Kafka "rawEvents"-->  engine (Spring Boot)  --REST/JWT-->  web (React)
   camera or video file          JSON RawEvent          MongoDB "event"       charts / grid / PDF
```

It began as a three-person graduation project (Oct 2023 – Jan 2024) and was rewritten for open
source in Aug 2026. The rewrite is done; the release is gated on licensing consent from the two
co-authors. **The repository is private until that arrives.**

## Commands

Each module runs on its own. There is no top-level build. `docker compose up` runs everything.

**detector** (Python 3.11+, run from `detector/`):
```
pip install -e .[dev]                       # no torch, fast
pip install -e .[cv]                        # ultralytics, opencv, kafka -- ~2 GB
pytest -m "not requires_ultralytics"        # 414, under a second, the inner loop
pytest                                      # 481 with the CV stack installed
ruff check src tools
python -m worksite_detector --dry-run --source clip.mp4
```
The venv at the repository root (`.venv`) has both extras installed.

**engine** (Java 17, Maven wrapper, run from `engine/`):
```
export JAVA_HOME="/c/Users/aziz/.jdks/corretto-17.0.20"   # JDK 25 is the default and will NOT work
./mvnw -B clean test        # 178 unit, Docker-free, ~9 s
./mvnw -B clean verify      # + 22 integration via Testcontainers, needs Docker
```

**web** (Vite, run from `web/`):
```
npm ci && npm test && npm run build
```

**demo clip** — not committed, generate it:
```
python demo/make_clip.py
```

## Things that will waste your time if you do not know them

- **`./mvnw` fails on the default JDK.** Boot 3.0.4's Lombok cannot run on JDK 21+, and this
  machine defaults to 25. Export `JAVA_HOME` to corretto-17 for every Maven command.
- **`-Dtest=SomeTest` does not run `@Nested` classes.** A targeted run reports green on tests it
  never executed. Verify with a full run.
- **Surefire has no `-Duser.timezone`, deliberately.** Pinning the JVM to UTC would mask the
  day-bucketing defects that three tests exist to catch.
- **The detector's fast tier is 414, not 418.** Two tests assert that torch and cv2 *are*
  importable — they are the guards that stop the import-blocking proofs elsewhere passing
  vacuously — so a job without the CV stack deselects exactly those two.
- **`tests/test_architecture.py` is load-bearing.** It parses each module's AST and fails if
  `cv2`, `ultralytics`, `kafka`, `torch` or `numpy` appears anywhere outside `adapters.py`,
  `annotate.py` and `publisher.py`. That boundary is why the unit suite runs in under a second.
  `__main__.py` is **not** exempt, and the check walks function bodies too, so a lazy import does
  not escape it.
- **Video-file input timestamps run from the start of the clip, not the wall clock.** Events from
  a file are stored against 1 Jan 1970, so a dashboard showing today looks empty while the
  collection is full. Live camera input does not have this.

## Architecture

### Event pipeline

`detector/src/worksite_detector/pipeline.py` runs one linear flow per frame: pose model, PPE model,
rules, publish, write the annotated frame. **Every frame takes the same path.** The original
skipped the rest of the frame whenever the pose model found nobody, which lost a fall (a person on
the ground is what a pose model is worst at detecting) and froze the preview.

`RawEventService.listener` is the only consumer and the only place events are persisted. It drops
malformed and unrecognised events with one warning rather than retrying or storing them.

### Event taxonomy

`EventNameEnum` splits two ways, and the whole stack treats them differently:
- **Countable** — `FALL`, `ARMS_UP`, `FRONT_BEND`: counted per day.
- **Periodic** — `NO_HELMET`, `NO_JACKET`: durations summed per day.

Adding an event type touches three places: the detector's `EventType`, `EventNameEnum` plus the
type lists in `EventService`, and the `keysAndColors*` arrays in `web/src/pages/ChartsContainer.jsx`.
A cross-module test derives the JSON key set from `RawEvent.java` by regex, so the two sides cannot
drift silently.

### Units — the one contract most likely to bite

`timePeriod` is **milliseconds** on the wire and in MongoDB, and **seconds** in every API response.
`event.periodic.input-unit` declares what the producer sends so the two repositories can deploy
independently. Both misreadings are silent and fail in opposite directions: milliseconds read as
seconds multiply everything by 1000; seconds read as milliseconds store nothing at all.

`Event.schemaVersion` records which unit a stored document is in. Absent means seconds (pre-
migration); 2 means milliseconds. It must never travel on the wire.

### Auth

Stateless JWT, 20-minute expiry, no refresh. `SecurityConfiguration` holds `PUBLIC_URLS` and
`ADMIN_URLS`; anything unlisted falls to `.anyRequest().authenticated()`. `Role` has one value, so
`ADMIN_URLS` means "any logged-in user". **Unauthenticated requests answer 403, not 401** — the
frontend's logout interceptor depends on that, and it is a known deviation that a later slice may
correct, at which point the interceptor silently stops working.

### The "stream"

Not a stream. The detector writes `output_image.jpg` through a temp file and `os.replace`;
`EventController.getImage` serves it; the web app polls every 100 ms. Writing in place served half
a JPEG on 108 of 130 reads, which is why the rename matters. `EVENT_IMAGE_PATH`'s trailing slash is
load-bearing — the controller concatenates strings.

## Conventions

- Backend is feature-first (`user/`, `event/`, `rawEvent/`, `email/`) with `controller/`, `service/`,
  `model/`, `repository/`; cross-cutting config under `core/`. Lombok throughout, 2-space indent.
- Detector modules are pure Python with injected collaborators — clock, publisher, models, sink.
  Nothing reads the wall clock except `__main__`; rules take timestamps as arguments.
- Frontend styling is styled-components under `src/assets/wrappers/`, TanStack Table for the
  reporting grid, recharts for charts. Redux Toolkit 2.x for the `user` slice only; page data is
  `useState` + `customFetch`.
- Commit messages explain **why**, in prose, not bullet lists. The git log is the primary record of
  what was measured and decided; read it before assuming something is arbitrary.

## Testing culture

Tests here were written by a different author than the implementation, deliberately. Several
encode a measurement rather than an opinion, and their comments say which. Before changing an
assertion, read its comment — a surprising number pin a defect on purpose, and a few record that a
different choice was considered and rejected.

Where a test says a value was **measured**, it was: the grace window, the boundary inclusivity, the
BSON storage type, the confidence provenance. Do not replace a measured number with a plausible one.

## Known limitations, all measured

- PPE violations are counted **globally**, not per person: three unhelmeted workers in one frame
  produce one event.
- **Person identity is not stable across frames.** Ids are positions in one frame's detection
  output with no tracker, so gesture counters are approximate with more than one person in shot.
- **Gesture detection is unproven on real footage.** Replaying 986 frames of a real worksite emitted
  zero `ARMS_UP` and zero `FRONT_BEND` — nobody in that clip raised their arms or bent over. The
  rules have synthetic coverage only. The same is true of `NO_HELMET`: the baseline clip contains
  no examples at all.
- A `FALL` emails **every registered user**.
- One camera, one role, no refresh tokens, no Kafka schema registry, no volume on Kafka.

## Outstanding, and blocking release

1. **Rotate `JWT_SECRET` and `PASSWORD_RESET_AES_KEY`.** Both old values are in git history. The
   AES key is the urgent one: it encrypts the token that authorises a password change and that
   token has no expiry, so anyone holding it can mint a reset link for any account.
2. **Revoke the Gmail app password** at Google. Removed from history; that does not un-leak it.
3. **AGPL consent from Emre Yılmaz and Nil Emekci.** The only thing gating public release.

`~/oss-release/` holds the pre-rewrite backups and the model weights. **`best.pt` is not
reproducible** — the training dataset is not in the repository. Do not delete that directory.

Both weights are now also published as assets of the [`weights-v1`](https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1)
pre-release, with their SHA256 in the notes, so `best.pt` is no longer a single local copy. That
release deliberately does **not** use the `v1.0.0` tag: it carries assets, not a version of this
code, and `v1.0.0` stays unclaimed until item 3 above clears and the repository goes public. Being
a pre-release, it is never GitHub's "Latest", so `v1.0.0` can take that place when it is cut.
