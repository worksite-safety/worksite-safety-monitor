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
source in Aug 2026. The rewrite is done, and all three co-authors have since given written consent
to AGPL-3.0-or-later — `NOTICE` records that and when. **The repository is still private**, and what
holds it there is now the credential work under "Outstanding" below, not the licensing.

## Commands

Each module runs on its own. There is no top-level build. `docker compose up` runs everything.

**detector** (Python 3.11+, run from `detector/`):
```
pip install -e .[dev]                       # no torch, fast
pip install -e .[cv]                        # ultralytics, opencv, kafka -- ~2 GB
pytest -m "not requires_ultralytics"        # 418 pass in ~2 s, the inner loop
pytest                                      # 481 collected: 465 pass, 16 skip, ~4 s
ruff check src tools
python -m worksite_detector --dry-run --source clip.mp4
```
The venv at the repository root (`.venv`) has both extras installed.

**engine** (Java 17, Maven wrapper, run from `engine/`):
```
export JAVA_HOME="/c/Users/aziz/.jdks/corretto-17.0.20"   # JDK 25 is the default and will NOT work
./mvnw -B clean test        # 178 unit, Docker-free, ~20 s
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

- **`./mvnw` fails on the default JDK, and not for the reason it looks like.** The build fails on
  JDK 23 and on JDK 25 — this machine defaults to 25 — and passes on corretto-17. It fails as
  hundreds of `cannot find symbol: builder()` and `getEmail()`: Lombok never ran, and javac prints
  nothing to say so. That is not a Lombok-versus-JDK incompatibility, and correcting the Boot
  version would not fix it. Lombok is 1.18.46 here and
  `./mvnw clean test -Dmaven.compiler.proc=full` passes all 178 on JDK 25. javac 23 and 25 do not
  run an annotation processor they merely find on the classpath; javac 17 does. Export `JAVA_HOME`
  to corretto-17 for every Maven command and the question never comes up.
- **A targeted `-Dtest=` run can still report green having executed nothing.** The old form of this
  trap is gone: under Surefire 3.5.6, `-Dtest=EventServiceTest` runs all 39, the 3 in its `@Nested`
  class included. Method selection did not follow. `-Dtest='EventServiceTest#allDayBucketing...'`
  names a test inside that nested class, runs **0 tests** and exits BUILD SUCCESS; the same
  selection against an outer method runs its 1 test. Surefire's "no tests matching pattern" guard
  does not save you, because the class half of the pattern did match. Verify with a full run.
- **Surefire has no `-Duser.timezone`, deliberately.** Pinning the JVM to UTC would mask the
  day-bucketing defects that three tests exist to catch.
- **The detector's fast tier is 418 here and 414 in CI, and neither number is a regression.** The
  root `.venv` has both extras, so `pytest -m "not requires_ultralytics"` selects 418 and passes
  418, in about two seconds. CI installs no CV stack at all and passes 414, in half of one. The
  gap is four tests and two unrelated mechanisms. Two are harness guards — in `test_main.py` and
  `test_publisher.py` — that assert torch, cv2, ultralytics and kafka *are* importable, which is
  what stops the import-blocking proofs elsewhere passing vacuously; they are plain asserts, so a
  CV-free job does not deselect them by itself and they would fail rather than skip.
  `.github/workflows/ci.yml` names both in explicit `--deselect` flags. The other two are in
  `test_geometry.py`, `importorskip("numpy")`, and skip themselves.
- **`tests/test_architecture.py` is load-bearing.** It parses each module's AST and fails if
  `cv2`, `ultralytics`, `kafka`, `torch` or `numpy` appears anywhere outside `adapters.py`,
  `annotate.py` and `publisher.py`. `__main__.py` is **not** exempt, and the check walks function
  bodies too, so a lazy import does not escape it. That boundary is why the unit suite runs in half
  a second on a machine with no CV stack; the two seconds it takes here are collection importing
  torch through the integration tier's `conftest.py`, not the tests themselves.
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

1. **Rotate `JWT_SECRET` and `PASSWORD_RESET_AES_KEY` — done, and this entry says less than it
   used to on purpose.** It claimed both old values were in git history. Only one was. The AES
   literal is in three blobs (`fdbaece`, `87e2869`, `a88e320`; `4363391` removed it), and it stays
   there deliberately — it is dead, nothing ever deployed with it, and a rewrite was judged not
   worth breaking every SHA for. The JWT secret was **never** a value here: all five historical
   `JwtService.java` blobs hold `SECRET_KEY = "${JWT_SECRET}"`, an unresolved placeholder, and a
   scan of all 663 blobs in the object database finds no 64-hex string at all. Both values now in
   `.env` appear in zero commits. Generate a pair with `scripts/init-env.sh`.
2. **Revoke the Gmail app password** at Google. This is the only item still gating public release.
   Removed from history; that does not un-leak it. The account is `coderunners24@gmail.com`, and
   the exposure is narrow — this repository and its predecessor are both private with 0 forks — but
   narrow is not zero, and every clone and CI cache taken while it was pushed still has it.
3. **AGPL consent from Emre Yılmaz and Nil Emekci — obtained.** Both consented in writing in
   August 2026, and `NOTICE` states that and when. It is recorded here rather than deleted because
   it was the item everything else deferred to; 1 and 2 are what gate public release now.

`~/oss-release/` holds the pre-rewrite backups and the model weights. **`best.pt` is not
reproducible** — the training dataset is not in the repository. Do not delete that directory.

Both weights are now also published as assets of the [`weights-v1`](https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1)
pre-release, with their SHA256 in the notes, so `best.pt` is no longer a single local copy. That
release deliberately does **not** use the `v1.0.0` tag: it carries assets, not a version of this
code, and `v1.0.0` stays unclaimed until the repository goes public. Being a pre-release, it is
never GitHub's "Latest", so `v1.0.0` can take that place when it is cut.
