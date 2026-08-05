# Security policy

## Reporting a vulnerability

Report privately, through GitHub's private vulnerability reporting:

<https://github.com/worksite-safety/worksite-safety-monitor/security/advisories/new>

That opens a draft advisory visible only to you and the maintainers. It is also the "Security
vulnerability" contact link offered when you go to open an issue. If private reporting is not
available to you, contact a maintainer directly using the address on their recent commits.

**Please do not open a public issue for a security problem.** A public issue is a disclosure: it
reaches attackers at the same moment it reaches us, and before there is anything to upgrade to.

Useful things to include: what an attacker can do, the shortest sequence that demonstrates it, the
commit or release you tested, and whether you have already disclosed it anywhere.

What to expect: this is a small project maintained by its original authors in their own time. No
response time is promised. You will get an acknowledgement, a yes-or-no on whether we can reproduce
it, and credit in the advisory unless you would rather not have it.

## Supported versions

`v1.0.0` is the first public release, and the only supported one. Fixes land on `master`.

---

## Credentials that were committed to this repository

Three secrets were committed to this repository's git history:

| what | where it lived | what to do |
|---|---|---|
| A Gmail **app password** | `spring.mail.password` in `engine/src/main/resources/application.yml` | **Revoke** it in the Google account that issued it |
| The **JWT signing key** | a `private static final String` in `JwtService.java`, later the same YAML | **Rotate** it |
| The **password-reset AES key** | a 16-character literal in `PasswordService.java` | **Rotate it first** — see below |

The history has been rewritten and none of the three is in the working tree any more. **Rewriting
the history does not un-leak anything.** Every value above was public for as long as it was pushed,
and a rewrite cannot reach clones that already exist, forks, CI caches, mirrors, editor backups, or
anything else that fetched the repository before the rewrite. Treat all three as disclosed, because
they are.

Relocating a credential to an environment variable changes where the value is read from. It does not
change whether the value is compromised. **All three must be rotated or revoked.**

### The password-reset key is the urgent one

`PasswordService.encrypt(email)` produces the token that becomes the `?token=` of a password-reset
link, and `decrypt(token)` yields the address whose password is then changed. The token carries **no
expiry**, is not bound to a request, and cannot be revoked.

So anyone holding that key can mint a valid password-reset link for **any** address, at any time,
without ever touching this system. It is not a configuration value; it is an account-takeover key,
and it has been public.

Rotating it invalidates every reset link that has already been emailed. That is the correct outcome:
every one of those links is forgeable by anyone who can read the history.

### Rotating

All three are now environment variables with **no committed fallback**, so a deployment that forgets
one refuses to start rather than running on a key that is public knowledge. That property is
asserted by `ProductionConfigurationTest`, which reads the production YAML as raw text and pins the
exact set of variables that have no default.

```bash
# JWT signing key: Base64, decoding to at least 256 bits (HS256's minimum,
# enforced by Keys.hmacShaKeyFor in JwtService's constructor).
openssl rand -base64 48

# Password-reset key: Base64, decoding to 16, 24 or 32 bytes (AES-128/192/256),
# enforced in PasswordService's constructor.
openssl rand -base64 32
```

Then set `JWT_SECRET`, `PASSWORD_RESET_AES_KEY`, `MAIL_USERNAME` and `MAIL_PASSWORD` in the
environment — see [`engine/.env.example`](engine/.env.example). Rotating `JWT_SECRET` stops every
already-issued token verifying, which logs every current session out. That is expected.

---

## Known weaknesses

These are design limits of the released code, already understood. They are documented here so that
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
