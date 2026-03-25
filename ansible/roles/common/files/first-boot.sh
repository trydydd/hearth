#!/usr/bin/env bash
# first-boot.sh — one-shot first-boot credential generator for Hearth
#
# Generates a random 12-character alphanumeric admin password, sets it for
# the hestia system user, and stores the plaintext temporarily at
# /run/hearth/initial-password (0400, owned by hestia) so the admin
# API can expose it via /api/public/services/status on first boot.
#
# A flag file at /var/lib/hearth/first-boot-done prevents re-execution on
# subsequent boots.

set -euo pipefail

FLAG_FILE="/var/lib/hearth/first-boot-done"
PASSWORD_FILE="/run/hearth/initial-password"
STATUS_JSON="/run/hearth/portal-status.json"
ADMIN_USER="hestia"

# Idempotency guard — exit cleanly if already run
if [ -f "${FLAG_FILE}" ]; then
    exit 0
fi

# Generate a 12-character random alphanumeric password.
# head -c12 exits after reading 12 bytes, sending SIGPIPE to tr (exit 141).
# Under `set -o pipefail` that propagates as a pipeline failure, so we scope
# the pipefail relaxation to a subshell to avoid any risk of leaking the
# change into the rest of the script.
PASSWORD="$(set +o pipefail; openssl rand -base64 64 | tr -dc 'A-Za-z0-9' | head -c12)"
if [ "${#PASSWORD}" -ne 12 ]; then
    echo "ERROR: failed to generate a 12-character password" >&2
    exit 1
fi

# Set the password for the admin user
printf '%s:%s\n' "${ADMIN_USER}" "${PASSWORD}" | chpasswd

# Ensure the runtime directory exists (should be created by tmpfiles.d, but
# guard here in case this service runs before systemd-tmpfiles-setup.service).
# Mode 0755 lets nginx (www-data) traverse the directory to read portal-status.json
# while the individual password file below remains locked to 0400.
install -d -m 0755 -o "${ADMIN_USER}" -g "${ADMIN_USER}" /run/hearth

# Write the plaintext password with tight permissions so only the admin
# backend process user can read it
printf '%s\n' "${PASSWORD}" > "${PASSWORD_FILE}"
chown "${ADMIN_USER}:${ADMIN_USER}" "${PASSWORD_FILE}"
chmod 0400 "${PASSWORD_FILE}"

# Write a world-readable JSON status file so nginx can serve the first-boot
# password banner on the portal until the admin API (Stage 1) takes over.
printf '{"first_boot":true,"initial_password":"%s","services":[]}\n' "${PASSWORD}" > "${STATUS_JSON}"
chmod 0644 "${STATUS_JSON}"

# Mark first-boot as complete
touch "${FLAG_FILE}"
