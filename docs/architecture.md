# Architecture

Three modules, three runtimes, two contracts. Everything else is internal to one module.

```
  ┌──────────────────────────────┐   Kafka   ┌────────────────────────────┐   REST   ┌───────────┐
  │ detector                     │  topic    │ engine                     │  + JWT   │ web       │
  │ Python 3.11+, YOLOv8         │ rawEvents │ Java 17, Spring Boot 3.5.16│          │ React     │
  │                              │ ────────► │                            │ ───────► │           │
  │ camera / file → rules        │  JSON     │ listener → MongoDB "event" │  JSON    │ charts    │
  │            └→ output_image.jpg│           │        → aggregation       │          │ grid, PDF │
  └───────────────┬──────────────┘           └────────────┬───────────────┘          └─────┬─────┘
                  │                                       │                                │
                  └──── same file on disk ────────────────┴─ GET /event/get_image/{ts} ────┘
                        (event.image.path)                   (public, unauthenticated)
```

**Contract 1** is the JSON on the Kafka topic `rawEvents`. **Contract 2** is the engine's REST API.
Neither is versioned or schema-validated; both are pinned by tests on the side that can see both
halves.

---

## The event pipeline, one frame at a time

`detector/src/worksite_detector/pipeline.py` is the frame loop, and its defining property is that
**there is no early exit**. Every frame runs the same stages in the same order, whatever the models
did or did not find.

```
read frame  ──►  pose model      ──►  gesture rules   ──┐
   │             (yolov8s-pose)       (per person)      │
   │                                                    ├──►  publish: FALL, then gestures,
   └────────────►  object model   ──►  collapse boxes ──┤     then closed PPE windows
                   (best.pt)          fall / PPE        │
                                            │           │
                                      PPE windows ──────┘
                                      (per event type)
                                                        └──►  write annotated frame
```

Each stage, and why it is shaped that way:

**Frame.** `adapters.OpenCvFrameSource` wraps one `cv2.VideoCapture` and decides what time a frame
happened: a video file is stamped from `CAP_PROP_POS_MSEC` (media position, from 0), a camera from
the injected clock. Everything downstream stamps events from the frame, never from a clock reading,
so replaying a file twice produces byte-identical event times. The consequence, stated in
`adapters.py`: a file-sourced run publishes times measured from the start of the clip, so a replay's
`startTime` lands in 1970 on the dashboard. Every duration, throttle and window is a *difference* of
two such stamps and is correct either way.

**Pose.** One `PoseDetection` per frame: 17 `(x, y)` keypoints per person in COCO order, 17
visibility scores, and the person *box* confidence. Empty on a frame with nobody in it — 278 of the
baseline clip's 986 frames.

**Gesture rules** (`pose_rules.py`). A gesture is a hysteresis band on one joint angle: it *arms*
when the angle falls below `maintaining` and *completes* when it rises back above `relaxing`. The
event fires on the completion edge and is stamped with that frame's time. Firing on entry would count
one slow movement once per frame it was held, making the dashboard a function of frame rate. Each
side of the body is gated on its own keypoint confidences and measured on its own; the mean is taken
over the sides that survived. State is one bit per gesture per person, keyed by a person id supplied
by the caller.

**PPE windows** (`ppe_rules.PpeViolationTracker`). A window opens on the first frame reporting a
violating type, absorbs later frames reporting the same type, and closes once that type has been
absent for `ppe_grace_ms`. Closing is what emits the event — while a window is open nothing is
published, because nothing is yet known about its duration. Windows are per event type and entirely
independent. `time_period_ms` is the last violating frame minus the first: what was *observed*, never
including the grace that closed the window and never running to the wall clock.

**Fall throttle** (`ppe_rules.FallThrottle`). One `FALL` per `fall_cooldown_ms` (default 180 000 ms).
A single fall is detected on many consecutive frames — 19 over ten seconds on the baseline clip — and
every `FALL` that reaches the engine emails every user in the database. Several `fall` boxes on one
frame collapse to the strongest, and the throttle is consulted once per frame rather than once per
box: a fall is an event about a frame, not about a rectangle.

**Publish order is FALL, then gestures, then window closures.** `KafkaEventPublisher.publish` flushes
after every send, so publish order is durability order: whatever has already gone is what survives the
process being killed mid-frame. Processing reads people before boxes and would put gestures first,
but that order is an artifact of how a frame is read, whereas urgency is a requirement.

**Sink.** `adapters.AnnotatingSink` encodes the annotated frame to a temporary file and renames it
over `output_image.jpg`. The write is last, so "a failed frame writes nothing" holds without a second
decision.

A frame whose stage raises is abandoned whole, costs one `ERROR` record, and the loop survives it. A
failing frame *source* is fatal — there are no more frames to read — and propagates through a
`finally` that flushes open windows and closes the source, the sink and the publisher exactly once.

---

## Contract 1: the `rawEvents` payload

`detector/src/worksite_detector/events.py` builds it; `engine/.../rawEvent/model/RawEvent.java` binds
it. Six keys, always all six:

