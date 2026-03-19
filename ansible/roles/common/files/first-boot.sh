#!/usr/bin/env bash
# first-boot.sh — one-shot first-boot credential generator for CafeBox
#
# Generates a random 12-character alphanumeric admin password, sets it for
# the cafebox-admin system user, and stores the plaintext temporarily at
# /run/cafebox/initial-password (0400, owned by cafebox-admin) so the admin
# API can expose it via /api/public/services/status on first boot.
#
# A flag file at /var/lib/cafebox/first-boot-done prevents re-execution on
# subsequent boots.

set -euo pipefail

FLAG_FILE="/var/lib/cafebox/first-boot-done"
PASSWORD_FILE="/run/cafebox/initial-password"
ADMIN_USER="cafebox-admin"

# Idempotency guard — exit cleanly if already run
if [ -f "${FLAG_FILE}" ]; then
    exit 0
fi

# Generate a 12-character random alphanumeric password
PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c12)"

# Set the password for the admin user
printf '%s:%s\n' "${ADMIN_USER}" "${PASSWORD}" | chpasswd

# Ensure the runtime directory exists (should be created by tmpfiles.d, but
# guard here in case this service runs before systemd-tmpfiles-setup.service)
install -d -m 0750 -o "${ADMIN_USER}" -g "${ADMIN_USER}" /run/cafebox

# Write the plaintext password with tight permissions so only the admin
# backend process user can read it
printf '%s\n' "${PASSWORD}" > "${PASSWORD_FILE}"
chown "${ADMIN_USER}:${ADMIN_USER}" "${PASSWORD_FILE}"
chmod 0400 "${PASSWORD_FILE}"

# Mark first-boot as complete
touch "${FLAG_FILE}"
