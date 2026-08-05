<!--
Keep this short. The checklist below is not ceremony: every item on it is a
mistake that has actually been made in this repository and cost real time to
find, because in almost every case nothing failed at the moment it was made.
-->

## What this changes

<!-- One or two sentences. What is different afterwards, and why. -->

## Why

<!--
The problem, not the diff. If it fixes something silent - an event that was
never stored, a chart that disagreed with the chart beside it, a mail with a
dead link - say how you knew, because the next person will need the same
method.
-->

## How it was verified

<!--
Commands and their outcome, not "tested locally".

  engine     cd engine && ./mvnw -B verify      (Failsafe needs a Docker daemon)
  detector   cd detector && pytest -m "not requires_ultralytics"
             cd detector && pytest -m requires_ultralytics   (needs the [cv] extra)
  web        cd web && npm test && npm run build
  the lot    docker compose up --build
-->

---

- [ ] **Modules touched are all touched.** Adding or changing an event type
      means the detector rule, `EventNameEnum` **and** the countable/periodic
      lists in `EventService`, **and** the `keysAndColors*` arrays in
      `ChartsContainer`. Missing one is silent: detected, stored, never shown.

- [ ] **No secret is added, and none is defaulted.** `JWT_SECRET`,
      `PASSWORD_RESET_AES_KEY`, `MAIL_USERNAME` and `MAIL_PASSWORD` have no
      fallbacks anywhere, deliberately - a `${VAR:-something}` added to any of
      them turns "refuses to boot" into "boots with a key anyone can forge".
      The gitleaks job in CI would not catch it; see the comment on that job for
      why not.

- [ ] **Units are stated where they cross a boundary.** `timePeriod` is
      milliseconds in storage and `event.periodic.input-unit` says what the
      producer sends. Getting it wrong in either direction is silent: millis
      read as seconds stores 33 ms flickers as violations, seconds read as
      millis stores nothing at all.

- [ ] **New endpoints are in `SecurityConfiguration`.** Anything not listed in
      `PUBLIC_URLS` or `ADMIN_URLS` falls through to
      `.anyRequest().authenticated()`. That default is safe; the unsafe mistake
      is adding something to `PUBLIC_URLS` that did not need to be there.

- [ ] **Tests are named so they run.** Surefire picks up `*Test`/`*Tests`;
      Failsafe owns `*IT` and needs Docker. A test class named anything else is
      a test that never runs and always passes.

- [ ] **`docker compose up` still works**, if this touched configuration, a
      property name, a port, or either half of the `EVENT_IMAGE_PATH` /
      `WSM_OUTPUT__ANNOTATED_FRAME_PATH` pair that makes the preview work.