```json
{
  "cameraName": "0",
  "confidencePercentage": 0.7386404275894165,
  "eventType": "FALL",
  "isProcessed": "false",
  "timePeriod": null,
  "startTime": 1730000000000
}
```

| key | type | notes |
|---|---|---|
| `cameraName` | string | published verbatim; how the dashboard attributes a violation to a site |
| `confidencePercentage` | number | a **fraction in [0, 1]**, despite the name. The dashboard multiplies by 100 |
| `eventType` | string | one of the five `EventNameEnum` names |
| `isProcessed` | string | the **string** `"false"`, not a boolean — the Java field is `String` |
| `timePeriod` | number or null | **milliseconds**, or null for a countable event |
| `startTime` | number | epoch milliseconds (media milliseconds for a file source) |

`RawEvent` is annotated `@JsonIgnoreProperties(ignoreUnknown = true)` and has no required fields, so
a payload with a misspelled, extra or missing key is accepted in silence: the value arrives as
`null`, becomes an empty column in MongoDB and a gap in a chart, with no exception and no log line on
either side. **The producer is the only enforcement point in the pipeline.** That is why
`DetectionEvent` validates on construction and why `detector/tests/test_events.py` asserts the key
set against `RawEvent.java` itself rather than against a transcribed copy.

The topic name is half of a contract whose other half is
`@KafkaListener(topics = "${kafka.raw-event.topic}")`. Changing it on one side only publishes into the
void, with no error anywhere.

---

## Ingest: the only place events are stored

`RawEventService.listener` is the single consumer of `rawEvents` and the only writer of the MongoDB
`event` collection. Its rules, in order:

1. **No `eventType`** → dropped with a `WARN`. `RawEvent` has no required fields, so a payload
   omitting it deserialises cleanly and every branch below would `NullPointerException`; thrown, that
   reaches the container's error handler, which re-invokes for the same record ten times before
   giving up.
2. **`eventType` not in `EventNameEnum`** → dropped with a `WARN`. Every read path filters by the
   five known names, so an unrecognised type would be stored and then unreachable by construction.
3. **`FALL`** → an alert email to **every** user in the database, each send isolated in its own
   `try`, then stored. The isolation matters: before it, the first unreachable mailbox ended the loop
   *and* aborted the listener before the save, so an SMTP hiccup deleted the record of a person
   falling over.
4. **`NO_HELMET` / `NO_JACKET`** → the duration is normalised to milliseconds by
   `event.periodic.input-unit`, and stored **only if** it exceeds `event.periodic.min-duration-ms`
   (default 3000). The stored document is stamped `schemaVersion = 2`, which is how the one-shot
   migration knows not to convert it twice.
5. **Everything else** — `FALL` (again, for the save), `ARMS_UP`, `FRONT_BEND` — stored with
   `timePeriod` forced to `null`. A countable event has no duration to normalise, so any number there
   is a measurement nobody took; one that arrives carrying a duration is logged and stored anyway,
   because dropping a `FALL` over a spurious field would recreate the data loss rule 3 exists to
   prevent.

A record that cannot be deserialised at all fails inside `poll()`, before a `ConsumerRecord` exists.
An `ErrorHandlingDeserializer` moves that failure somewhere a handler can see it; the record is logged
once with its partition and offset, and skipped. No retries.

### The unit flag

`event.periodic.input-unit` declares what the *producer* sends — `SECONDS` for the implementation
that was in the field before this release, `MILLIS` for the rewritten detector — and ingest normalises
to milliseconds. It exists because the two repositories deploy independently: a millisecond producer
read as seconds stores 33 ms flickers as violations, and a seconds producer read as milliseconds
stores nothing at all. Both are silent. It ships as `SECONDS` and **must be flipped to `MILLIS` when
the rewritten detector is deployed.**

---

## Event taxonomy

Two families, treated differently end to end. `EventType.is_periodic` in the detector and the
`NO_HELMET || NO_JACKET` branch in the listener are the same split.

| | countable | periodic |
|---|---|---|
| types | `FALL`, `ARMS_UP`, `FRONT_BEND` | `NO_HELMET`, `NO_JACKET` |
| carries a duration | no (`timePeriod` is null) | yes, in milliseconds |
| emitted | as it occurs | once, when the violation window closes |
| aggregated as | count per day | summed duration per day |
| endpoints | `/event/countable-events`, `/event/pie-chart-events` | `/event/periodic-events` |

