# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Stage 1 - build the fat jar.
#
# The Maven *wrapper* is used rather than a `maven:` base image on purpose:
# .mvn/wrapper/maven-wrapper.properties pins Maven 3.9.5, and that pin is what
# CI, a developer's shell and this image should all agree on. A `maven:3.9-...`
# tag floats independently and would eventually build the jar with a Maven the
# project never tested against.
#
# Tests are skipped here, and that is not laziness. `./mvnw verify` runs the
# Failsafe suite, which starts MongoDB and Kafka through Testcontainers - i.e.
# it needs a Docker daemon *inside* the build. Docker-in-Docker for a build that
# CI already gates is a lot of machinery to re-prove something proven upstream.
# The contract is: CI runs the tests, this image packages the artifact.
# ---------------------------------------------------------------------------
FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /build

# The wrapper and the POM first, so that the dependency download layer is
# invalidated only by a POM change and not by every source edit.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

# The `sed` is not superstition. .gitattributes declares `engine/mvnw text
# eol=lf` and the committed blob is LF, so a fresh clone is fine - but a working
# tree checked out BEFORE that attribute existed keeps its CRLF endings and
# `git status` still calls it clean, because git normalises on read. Building
# from such a tree gives `./mvnw: not found`: the kernel reads the shebang as
# `/bin/sh\r`, which is not a program. That message names the wrong file and
# sends people looking for a missing wrapper that is right there. One line here
# ends the entire question. (Observed on the machine this file was written on.)
RUN sed -i 's/\r$//' mvnw && chmod +x mvnw

# A BuildKit cache mount rather than `dependency:go-offline`. go-offline is
# notoriously incomplete - it misses plugin dependencies resolved later in the
# lifecycle, so the "offline" build then reaches for the network anyway and
# fails confusingly. The cache mount gives the same rebuild speed with none of
# that, at the cost of not being a layer (it is not pushed with the image).
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -q dependency:resolve

COPY src/ src/
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -DskipTests package \
 && cp target/engine-*.jar /build/engine.jar

# ---------------------------------------------------------------------------
# Stage 2 - run it.
# ---------------------------------------------------------------------------
FROM eclipse-temurin:17-jre-alpine AS runtime

# Patch the OS packages the JRE layer brings in. Trivy on this image reported
# three HIGH CVEs and all three were Alpine packages, none of them ours:
# libexpat 2.8.1-r0 (CVE-2026-56408), and p11-kit + p11-kit-trust 0.25.5-r2
# (CVE-2026-2100). The dependency upgrade that cleaned the jar layer down to
# five MEDIUMs could not reach them, because they are not on our dependency
# tree at all - they arrive with the base.
#
# The two cheaper answers were measured rather than assumed, and both fail.
# `docker build --pull` changes nothing: a fresh pull of
# eclipse-temurin:17-jre-alpine is still Alpine 3.23.5 carrying those same three
# versions. And there is no newer tag to move to - 17-jre-alpine and
# 17-jre-alpine-3.23 resolve to the same image id, every 17-jre-alpine* tag was
# last rebuilt 2026-06-22, and Temurin publishes no Alpine 3.24 variant for 17.
# Upstream simply has not rebuilt, which is the whole problem.
#
# The patched packages do exist, in the branch this image is already pinned to:
# v3.23/main serves libexpat 2.8.2-r0 and p11-kit 0.26.2-r0 today. So `apk
# upgrade` takes them from the same repository the next line would use anyway,
# and the image stays on Alpine 3.23 rather than changing distribution to dodge
# three CVEs.
#
# The fair objection is that this makes the build depend on when it runs. It
# does - but the `apk add` immediately below has never pinned a version either,
# so this introduces no new class of drift. Pinning the exact -r0 releases would
# be worse than not pinning: Alpine keeps only the newest build of each package
# per branch, so an exact pin breaks the build outright the day 3.23 ships a
# successor. Delete this line once Temurin rebuilds its Alpine images and the
# tag carries the fixes on its own.
RUN apk upgrade --no-cache

# fontconfig + a real font family, for iText. EventService.generateEventsPdf
# builds the emailed report with iText 5, which resolves its base-14 fonts
# through the JDK's font machinery; on a font-less Alpine that surfaces as a
# runtime error from inside the PDF writer, on the one code path nobody exercises
# until an operator clicks "Send Report". ~12 MB to delete a whole class of
# failure that only appears in production.
RUN apk add --no-cache fontconfig ttf-dejavu

# Non-root, with a FIXED uid. The uid is not cosmetic: the engine and the
# detector share a volume for output_image.jpg, and a named volume takes its
# ownership from whichever container mounts it first. Both images therefore
# declare the same uid, so the answer does not depend on start order.
RUN addgroup -g 10001 -S worksite \
 && adduser -u 10001 -S -G worksite worksite

# Created here, with ownership, so an empty named volume mounted over it
# inherits 10001:10001 from this image.
RUN mkdir -p /var/lib/worksite/preview \
 && chown -R worksite:worksite /var/lib/worksite

WORKDIR /app
COPY --from=build --chown=worksite:worksite /build/engine.jar /app/engine.jar

USER worksite
EXPOSE 8080

# MaxRAMPercentage rather than a fixed -Xmx: the container's memory limit is set
# by whoever runs it, and a hardcoded heap is either wasteful or an OOM kill.
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"

# Exec form, so the JVM is pid 1 and receives SIGTERM directly - Spring's
# shutdown hook then closes the Kafka listener container and the Mongo client
# instead of being killed 10 seconds later.
ENTRYPOINT ["java", "-jar", "/app/engine.jar"]
