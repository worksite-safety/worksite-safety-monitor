# Security policy

## Reporting a vulnerability

**Email the maintainer: azizcanguv@gmail.com.** That address is in `.mailmap` and on the commits, it
works today, and it is the channel that does not depend on any repository setting being in a
particular state.

GitHub's private vulnerability reporting is the other route:

<https://github.com/worksite-safety/worksite-safety-monitor/security/advisories/new>

It opens a draft advisory visible only to you and the maintainer, and it is the better of the two
when it is available — the report, the fix and the CVE all live in one place. GitHub only offers the
feature on public repositories, though, and refuses to enable it in advance. **If that link answers
404, this repository is not public yet**; that is the expected state until it is, and it is why the
email address is listed first rather than as a footnote.

**Please do not open a public issue for a security problem.** A public issue is a disclosure: it
reaches attackers at the same moment it reaches us, and before there is anything to upgrade to.

Useful things to include: what an attacker can do, the shortest sequence that demonstrates it, the
commit you tested, and whether you have already disclosed it anywhere.

What to expect: this is a small project with one maintainer, working on it in his own time. No
response time is promised. You will get an acknowledgement, a yes-or-no on whether it reproduces,
and credit in the advisory unless you would rather not have it.

## Supported versions

There are no releases of this code yet, so there is no version to support and nothing to tell you to
upgrade to. **`main` is the only thing that exists**, and a fix lands there.

The one tag in this repository is [`weights-v1`](https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1),
a pre-release carrying the two model weight files as assets. It versions those files, not this code:
nothing about it says which commit you are running. When a version of the code is cut, this section
will name it.

---

## Credentials that were committed to this repository

Two were, and a third that earlier drafts of this file listed was not. The distinction is the whole
point of the table, so it is stated rather than smoothed over:

| what | where it lived | still in history? | what was done |
|---|---|---|---|
| A Gmail **app password** | `spring.mail.password` in `engine/src/main/resources/application.yml` | no | **Revoke** it in the Google account that issued it |
| The **password-reset AES key** | a 16-character literal in `PasswordService.java` | **yes — deliberately** | Rotated. See below |
| The **JWT signing key** | never a value here — see below | no | Rotated anyway |

**The JWT signing key was never committed to this repository.** All five historical
`JwtService.java` blobs hold `private static final String SECRET_KEY = "${JWT_SECRET}"` — an
unresolved Spring placeholder, not a key. (It could never have resolved: javac inlines a
`static final String` at every use site, so neither `@Value` nor reflection reaches the field. That
is a separate defect, fixed by making the key a constructor argument, and it is why authentication
failed as a 500 rather than as a 401.) Scanning all 663 blobs in the object database for a run of 64
hexadecimal characters returns nothing. The key was rotated regardless, because that costs one
command, but no reader should go looking for a leak that is not there.

**The password-reset AES key is still in this repository's history, and history was not rewritten to
remove it.** Three blobs in the object database hold the literal: `PasswordService.java` as
introduced in `fdbaece` and as reformatted in `87e2869`, and `PasswordServiceTest.java`, which quoted
it in `a88e320`. `4363391` removed it from both files, so the working tree is clean. All four commits
are reachable from `main`, and `git log -S` will find them.

Leaving it there was a decision, not an oversight. A rewrite rewrites every commit id beneath it,
invalidates every link into the history that anyone has ever saved, and still cannot reach a clone
that already exists — it buys the appearance of cleanliness and none of the substance. What actually
closes the exposure is that **the key is dead**: it was rotated, no deployment ever ran on it, and
the value in the current `.env` appears in **zero** commits. A dead key sitting in an old commit is a
historical artifact. A live key removed from the tip is still a live key.

Relocating a credential to an environment variable changes where the value is read from. It does not
change whether the value is compromised — which is why the Gmail app password is the one item on
this list still needing an action outside this repository. **Revoke it at Google.** Deleting it from
a file has never un-issued it.

### How far it got

Narrower than a leak of this kind usually is, and worth stating so that nobody over- or under-reacts.
This repository is private and has 0 forks; publishing it is the pending action all of this work is
preparing for, so nothing in it has been world-readable. Its predecessor,
`GraduationProjectBuddies/GraduationDesignRepository`, is private, archived and also has 0 forks. The
exposure is therefore to everyone who has ever had read access to either — a small, known set — and
not to the internet.