Adding a sixth type means touching all three modules — see
[development.md](development.md#adding-a-new-event-type).

---

## Contract 2: the REST API

Base URL `http://localhost:8080` by default. Swagger UI at `/docs/swagger-ui.html`, OpenAPI JSON at
`/docs`. **All date-range parameters are epoch milliseconds, as path variables.**

| method | path | auth | returns |
|---|---|---|---|
| `POST` | `/auth/register` | public | `{id, name, lastName, token, role, email}` |
| `POST` | `/auth/login` | public | the same |
| `POST` | `/auth/forgot-password` | public | sends a reset mail |
| `POST` | `/auth/change-password` | public | consumes the reset token |
| `PUT` | `/auth/update-user/{userId}` | ADMIN | the same auth response |
| `POST` | `/auth/logout` | logout filter | marks the presented token expired and revoked |
| `GET` | `/event/countable-events/{startDate}/{endDate}` | ADMIN | `[{date, fall, armsUp, frontBending}]` |
| `GET` | `/event/periodic-events/{startDate}/{endDate}` | ADMIN | `[{date, noHelmet, noJacket}]`, **seconds** |
| `GET` | `/event/pie-chart-events/{startDate}/{endDate}` | ADMIN | `[{name, value}]` |
| `GET` | `/event/all-events` | ADMIN | `[{id, cameraName, confidencePercentage, eventType, startTime, endTime, timePeriod}]`, `timePeriod` in **seconds** |
| `DELETE` | `/event/delete-events/{eventId}` | ADMIN | — |
| `POST` | `/event/sendPdfEmail/{startDate}/{endDate}/{emailReceiver}` | ADMIN | builds the report and mails it |
| `GET` | `/event/get_image/{timestamp}` | **public** | the current annotated frame as `image/jpeg` |

`date` is `dd.MM.yyyy`. The `{timestamp}` on `get_image` is a cache-buster and is otherwise ignored.

### Units on the wire

Durations are **stored in milliseconds** and **returned in seconds**, truncated per event, at every
boundary that returns one: the periodic chart, the events grid and the PDF report all go through the
same conversion, so they cannot disagree about the same event. The dashboard needs no conversion and
its charts do not become a thousand times taller.

`confidencePercentage` travels as a fraction and is multiplied by 100 for display.

### Which day an event belongs to

One property, `app.timezone` (an IANA zone id, default `UTC`), read once by `EventService`'s
constructor and by `RawEventService` for the fall alert's "Detection Time". It answers "which day"
for every surface that answers it: the countable chart, the periodic chart and the PDF report. Those
three used to disagree — two read the JVM default zone and one divided the epoch by 86 400 000 — so
on any host not set to UTC, one event near midnight was counted on different days by charts shown
side by side.

---

## Auth

Stateless JWT, HS256, 20 minutes (`jwt.expiration-ms`), signed with `jwt.secret`. There is no refresh
flow.

```
  browser                         engine
     │  POST /auth/login            │
     │ ───────────────────────────► │  authenticate, sign a token, store it
     │  ◄─────────────────────────  │  {token, role, ...}
     │                              │
   localStorage["user"]             │
     │                              │
     │  Authorization: Bearer <t>   │  JwtAuthenticationFilter:
     │ ───────────────────────────► │    extract subject → load user
     │                              │    token not expired && not revoked (checked in Mongo)
     │  403 ──────────────────────► │  → SecurityContext, else no authentication
     │  (frontend clears storage    │
     │   and redirects to /landing) │
```

`User` implements `UserDetails` directly, with the email as the username. `SecurityConfiguration`
holds two hardcoded arrays, `PUBLIC_URLS` and `ADMIN_URLS`; anything in neither falls through to
`.anyRequest().authenticated()`. `Role` has exactly one value, `ADMIN`, so `ADMIN_URLS` in practice
means "any logged-in user".

Issued tokens are stored, so `POST /auth/logout` can mark one expired and revoked and the filter
rejects it from then on. Nothing revokes a user's *other* tokens.

CORS is one bean driven by `app.cors.allowed-origins`, exact-match origins only, credentials off (the
API uses a bearer token set by JavaScript, never a cookie). A wildcard is refused at startup.

---

## The video "stream"

There is no stream. The detector overwrites one `output_image.jpg`; the engine serves that single
file from the directory named by `event.image.path`; the browser polls the URL through a queue
buffer. The endpoint is in `PUBLIC_URLS`, so it needs no token.

Two consequences worth knowing before deploying: the preview shows the current frame of whichever
detector process last wrote that file, so **the design is single-camera**; and anyone who can reach
the API can fetch the worksite frame.

`event.image.path` defaults to `../detector/`, because the documented way to start the engine is
`./mvnw spring-boot:run` from `engine/`, which makes `detector/` its sibling. Starting it from the
repository root needs `EVENT_IMAGE_PATH` set explicitly.

---

## What breaks if one side changes alone

| change | other side that must change | symptom if it does not |
|---|---|---|
| Kafka topic name | `kafka.raw-event.topic` | events publish into the void; no error either side |
| a JSON key in the payload | `RawEvent.java` | field arrives null, empty column, gap in a chart, nothing logged |
| the unit of `timePeriod` | `event.periodic.input-unit` | flickers stored as violations, or nothing stored at all |
| a new `EventType` | `EventNameEnum` + the type lists in `EventService` + the chart keys in `web/` | dropped at ingest with a `WARN` |
| `event.image.path` | where the detector writes `output_image.jpg` | 404 from a public endpoint, nothing in a log |
| a new endpoint | `PUBLIC_URLS` / `ADMIN_URLS` | falls through to `.anyRequest().authenticated()` |
