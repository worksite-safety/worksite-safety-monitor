# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Stage 1 - build the static bundle.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Lockfile first: `npm ci` is invalidated only when the dependency set changes.
COPY package.json package-lock.json ./

# `npm ci`, never `npm install`, and deliberately with no `|| npm install`
# fallback. ci fails loudly when package.json and package-lock.json have drifted
# apart; install would quietly resolve a different tree and rewrite the lock, so
# the image would contain dependencies nobody reviewed and CI would be testing a
# different set from the one shipped. A lockfile that no longer matches is a
# thing to fix, not to route around.
RUN npm ci --no-audit --no-fund

COPY . .

# Where the browser should reach the engine. The name is Vite's: only VITE_*
# variables are exposed to client code, and src/util/axios.js reads
# import.meta.env.VITE_API_URL with a localhost:8080 fallback. NO TRAILING
# SLASH - axios.js strips one, VideoStream builds `${apiBaseUrl}/event/...`,
# and web/.env.example documents it without.
#
# Baked in at BUILD time, unavoidably: a static bundle has no runtime
# environment to read, so pointing an already-built image at a different API
# means rebuilding it with a different --build-arg.
#
# It is localhost and not the `engine` service name because the caller is the
# operator's BROWSER, on the host, talking to the host's published port. It is
# not a container-to-container call, and a compose service name means nothing
# outside the compose network.
ARG VITE_API_URL=http://localhost:8080
ENV VITE_API_URL=${VITE_API_URL} \
    NODE_ENV=production \
    CI=true

# The bundle lands in build/. That is Vite configured to keep Create React App's
# path (vite.config.js sets `outDir: 'build'`) rather than Vite's own default of
# dist/, because .gitignore and the README already document build/ and there was
# no reason to make three files disagree.
#
# dist/ is still accepted as a fallback, and deliberately second: if someone
# drops the outDir override, this image keeps working instead of failing at the
# COPY with an empty directory. Neither present is a hard error with a sentence
# saying so - an nginx serving an empty root would otherwise start, pass its
# healthcheck on /healthz, and answer every real request with a 404.
RUN npm run build \
 && if   [ -d build ]; then mv build /bundle; \
    elif [ -d dist ];  then mv dist  /bundle; \
    else \
      echo "web: 'npm run build' produced neither dist/ nor build/." >&2; \
      echo "     Update the COPY in web/Dockerfile to name the real output dir." >&2; \
      exit 1; \
    fi \
 && test -f /bundle/index.html

# ---------------------------------------------------------------------------
# Stage 2 - patch the runtime base's OS packages.
#
# Trivy on this image reported 105 findings and every single one was an Alpine
# package from the base - 2 CRITICAL, 31 HIGH, 46 MEDIUM, 26 LOW, nothing from
# our own dependency tree. Both CRITICALs were libcrypto3 and libssl3 3.3.3-r0
# (CVE-2026-31789). The frontend dependency work could not reach any of them,
# because they do not arrive with npm - they arrive with the base image.
#
# The image is Alpine 3.21.3 and pins itself to v3.21/main + v3.21/community.
# That branch has already backported the fixes: `apk policy libcrypto3` inside
# the unmodified base offers 3.3.7-r0 from v3.21/main today, against the
# 3.3.3-r0 that is installed. The base is simply stale - nginx-unprivileged
# 1.27-alpine was built against Alpine 3.21.3 while the branch is now at
# v3.21.7. So `apk upgrade` pulls the fixes from the very repository the image
# already trusts, and the image stays on Alpine 3.21 rather than changing
# distribution or nginx version to dodge a CVE. Measured: this moves 22
# packages and leaves nginx itself untouched at 1.27.5-r1, because nginx and
# its modules are held at a version no configured repository supersedes.
#
# The fair objection is that this makes the build depend on when it runs. It
# does - but pinning the exact -r0 releases would be worse than not pinning:
# Alpine keeps only the newest build of each package per branch, so an exact
# pin breaks the build outright the day v3.21 ships a successor. Delete this
# stage once nginx-unprivileged rebuilds and the tag carries the fixes itself.
#
# This is a separate stage purely so that no `USER root` appears among the
# instructions that assemble the served image. apk needs root and the base
# already dropped to uid 101, so the privilege is taken here, used for exactly
# one command, and handed back before anything else happens.
# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS patched

USER root
RUN apk upgrade --no-cache
# Back to the uid the base image declares. Numeric rather than the `nginx`
# name, so it keeps meaning the same thing if the name ever moves.
USER 101

# ---------------------------------------------------------------------------
# Stage 3 - serve it.
#
# nginx-unprivileged rather than plain nginx: it already runs as uid 101 with
# its temp and pid paths relocated, so it needs no root and no capability to
# bind, and it listens on 8080. Plain nginx as a non-root user requires patching
# four directory permissions and the pid path by hand.
# ---------------------------------------------------------------------------
FROM patched AS runtime

COPY --from=build /bundle /usr/share/nginx/html

# React Router owns the URL space, so every path that is not a real file has to
# be answered with index.html. Without this, a reload on /profile or a pasted
# /change-password?token=... link - the one link every password-reset mail
# contains - is a bare nginx 404.
COPY <<'NGINX' /etc/nginx/conf.d/default.conf
server {
    # Both families, deliberately. `listen 8080;` alone binds 0.0.0.0 only, and
    # that is not a cosmetic gap: inside the container /etc/hosts maps localhost
    # to BOTH 127.0.0.1 and ::1, and BusyBox wget tries ::1 first. So the compose
    # healthcheck - `wget -qO- http://localhost:8080/healthz` - got "Connection
    # refused" on every single attempt while the same request to 127.0.0.1
    # answered "ok". FailingStreak reached 19. It went unnoticed because nothing
    # depends_on web with service_healthy and `docker compose up -d` still exits
    # 0; `docker compose up --wait`, which the PR and issue templates both tell
    # contributors to run, reports web as failed.
    #
    # Fixed on the server rather than by pointing the healthcheck at 127.0.0.1,
    # because the healthcheck is only the caller that happened to notice. Any
    # consumer that resolves localhost, or reaches this container over an
    # IPv6-enabled network, hits the same refusal. Teaching one caller to avoid a
    # name that is broken leaves the next person to rediscover it.
    #
    # ipv6only is on by default (nginx >= 1.3.4), so the two lines are two
    # separate sockets and do not fight over the v4 space. IPv4 traffic, and
    # therefore the published port mapping, behaves exactly as it did before.
    listen       8080;
    listen       [::]:8080;
    server_name  localhost;
    root         /usr/share/nginx/html;
    index        index.html;

    # Hashed asset filenames are content-addressed and safe to cache forever.
    location /static/ { expires 1y; add_header Cache-Control "public, immutable"; }
    location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }

    # index.html must NOT be cached, or a browser keeps loading the old bundle's
    # asset names after a redeploy and the app breaks with 404s on chunks.
    location = /index.html { add_header Cache-Control "no-store"; }

    location / { try_files $uri $uri/ /index.html; }

    # Plain-text liveness endpoint for the compose healthcheck. Distinct from /
    # so that a healthcheck cannot be satisfied by the SPA fallback answering
    # 200 for a bundle that was never actually copied in.
    location = /healthz {
        access_log off;
        default_type text/plain;
        return 200 "ok\n";
    }
}
NGINX

EXPOSE 8080
