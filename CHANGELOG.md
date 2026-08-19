# Changelog

Notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com);
versions follow [Semantic Versioning](https://semver.org).

Every number below is reproducible from this repository: the per-frame measurements come from
`detector/tests/data/baseline/`, and every fix named is pinned by a test.

## [1.0.2] — 2026-08-19

Documentation only. No source file and no test changed. This release exists because three documents
were describing a state the repository had left: this file still called the first release untagged,
`CLAUDE.md` still called the repository private, and nothing anywhere named the DOI the archive had
just been given.

### Added

- **[CITATION.cff](CITATION.cff)**, valid against CFF schema 1.2.0, and a citation section in
  [README.md](README.md) carrying the DOI badge. The file drives GitHub's "Cite this repository"
  button and is what Zenodo reads when depositing a release — but only while no `.zenodo.json`
  exists, which would override it entirely. This is the first release deposited with it; every
  earlier deposit took its metadata from GitHub's own author derivation.
- **A "Releases and the DOI" section in `CLAUDE.md`**, saying which of the two DOIs means what, so
  the next person does not paste the wrong one into a badge.

### Fixed

- **This file described the first release as untagged**, thirteen days after it shipped. The
  `[Unreleased]` heading became `[1.0.0] — 2026-08-06` and nothing beneath it changed, exactly as
  the paragraph under that heading had promised.
- **`CLAUDE.md` said the repository was still private**, and said that `v1.0.0` "can take that
  place" of GitHub's "Latest" when it is cut — by the time anyone read it, `v1.0.1` held it.
- **The Zenodo record for `v1.0.1` credited its authors wrongly.** Zenodo had put each
  contributor's whole display name into the family-name field, and had rendered one of the three as
  `NilEmekci`, so a citation would have filed them under a name none of them has. Corrected by hand
  on the record on 19 Aug 2026, along with the auto-generated title; the DOI did not change. The
  fix is on Zenodo rather than here because `CITATION.cff` governs future deposits only.

---

## [1.0.1] — 2026-08-19

**No code changed.** `v1.0.1` tags the same commit as `v1.0.0` — `974b52f` — and
`git diff v1.0.0 v1.0.1` prints nothing. The tag exists because Zenodo only archives releases
published after its GitHub integration is switched on, and `v1.0.0` was published thirteen days
before it was. A second tag over an unchanged tree was cheaper than rewriting the first release.

It is a patch number that buys an archive rather than fixes a defect, which is a deviation from the
Semantic Versioning promise three lines above. It is recorded here rather than skipped quietly
because anyone who diffs the two tags will find them identical and wonder what was hidden.

### Added

- **A DOI.** [10.5281/zenodo.22009804](https://doi.org/10.5281/zenodo.22009804) is the concept DOI
  and always resolves to the newest archived version;
  [10.5281/zenodo.22009805](https://doi.org/10.5281/zenodo.22009805) is this release alone. The DOI
  Zenodo displays beside the repository on its own GitHub settings page is the version one, so
  copying what it offers into a README freezes the badge at whatever release was current that day.

---

## [1.0.0] — 2026-08-06

Everything below is the first open-source release. It was tagged
[`v1.0.0`](https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/v1.0.0) on
6 August 2026, at the commit `main` carried when this section was written; the heading took its
number and its date and nothing beneath it changed, exactly as the pre-release version of this
paragraph said it would. The other tag in this repository is
[`weights-v1`](https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1),
a pre-release that carries the two model weight files as assets — it versions those files, not this
code, which is why it is not `v1.0.0` and why retraining can yield `weights-v2` without implying a
release of the code.

The starting point was a university graduation project: a working demo of three modules that talked
to each other, and a 546-line `aiModule.py` that could not be imported without a live Kafka broker,
let alone tested. Everything below is the distance between that and something publishable. That file
is not in the tree: it was kept at the tip through the rewrite as the artifact being measured
against, then removed before publication, because nothing executed it and it does not import on
ultralytics 8.1 or later. It stays in history untouched, and the line numbers that cite it
throughout `detector/` still resolve — `git show 621cfb0:detector/aiModule.py`, or see
[docs/development.md](docs/development.md#aimodulepy-and-the-line-numbers-that-cite-it).

### Added

- **`worksite_detector`**, the detector rewritten as a package with a hard boundary: only
  `adapters.py`, `annotate.py` and `KafkaEventPublisher.connect` may import `cv2`, `ultralytics`,
  `kafka`, `torch` or `numpy`, enforced by an AST test. The consequence is a unit suite that does not
  need a CV stack to run: 418 passed and 63 deselected in 1.64 s on a machine that has one, and 414
  in CI on a machine that has none — the four-test gap is two `numpy` `importorskip`s plus two
  harness guards that assert the blocked libraries *are* installed, which is what stops the
  import-blocking proofs passing vacuously. The 63 deselected are the tier that genuinely needs
  ultralytics, behind a `requires_ultralytics` marker.
- **A real entry point.** `python -m worksite_detector`, or the `worksite-detector` console script.
  The original defined `parse_args()` and never called it, so nothing was configurable without
  editing Python — and its `--sport` default named a gesture that did not exist in its own table.
- **`--dry-run`**, which runs the whole pipeline against no broker, needs no Kafka client library,
  and prints a summary of what it would have published. This is the quick start in the README,
  because it is the only path that works before anything else is deployed.
- **One validated configuration schema.** Defaults, then a YAML file, then `WSM_<SECTION>__<FIELD>`
  environment variables, then the command line — each layer overriding the last and only where it
  speaks. An unknown key is fatal and the error names it, in the file and the environment alike:
  `WSM_KAFKA__BOOTSTRAP_SERVER`, singular, otherwise leaves a rig publishing to `localhost` for
  weeks with an empty dashboard and nothing logged. `config.example.yaml` is asserted to parse back
  equal to the built-in defaults, so it cannot drift into fiction.
- **Signal handling and a shutdown path.** `SIGINT`/`SIGTERM` finish the current frame and then
  flush the PPE windows still open. The original documented `q` to quit, against a window whose
  `imshow` call was commented out, so the only exit was killing the process — which skipped the
  capture release, the flush and `producer.close()`, all of which sat after the loop.
- **A recorded baseline and a measured differential.** 986 frames of real worksite footage captured
  as model *outputs* (457 KB gzipped, no pixels), the original's logic transcribed as an oracle, and
  both driven over the same records. `detector/tests/data/baseline/PROVENANCE.md` and
  `DIFFERENTIAL.md` state what that evidence can and cannot prove.
- **Container-backed integration tests for the engine**, split from the unit suite: Surefire (`*Test`,
  no Docker) and Failsafe (`*IT`, Testcontainers), with JaCoCo split and merged so integration
  coverage stops being invisible.
- **A Dockerfile per module and a `docker-compose.yml`** that brings Kafka, MongoDB, the engine, the
  web app and the detector up together. The detector service is fed a video file mounted read-only
  rather than a camera device, because a device passthrough is Linux-only and turns "clone and run"
  into "find a camera first". The engine's `EVENT_IMAGE_PATH` and the detector's
  `WSM_OUTPUT__ANNOTATED_FRAME_PATH` are set to two halves of one shared volume rather than left to
  whichever directory a process started in.
- **CI and repository furniture**: a GitHub Actions workflow with a job per module — the engine
  through `./mvnw verify` with a Docker daemon for the integration tier, the detector's fast tier on
  a runner where the CV stack is asserted *absent*, and the web app through `npm ci`, `npm test` and
  `npm run build` — plus Dependabot for all four ecosystems, issue templates and a pull-request
  template.
- **Training artifacts**: hyperparameters, per-epoch metrics and the performance charts for the run
  that produced `best.pt`, under `detector/training/` and `docs/images/`.
- **This documentation**: `README.md`, `LICENSE` (AGPL-3.0-or-later), `NOTICE`, `SECURITY.md`,
  `CONTRIBUTING.md`, `docs/architecture.md`, `docs/development.md` and `.env.example` files.

### Fixed — detector

- **`NO_JACKET` was never published, on any input.** `controlJacket` was set `False` at line 409 and
  `False` again at line 428 where `True` was meant, so the emit at 489 was unreachable. The baseline
  clip carries `no-jacket` detections on 63 frames and the original produced zero events; the rewrite
  produces four windows, the longest 6500 ms.
- **PPE violations are windows now, closed on a grace timer.** Detections flicker: those 63 frames
  arrive as 27 runs, the longest 367 ms, and closing on the first clean frame yields 63 windows of
  which *none* clears the engine's 3-second threshold. Fixing the never-published bug alone would
  still have recorded nothing. At the chosen 1500 ms grace the same footage becomes one coherent
  6500 ms violation.
- **A frame with no detected person skipped everything after it** — the PPE boxes, the fall branch,
  the violation flags and the preview write. A person lying on the ground is exactly what a pose
  model is worst at, so that early exit was aimed at the event the system exists to catch: of the two
  falls in the baseline clip, the earlier one was on such a frame and was never published. Every
  frame now takes the same path, and 986 of 986 frames reach the end of the pipeline where 708 did.
  The same incident is now reported 8.3 seconds sooner.
- **Neither gesture could ever fire.** The hysteresis latch armed once per slot and never re-armed,
  so every slot went silent for the life of the process — over 986 frames, zero `ARMS_UP` and zero
  `FRONT_BEND`, with the visibility gates passing 811 and 964 times. The latch re-arms now.
- **Gesture state had no owner.** It was four fixed 10-element arrays indexed by a person's position
  in one frame's model output, with no tracker, so slot 0's history routinely belonged to a different
  human on the next frame — and the eleventh person in shot was an `IndexError` that ended the run.
  State is now a dict keyed by an externally supplied person id.
- **A person seen side-on had the unseen side folded into the measurement.** The gates were
  `left AND ... or right AND ...` and the angle helper then averaged both sides unconditionally;
  `atan2(0, 0)` is `0.0` rather than an error, so the reported angle was roughly halved before every
  threshold. Each side is now gated and measured on its own, and degenerate input raises.
- **The upright precondition measured a limb nobody checked.** The gate covered shoulder-hip-knee
  while the angle was taken over hip-knee-**ankle**; ankle confidence was read nowhere in the file.
  A gesture may no longer declare that it needs a posture check without also gating the keypoints
  that check reads.
- **Published confidence was a keypoint visibility score**, not the detection box's — a different
  number about a different thing, shown to a safety officer as the detector's confidence.
- **Periodic confidence was a session-long running mean.** The sums were never reset, so every event
  after the first reported the average of everything seen since startup.
- **`timePeriod` was `int(seconds)` beside a millisecond `startTime`.** Applied to the four windows
  above that formula gives `[0, 0, 0, 6]`. Both fields are milliseconds now.
- **The preview frame was written in place**, so the browser polling it every 100 ms read half a
  JPEG: reproduced against a polling reader, 108 of 130 reads came back empty or undecodable. It is
  encoded to a temporary file and renamed into place now; none did over 60 writes.
- **The overlay discarded keypoints on the frame edge.** A modulo was used to ask "is this the
  missing-keypoint marker?", which is a different question: a joint genuinely found at the top of the
  frame was dropped, while a negative coordinate was drawn as a point and refused as a limb.
- **A broker outage stopped detection.** None of the five publish sites was wrapped, so a hiccup
  raised out of the frame loop and the camera stopped — losing not just the buffered events but every
  event that would have been observed afterwards. A failed publish now costs one WARNING and a
  counter reported at shutdown.
- **The Kafka partition key was `str(time.time())`**, a fresh value on every call, so two identical
  events landed on different partitions under a key nobody could reproduce.

### Fixed — engine

- **Authentication was completely broken, and failed as a 500.** The signing key was the literal
  placeholder left by the history rewrite, and `JwtAuthenticationFilter` decoded it *before* reading
  the token, so the failure escaped the servlet filter chain — outside `DispatcherServlet`, where the
  exception handler can never see it. Any request carrying an `Authorization` header returned a bare
  500, public endpoints included.
- **The test suite ran one test.** Two of three test classes were named `*TestImpl`, which matches no
  Surefire default include, so they were silently skipped, and the build then failed on the third.
- **Date ranges silently dropped their boundaries.** Spring Data maps `Between` to `$gt`/`$lt` —
  exclusive at both ends, unlike JPA — and one repository method funnels the countable chart, the pie
  chart, the periodic chart, the events grid and the PDF report.
- **The PDF report was emailed as zero bytes** with a `200` and "Email sent successfully!". iText
  buffers until `close()`, which the error path never reached. Generation failure, an empty report and
  a delivery failure are three distinct answers now.
- **One failed fall-alert email destroyed the record of the fall.** The send loop had no
  per-recipient isolation and the save came after it, so a transient SMTP outage skipped every
  remaining recipient *and* aborted the listener before the event was stored.
- **A single malformed Kafka message wedged the consumer.** Deserialization fails inside `poll()`,
  before any record exists, so the error handler never saw it and the container could not advance —
  it spun. The build log for the reproducing test was 1.26 GB.
- **Every `spring.kafka.consumer.*` and `spring.kafka.listener.*` property was ignored.**
  `KafkaConsumerConfig` declared `kafkaListenerContainerFactory` under the bean name Spring Boot's
  own auto-configuration uses, so Boot backed off — and then the class applied neither
  `KafkaProperties` nor `ConcurrentKafkaListenerContainerFactoryConfigurer`. Every such key in every
  environment was readable, plausible and connected to nothing. Both are applied now, and three
  settings stay in code deliberately, each with a test: `auto.offset.reset` defaults to `earliest`
  through `putIfAbsent`, so it is a default configuration can override rather than a second
  hardcoding; the no-retry error handler is set *after* the configurer, so it wins over any
  `CommonErrorHandler` bean the configurer would otherwise apply; and the two `*-deserializer`
  properties are refused at startup instead of silently ignored, because the deserialisers are
  constructed instances and `KafkaConsumer` never calls `configure()` on one.
  The `spring.kafka.listener.auto-startup: false` that sat in the test configuration was inert for a
  different reason and still would be: Boot 3.0.4's `KafkaProperties.Listener` has no such field at
  all — it arrives in 3.2. It is deleted rather than kept as documentation of a wrong diagnosis.
- **Unrecognised `eventType`s were written to a collection no query can read.** Every read path
  filters by the five known names, so those documents were unreachable by construction. They are
  dropped with one WARNING naming the type.
- **"Which day did this happen on" had four different answers.** Two chart methods read the JVM
  default zone, one divided the epoch by 86 400 000 (hard-wired UTC), and the fall-alert email used a
  zoneless `LocalDateTime.now()`. On any host not set to UTC, one event near midnight was counted on
  different days by charts shown side by side. All four read `app.timezone` now.
- **Durations are stored in milliseconds.** `event.periodic.input-unit` declares what the producer
  sends so the two repositories can deploy independently, and an opt-in one-shot
  `PeriodicTimePeriodMigration` rewrites existing documents and stamps `schemaVersion`.
  `BigDecimal.intValue()` was also replaced with `longValue()` on both the write and the read path: it
  returns the low-order 32 bits without throwing, so a window over ~24.8 days wrapped negative and
  the longest, most serious violations were the ones discarded.
- **Password-reset links were dead or corrupted.** The link was hardcoded to
  `http://localhost:3000/change-password`, so every reset mail a deployed instance sent pointed the
  recipient at their own machine; and the token is standard-alphabet Base64 interpolated into a query
  string, where the `+` present in 49% of tokens arrives as a space.
- **`decrypt("")` returned `""`** instead of refusing.
- **Deleting an event reported "User Not Found".**
- **`GET /event/all-events` returned the MongoDB entity**, so durations reached the dashboard in
  milliseconds while the chart beside them converted to seconds — the API contradicted itself.

### Security

- **Two credentials were committed, not three, and one of them is still in the history.** All three
  secrets are environment variables with no committed fallback now, so a deployment that forgets one
  refuses to start; but "externalised" and "not leaked" are different claims and an earlier draft of
  this entry ran them together. Separately, then:

  **A Gmail app password** sat in `spring.mail.password`. It is out of the working tree and out of
  the history, and it **must still be revoked at Google** — deleting a credential from a file has
  never un-issued it.

  **The password-reset AES key** was a 16-character literal in `PasswordService.java`, and it is
  **still in this repository's history**. Three blobs hold it: the file as introduced in `fdbaece`
  and as reformatted in `87e2869`, plus `PasswordServiceTest.java`, which quoted it in `a88e320`.
  `4363391` removed it from both. All four commits are reachable from `main`. History was
  deliberately *not* rewritten to purge it, because a rewrite changes every commit id beneath it and
  still cannot reach a clone that already exists — it buys the appearance of cleanliness and none of
  the substance. What closes the exposure is that the key is dead: it has been rotated, no deployment
  ever ran on it, and the value in use today appears in zero commits.

  **The JWT signing key was never committed at all.** All five historical `JwtService.java` blobs
  read `private static final String SECRET_KEY = "${JWT_SECRET}"` — an unresolved Spring placeholder,
  never a value — and no run of 64 hexadecimal characters exists in any of the 663 blobs in the
  object database. It was rotated anyway. This entry used to say it leaked; it did not.

  See [SECURITY.md](SECURITY.md), which carries the same facts with the reasoning behind each.
- **`MailController` accepted an unauthenticated `POST` with the recipient in the path** — an open
  relay. The class is deleted, its `permitAll` entry with it, and a test asserts it is gone from the
  classpath, because securing a URL and deleting its handler look identical from outside.
- **CORS meant "any origin".** `@CrossOrigin` with no attributes sat on both controllers, including
  the unauthenticated camera-frame endpoint. It is one property-driven bean now, and
  `SecurityConfiguration` refuses `*` at startup.
- The JWT secret, its expiry and the AES key are constructor arguments validated once at startup.
  They had been `private static final String`s, which javac inlines at every use site — neither
  `@Value` nor reflection could reach them.

### Changed

- **The dashboard moved from Create React App to Vite**, with Vitest for tests — the module had no
  test file of any kind before this release. The dev server port is pinned to 3000
  (`strictPort: true`) rather than left to Vite's 5173 default, because the engine's CORS list and
  the host in every password-reset link both default to `http://localhost:3000` and would otherwise
  reject it. Redux Toolkit 1.9 → 2.x (the `user` slice's `extraReducers` object-map form, removed in
  2.x, is now the builder form), react-redux 8 → 9, react-router-dom 6 → 7.
- **The engine's URL is `VITE_API_URL`.** It was the literal `http://localhost:8080` in two files, so
  a build could only ever talk to a backend on the developer's own machine. The bearer token is
  attached by an axios request interceptor as well: every authenticated call used to spell out its
  own `Authorization` header, so each new call site could forget it.
- `AIModule/detect/` → `detector/`, `designer/` → `web/`. Pure renames; every file byte-identical.
- The `event.fall.threshold.value` property is now `event.periodic.min-duration-ms`. The old name
  named the wrong event family and carried no unit — `3` meant three seconds, which is how it
  survived the producer switching to milliseconds and started admitting 33 ms flickers.
- The Kafka topic and consumer group are properties (`kafka.raw-event.*`) rather than literals on the
  `@KafkaListener`.
- `event.image.path` defaults to a relative path resolved against the engine's working directory. It
  was an absolute path into a former developer's OneDrive folder, so the camera preview was broken on
  every machine but one — silently, as a 404 from a public endpoint.

### Removed

- Model weights, training runs and the detector's per-frame output image are no longer tracked. They
  are what made this repository 250 MB before the history rewrite.
- `EngineApplicationTests`, whose `@MockBean KafkaAdmin` existed only because there was no broker;
  `EngineApplicationIT` boots the real context against a real one.
- The on-frame repetition-counter banner and the mp4 writer from the original annotator. The counters
  live inside the gesture detector now, and the banner painted a filled bar across every frame.
- Dashboard dependencies that nothing imported, among them `cors` — a Node server package with no
  meaning in a browser bundle — `socket.io-client`, `@mui/joy`, `react-date-range`, `date-fns` and
  `web-vitals`.

### Known limitations at this release

Stated here because they are measured, not assumed. The full list is in the README.

- **`event.periodic.input-unit` ships as `MILLIS`**, matching the rewritten detector — in
  `engine/src/main/resources/application.yml` and in `docker-compose.yml` alike. An earlier draft of
  this entry said `SECONDS`, which described the producer that was in the field *before* this work
  and was already stale when it was written. The one place `SECONDS` survives is the annotation
  default in `RawEventService`, `${event.periodic.input-unit:SECONDS}`, which applies only if the
  property is absent from configuration entirely; it is the pre-migration reading, kept so that an
  old deployment picking up this code does not silently reinterpret its existing producer. If you
  have data written before this work, run the migration first and then confirm the flag — a
  millisecond producer read as seconds stores 33 ms flickers as violations, and a seconds producer
  read as milliseconds stores nothing. Both are silent.
- **Neither gesture has ever been demonstrated on real video.** The baseline clip contains no
  completed arm raise and no bend, so both rules remain covered by synthetic tests only.
- **`NO_HELMET` has no real-footage evidence either** — the clip contains zero `no-helmet`
  detections.
- **PPE violations are per frame, not per person**, and person ids do not survive a frame.
- `DIFFERENTIAL.md` records the engine's periodic threshold as still unchanged. That was true when it
  was written and is not true now; both documents in `detector/tests/data/baseline/` are frozen
  measurements, kept as they were taken, with their corrections pinned by tests rather than edited in.
