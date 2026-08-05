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
# Stage 2 - serve it.
#
# nginx-unprivileged rather than plain nginx: it already runs as uid 101 with
# its temp and pid paths relocated, so it needs no root and no capability to
# bind, and it listens on 8080. Plain nginx as a non-root user requires patching
# four directory permissions and the pid path by hand.
# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=build /bundle /usr/share/nginx/html

# React Router owns the URL space, so every path that is not a real file has to
# be answered with index.html. Without this, a reload on /profile or a pasted
# /change-password?token=... link - the one link every password-reset mail
# contains - is a bare nginx 404.
COPY <<'NGINX' /etc/nginx/conf.d/default.conf
server {
    listen       8080;
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
