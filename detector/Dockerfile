# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# The detector: ultralytics, OpenCV and a Kafka client around this package.
#
# This is by far the largest of the three images and every megabyte of it is
# torch. See the CPU-wheel comment below for the one decision that keeps it
# under 2 GB instead of over 6.
#
# What is NOT in here, deliberately:
#
#   * the model weights.  best.pt is 52 MB of trained model and yolov8s-pose.pt
#     is 23 MB; both are gitignored (see the repository .gitignore, which
#     records that they are what made this repo 250 MB before the v1.0.0 history
#     rewrite). Baking them in would make the image unbuildable from a clean
#     clone - exactly the failure this file exists to remove. They arrive as a
#     read-only bind mount instead; compose maps ./detector/models.
#   * the footage.  Same reasoning, and a clip of a real worksite is not
#     redistributable anyway.
#
# Neither can be fetched for us: require_weights() in __main__.py refuses to
# start without them precisely so that a mistyped path cannot trigger a silent
# ultralytics download of a *stock* model and leave a rig running the wrong
# detector. The entrypoint below therefore only adds the one thing the package
# cannot know - that in a container these paths are bind mounts, and which host
# directory each one came from.
# ---------------------------------------------------------------------------
# Trixie (Debian 13), not bookworm. A scan of the bookworm-based image reported 8
# CRITICAL CVEs with no fix available - "no fix available" because Debian 12 never
# shipped patched versions of the affected packages, so there was nothing to
# upgrade to and no amount of apt-get would have cleared them. Trixie has them.
# Python is 3.12.13 on both bases, so no interpreter change is hiding in this line.
FROM python:3.12-slim-trixie AS runtime

# OpenCV's shared-library dependencies. pyproject pins `opencv-python`, not
# `-headless`, so the GUI-linked wheel is what gets installed and it needs
# libGL and glib present even though this program never opens a window
# (cv2.imshow is not called anywhere - the "display" is a JPEG on disk).
# Without these, `import cv2` dies with "libGL.so.1: cannot open shared object
# file", six layers into an import chain, which reads as a broken install
# rather than a missing OS package.
#
# `libglib2.0-0` is a VIRTUAL package on trixie, not a real one - Debian's 64-bit
# time_t transition renamed the real package to libglib2.0-0t64, which Provides the
# old name, and apt resolves it because that is the only provider. So the line below
# survived the move to Debian 13 unchanged, and installs libglib2.0-0t64. Left as
# the plain name deliberately: libglib2.0-0t64 does not exist in bookworm at all, so
# spelling it out would pin this file to Debian 13 and later for no gain. If you run
# `apt-cache policy libglib2.0-0` and see "Candidate: (none)", that is the virtual
# package showing through - not a broken line. `libgl1` is real on both.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Build tooling, pinned, and installed BEFORE anything else. The position is the
# whole point: the CPU-wheel layer below uses `--index-url`, which REPLACES PyPI
# rather than adding to it, and download.pytorch.org hosts exactly three setuptools
# (70.0.0, 70.2.0, 78.1.0) and no wheel at all. Leave this until later and torch's
# own `setuptools>=77.0.3` gets satisfied from that mirror by 78.1.0 - the version
# these pins exist to get past - and the image ships it. Doing it here means the
# requirement is already met and pip never asks the mirror.
#
# The base image carries pip and nothing else; setuptools and wheel otherwise arrive
# as somebody else's transitive dependency, at whatever version that somebody
# happened to need. That is what is being removed here, more than any one CVE.
#
# Pinned exactly rather than `>=`: a floor resolves to whatever is newest on the day
# of the build, which would make two builds of the same commit contain different
# software. Every bump here is therefore a deliberate edit to this line.
#
# setuptools is 83.0.0 because of what it VENDORS, not because of setuptools itself.
# A scan of the image reports the contents of setuptools/_vendor/ as packages in their
# own right, and those were the only two fixable HIGH findings in the whole image -
# every other CRITICAL/HIGH is a Debian package with no fixed version upstream. The
# wheel pin on this line does not reach them; it installs the TOP-LEVEL wheel, and
# `pip show wheel` reporting 0.46.2 while a scanner still says 0.45.1 is the two
# copies talking past each other. Only moving setuptools moves the vendored copy.
#
# Measured against the artifacts on PyPI, not against a changelog:
#
#     78.1.1 - 80.9.0    wheel 0.45.1   jaraco.context 5.3.0   both flagged
#     80.10.1            wheel 0.45.1   jaraco.context 6.1.0   half of it
#     80.10.2 and later  wheel 0.46.3   jaraco.context 6.1.0   both clear
#
# so 80.10.2 is the lowest version that clears both. 83.0.0 is what is pinned because
# it clears a third finding the others do not - CVE-2026-59890 is against setuptools
# itself and names 83.0.0 as its fix - and because 80.10.2 through 82.x buy nothing
# that 83.0.0 does not. Note that the vendored jaraco.context directory is spelled
# `jaraco_context-6.1.0.dist-info` from 80.10.1 on, with an underscore; grepping the
# old dotted name finds nothing and looks like a removal rather than an upgrade.
#
# THE behaviour change to know about, and the reason this is a Dockerfile edit rather
# than a version bump: setuptools 82.0.0 DELETED pkg_resources. 81.0.0 still ships it,
# 82.0.0 and later do not, so any `import pkg_resources` in this image is now an
# ImportError rather than a deprecation warning. Nothing here does one - checked
# across ultralytics, torch, torchvision, cv2 and kafka-python-ng, and the suite runs
# inside the built image to prove it - but a future dependency that does will fail on
# import, and 81.0.0 is the last version that would forgive it.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade 'pip==25.3' 'setuptools==83.0.0' 'wheel==0.46.2'