That is a reason to revoke the Gmail password calmly rather than a reason not to revoke it. "Only
the people with access saw it" is an assumption about every clone, CI cache and editor backup those
people made, and it is not one this project is willing to bet an account on.

### Why the password-reset key was the one that mattered

`PasswordService.encrypt(email)` produces the token that becomes the `?token=` of a password-reset
link, and `decrypt(token)` yields the address whose password is then changed. The token carries **no
expiry**, is not bound to a request, and cannot be revoked.

So anyone holding that key can mint a valid password-reset link for **any** address, at any time,
without ever touching this system. It is not a configuration value; it is an account-takeover key —
which is why it is the one credential in the table whose exposure justified an action rather than a
note, and why it was rotated before anything else.

Rotation invalidates every reset link that has already been emailed. That is the correct outcome:
every one of those links was forgeable by anyone who could read the history.

Note what rotation does *not* fix, because it is a property of the design rather than of the key:
see "Password-reset tokens are AES/ECB over an email address" below.

### Rotating

Every credential the engine reads is an environment variable with **no committed fallback**, so a
deployment that forgets one refuses to start rather than running on a key someone else may know.
`ProductionConfigurationTest` reads the production YAML as raw text and pins that set at exactly
four: `MAIL_USERNAME`, `MAIL_PASSWORD`, `JWT_SECRET`, `PASSWORD_RESET_AES_KEY`. Adding a fallback for
any of them makes it fail.

To generate a fresh pair, run [`scripts/init-env.sh`](scripts/init-env.sh) from the repository root:
it writes a `.env` with both keys generated locally, and refuses to overwrite one that already
exists. Or do it by hand:

```bash
# JWT signing key: Base64, decoding to at least 256 bits (HS256's minimum,
# enforced by Keys.hmacShaKeyFor in JwtService's constructor).
openssl rand -base64 48

# Password-reset key: Base64, decoding to 16, 24 or 32 bytes (AES-128/192/256),
# enforced in PasswordService's constructor.
openssl rand -base64 32
```

Either way, set `JWT_SECRET`, `PASSWORD_RESET_AES_KEY`, `MAIL_USERNAME` and `MAIL_PASSWORD` in the
environment — see [`engine/.env.example`](engine/.env.example) for what each one is, and the root
[`.env.example`](.env.example) for the compose stack. Rotating `JWT_SECRET` stops every
already-issued token verifying, which logs every current session out. That is expected.

---

## Known weaknesses

These are design limits of the code on `main`, already understood. They are documented here so that
nobody spends a report on them — but a working exploit of anything below, or of anything not listed,
is still worth reporting.

**Password-reset tokens are AES/ECB over an email address.** Even under a fresh secret key they are
deterministic, unexpiring, not revocable, and they leak block structure. The correct design is an
opaque random token stored server-side with an expiry. Rotating the key closes the disclosure; it
does not fix the design.

**There is one role.** `Role` has exactly one value, `ADMIN`, so the `ADMIN_URLS` list in
`SecurityConfiguration` effectively means "any logged-in user". There is no privilege separation
between operators.

**The camera frame is public.** `/event/get_image/**` is in `PUBLIC_URLS` and needs no token. Anyone
who can reach the API can fetch the current worksite frame. CORS no longer permits every origin —
`SecurityConfiguration` refuses `*` at startup — but the endpoint itself is unauthenticated.

**The Kafka topic is unauthenticated.** Any producer that can reach the broker can publish to
`rawEvents`. A published `FALL` sends an email to every registered user. The engine validates the
`eventType` against its enum and drops what it does not recognise, and a message it cannot
deserialise is logged and skipped rather than retried — that is the whole of the input validation.

**The bearer token lives in `localStorage`.** Any script injection in the dashboard can read it.
Tokens last 20 minutes and there is no refresh flow — a session simply ends. Issued tokens are
stored and checked on every request, and `POST /auth/logout` marks the presented token expired and
revoked, so a token can be killed server-side; but nothing revokes a user's *other* outstanding
tokens, and the dashboard's own auto-logout only discards the token client-side.

**Registration is open.** `/auth/register` is public, and every registered user receives every fall
alert.
