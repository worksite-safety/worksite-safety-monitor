#!/usr/bin/env bash
#
# Create `.env` from `.env.example`, with both cryptographic secrets generated.
#
#     ./scripts/init-env.sh
#     ./scripts/init-env.sh --force     # overwrite an existing .env
#
# This exists because `.env.example` cannot ship working values for JWT_SECRET
# and PASSWORD_RESET_AES_KEY and must not pretend to. It ships them empty, so
# that compose's `${VAR:?...}` guard fires and names the variable; a filled-in
# placeholder satisfies that guard and fails forty lines into a Spring stack
# trace instead. That leaves a real gap between `cp .env.example .env` and a
# stack that starts, and this script is the thing that closes it.
#
# Nothing here is Docker-specific: it only reads and writes two files.

set -euo pipefail

# Defensive. If someone runs this as `bash -x scripts/init-env.sh` the trace
# would put both freshly generated secrets on their terminal and into their
# scrollback. Nothing below is interesting enough to trace.
set +x

readonly PROGRAM="${0##*/}"

die() {
  printf '%s: %s\n' "$PROGRAM" "$1" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/init-env.sh [--force]

Copies .env.example to .env and generates the two secrets it leaves empty:

  JWT_SECRET               openssl rand -base64 48
  PASSWORD_RESET_AES_KEY   openssl rand -base64 32

Every other setting keeps the value and the comments .env.example ships.
The generated secrets are never printed; read them out of .env if you need
them.

  --force, -f   Replace an existing .env. Refused by default: new keys
                invalidate every issued session token and every outstanding
                password-reset link.
  --help,  -h   This message.
EOF
}

force=0
while [ $# -gt 0 ]; do
  case "$1" in
    -f|--force) force=1 ;;
    -h|--help)  usage; exit 0 ;;
    *)          usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

# Anchor to the repository, not to the caller's directory, so this works the
# same from the root, from `scripts/`, or from an absolute path in a Makefile.
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH='' cd -- "$script_dir/.." && pwd)

readonly example="$repo_root/.env.example"
readonly target="$repo_root/.env"

[ -f "$example" ] || die "no .env.example at $example - run this from a checkout of the repository"

# Refuse rather than clobber. Regenerating JWT_SECRET signs out every logged-in
# user; regenerating PASSWORD_RESET_AES_KEY makes every reset link already in
# somebody's inbox undecryptable, and those links have no expiry, so there is no
# window after which this stops mattering. Deliberately no automatic backup: a
# `.env.bak` holding the old keys is not covered by .gitignore.
if [ -e "$target" ] && [ "$force" -ne 1 ]; then
  printf '%s: %s already exists - not touching it.\n' "$PROGRAM" "$target" >&2
  printf '\n' >&2
  printf 'Re-run with --force to replace it, but understand what that costs:\n' >&2
  printf '  * a new JWT_SECRET invalidates every token in issue, logging out\n' >&2
  printf '    every active session\n' >&2
  printf '  * a new PASSWORD_RESET_AES_KEY makes every reset link already sent\n' >&2
  printf '    undecryptable, and those links never expire on their own\n' >&2
  printf '\n' >&2
  printf 'To add a setting that .env.example has gained since, copy that one\n' >&2
  printf 'line across by hand and leave the secrets alone.\n' >&2
  exit 1
fi

command -v openssl >/dev/null 2>&1 || die "openssl not found on PATH, and both secrets have to come from somewhere.
  Debian/Ubuntu   sudo apt-get install openssl
  Fedora/RHEL     sudo dnf install openssl
  macOS           openssl ships with the system; brew install openssl@3 for a newer one
  Windows         use Git Bash, which bundles it, and run this script from there"

# `tr` strips the trailing newline, and any wrap openssl might insert: it breaks
# base64 output at 64 characters, and 48 bytes encodes to exactly 64. A newline
# inside the value would travel into the container and fail Base64 decoding
# there, which is the class of failure this whole script exists to prevent.
jwt_secret=$(openssl rand -base64 48 | tr -d '\n\r')
aes_key=$(openssl rand -base64 32 | tr -d '\n\r')

[ -n "$jwt_secret" ] && [ -n "$aes_key" ] || die "openssl produced an empty key - refusing to write a .env that cannot work"

# 077 so the temporary file is unreadable by anyone else from the moment it is
# created, rather than being chmod-ed after the secrets are already in it.
umask 077

tmp="$target.tmp.$$"
trap 'rm -f "$tmp"' EXIT INT TERM

# Substituted with a read loop rather than sed: generated base64 contains '/'
# and '+', which are sed's delimiter and a regex metacharacter respectively, and
# every escaping scheme for that is a bug waiting to happen. A prefix match on
# the whole line has no such failure mode, and it preserves every comment in
# .env.example, which is where this project keeps its configuration reference.
filled_jwt=0
filled_aes=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    JWT_SECRET=*)
      printf '%s\n' "JWT_SECRET=$jwt_secret"
      filled_jwt=1
      ;;
    PASSWORD_RESET_AES_KEY=*)
      printf '%s\n' "PASSWORD_RESET_AES_KEY=$aes_key"
      filled_aes=1
      ;;
    *)
      printf '%s\n' "$line"
      ;;
  esac
done < "$example" > "$tmp"

# If .env.example is ever restructured and a key stops being a bare assignment
# at the start of a line, this catches it here rather than at `docker compose
# up`, where the symptom would be a required-variable error that looks like the
# user's fault.
[ "$filled_jwt" -eq 1 ]  || die "no JWT_SECRET= line in .env.example - it has changed shape and this script needs updating"
[ "$filled_aes" -eq 1 ]  || die "no PASSWORD_RESET_AES_KEY= line in .env.example - it has changed shape and this script needs updating"

mv -- "$tmp" "$target"
trap - EXIT INT TERM
chmod 600 "$target" 2>/dev/null || true

printf '%s: wrote %s\n' "$PROGRAM" "$target"
printf '  JWT_SECRET               generated (48 bytes, base64)\n'
printf '  PASSWORD_RESET_AES_KEY   generated (32 bytes, base64)\n'
printf '\n'
printf 'The values are not printed here on purpose; they are in .env, which is\n'
printf 'gitignored. Every other setting kept the default .env.example ships,\n'
printf 'including MAIL_USERNAME and MAIL_PASSWORD, which are fine as they are\n'
printf 'for a local demo - only the two features that send mail need real ones.\n'
printf '\n'
printf 'Next:  docker compose up --build\n'