# THE size decision. `pip install ultralytics` on linux/amd64 resolves torch
# from PyPI, and that wheel bundles the CUDA runtime, cuDNN and cuBLAS: roughly
# 2.5 GB downloaded and over 6 GB unpacked, for a container that has no GPU and
# could not use one without device passthrough. Installing the CPU build first,
# from PyTorch's own CPU index, satisfies ultralytics' `torch>=1.8` requirement
# so the resolver below leaves it alone. Costs ~200 MB instead.
#
# If you DO want GPU inference, delete this layer, add `--gpus all` and the
# NVIDIA container toolkit, and accept the image size - do not try to have both.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

WORKDIR /opt/detector

# Package metadata before sources: the (large) dependency install is then
# invalidated only by a pyproject change, not by editing a rule module.
COPY pyproject.toml ./
COPY src/ src/

# pillow is named here and nowhere else on purpose. It is purely transitive -
# torchvision, matplotlib and ultralytics all pull it in, and nothing in this package
# imports PIL - so it arrives from the CPU-wheel index above at 12.2.0 and stays
# there: every downstream bound (pillow>=7.1.2, >=9, !=8.3.*,>=5.3.0) is satisfied by
# 12.2.0, so no install below would ever move it on its own.
#
# Constrained in this layer rather than added to the `cv` extra in pyproject.toml:
# putting it there would assert a direct dependency this codebase does not have, and
# would push a container's security pin onto every developer who runs
# `pip install -e .[cv]` on their laptop. The pin belongs to the image, so it lives
# in the image.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir '.[cv]' 'pillow==12.3.0'

# Ultralytics writes a settings YAML and scratch files on first use, and
# defaults to ~/.config/Ultralytics - which is not writable by the non-root user
# below. Pointed at /tmp instead. YOLO_AUTOINSTALL=false is the important one:
# by default ultralytics runs `pip install` ITSELF when it decides a dependency
# is missing, which in a container means a network fetch at inference time,
# mutating a supposedly immutable image, from inside the frame loop.
ENV YOLO_CONFIG_DIR=/tmp/ultralytics \
    MPLCONFIGDIR=/tmp/matplotlib \
    YOLO_AUTOINSTALL=false \
    PYTHONUNBUFFERED=1

# Same fixed uid as the engine image, for the same reason: the two share a
# named volume for output_image.jpg and a volume takes its ownership from
# whichever container mounts it first. Equal uids make that a non-question.
RUN groupadd -g 10001 -r worksite \
 && useradd -u 10001 -r -g worksite -d /opt/detector worksite \
 && mkdir -p /var/lib/worksite/preview /tmp/ultralytics /tmp/matplotlib \
 && chown -R worksite:worksite /var/lib/worksite /tmp/ultralytics /tmp/matplotlib

# Mount points, created with ownership so the bind mounts land somewhere real
# even when nothing is mounted over them (which is the case this entrypoint
# reports on).
RUN mkdir -p /opt/detector/models /media && chown worksite:worksite /opt/detector/models /media

USER worksite

# Ultralytics' `runs_dir`, moved off the working directory - and its telemetry,
# switched off. Both are settings in a JSON file rather than environment
# variables, so the only way to set them is to write the file, which is what
# this does at build time.
#
# runs_dir matters because it is NOT optional output. YOLO's predictor builds a
# save_dir on construction whether or not anything is ever saved, and
# get_save_dir() calls increment_path(..., mkdir=True) - so the first inference
# call unconditionally creates `runs/detect/predictN` relative to the working
# directory. As uid 10001 in /opt/detector that is
#
#     PermissionError: [Errno 13] Permission denied: 'runs'
#
# raised inside the frame loop, on every frame. The frame loop is built to
# survive a bad frame, so it does: the run completes, exits 0, and reports
# "no events were collected" - a detector that looks like it worked and saw a
# quiet site, when in fact it never ran a model once. (Observed. And note the
# empty runs/detect/predict1..8 directories committed to this repository -
# that is the same behaviour, from before the process ran as a non-root user.)
#
# sync=False stops ultralytics POSTing anonymous analytics on startup. A
# container that phones home from a worksite network is a surprise nobody
# consented to, and on an air-gapped rig it is a startup delay with no
# explanation.
RUN python -c "from ultralytics import settings; settings.update({'runs_dir': '/tmp/ultralytics/runs', 'datasets_dir': '/tmp/ultralytics/datasets', 'weights_dir': '/tmp/ultralytics/weights', 'sync': False})"

USER root

# The whole of the container-specific knowledge, and no more. The package's own
# startup errors are good - require_weights names both files, the working
# directory and where to download them - but they name CONTAINER paths, and an
# operator staring at "/opt/detector/models/best.pt is not there" has no way to
# know that the fix is a file in ./detector/models on their laptop. That
# translation is the only thing added here; everything else is left to the
# program, so there is no second copy of the rules to drift.
COPY <<'PREFLIGHT' /usr/local/bin/preflight
#!/bin/sh
set -e

# `--help` is answered by the program, always, even on a container with nothing
# mounted into it. A preflight that can refuse to show the usage text is a
# preflight that can stop someone finding out how to fix it.
for arg in "$@"; do
  case "$arg" in
    -h|--help) exec "$@" ;;
  esac
done

if [ ! -f /opt/detector/models/best.pt ] || [ ! -f /opt/detector/models/yolov8s-pose.pt ]; then
  cat >&2 <<'MSG'
worksite-detector: the model weights are not in this container.

  /opt/detector/models is a read-only bind mount of ./detector/models on the
  host, and at least one of best.pt (52 MB) or yolov8s-pose.pt (23 MB) is not
  there. Both are gitignored, so a fresh clone does not have them.

    yolov8s-pose.pt  stock Ultralytics pose weights, also available from
                     https://github.com/ultralytics/assets/releases
    best.pt          the model THIS project trained, for no-helmet / no-jacket /
                     fall. There is no public copy of it anywhere else.

  Both are attached to the weights-v1 release of this repository. From the
  repository root on the HOST, not in here:

    gh release download weights-v1 \
      --repo worksite-safety/worksite-safety-monitor \
      --pattern '*.pt' --dir detector/models

  or download both by hand from
  https://github.com/worksite-safety/worksite-safety-monitor/releases/tag/weights-v1
  into ./detector/models, then bring this container back up. The release notes
  carry the SHA256 of both files.

  They are not downloaded for you on purpose: ultralytics will silently fetch a
  stock model for any weights name it recognises, so a wrong path would leave a
  rig running a detector that does not know what a hard hat is, and say nothing.

  Everything else in the stack runs without this container:
      docker compose up kafka mongodb engine web
MSG
  exit 3
fi

# Only checked when the source names a file. A webcam index ("0") or a stream
# URL (rtsp://...) is not a path and is the program's business, not this
# script's.
case "${WSM_CAMERA__SOURCE:-}" in
  /*)
    [ -e "$WSM_CAMERA__SOURCE" ] || cat >&2 <<MSG
worksite-detector: no footage at "$WSM_CAMERA__SOURCE".

  /media is a read-only bind mount of the directory named by DEMO_VIDEO_DIR in
  your .env (default ./demo). Drop any video file in there and set
  DEMO_VIDEO to its name, or point the detector at a real camera - see the
  "Using a real camera" section of .env.example.

  No sample clip ships with this repository: worksite footage of identifiable
  people is not redistributable.
MSG
    [ -e "$WSM_CAMERA__SOURCE" ] || exit 3
    ;;
esac

# Replay the source when it runs out, if asked to. A video file is a finite
# thing: OpenCvFrameSource is single-pass by design, so at the end of the clip
# the pipeline flushes, closes and the process exits 0 - correct behaviour, and
# a demo that stops after 33 seconds with a frozen preview.
#
# Deliberately NOT done with `restart: unless-stopped` in compose, which would
# also restart the container when the preflight above fails, turning a missing
# weights file into an endless loop of the same 20-line message. The loop
# belongs to the successful case only; compose uses `restart: on-failure`.
#
# Deliberately NOT named WSM_*: config.py treats every WSM_-prefixed variable as
# a setting and makes an unrecognised one fatal, so WSM_DETECTOR__LOOP would not
# enable a loop, it would refuse to start with "unknown configuration section".
if [ "${DETECTOR_LOOP:-false}" = "true" ]; then
  # A non-zero exit still ends the loop: replaying a clip is the answer to
  # "finished", never to "failed".
  trap 'if [ -n "${child:-}" ]; then kill -TERM "$child" 2>/dev/null; fi' TERM INT
  while true; do
    "$@" &
    child=$!
    wait "$child" || exit $?
  done
fi

exec "$@"
PREFLIGHT
RUN chmod +x /usr/local/bin/preflight

USER worksite

# `preflight` execs through to the detector, so the detector is still pid 1's
# successor and still receives SIGTERM - which matters more here than anywhere
# else in the stack. __main__.py installs a SIGTERM handler that finishes the
# current frame, flushes any PPE violation window still open and closes the
# producer; a signal that never arrives loses the last violation of every run.
ENTRYPOINT ["/usr/local/bin/preflight", "worksite-detector"]
