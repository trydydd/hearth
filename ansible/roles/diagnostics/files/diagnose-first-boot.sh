#!/usr/bin/env bash
# diagnose-first-boot.sh — collect diagnostic information for the CafeBox
# first-boot password flow.
#
# Deployed to /usr/local/share/cafebox/diag/ on the target host by the
# diagnostics Ansible role (development only by default).
#
# Run inside the VM as root when the initial password banner is not
# appearing in the portal:
#
#   vagrant ssh -- sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
#
# The script checks every component in the chain:
#   first-boot service → /run/cafebox/portal-status.json → nginx → browser
#
# It prints a clearly labelled report; share the full output when filing an
# issue.

set -euo pipefail

hr()  { printf '\n%s\n' "──────────────────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$1"; hr; }
ok()  { printf '  [OK]   %s\n' "$1"; }
warn(){ printf '  [WARN] %s\n' "$1"; }
fail(){ printf '  [FAIL] %s\n' "$1"; }

hdr "1. System users"
for user in cafebox cafebox-admin; do
    if id "$user" &>/dev/null; then
        ok "user '$user' exists: $(id "$user")"
    else
        fail "user '$user' does NOT exist"
    fi
done

hdr "2. First-boot service status"
systemctl status cafebox-first-boot.service --no-pager --full || true

hdr "3. First-boot service journal (last 50 lines)"
journalctl -u cafebox-first-boot.service --no-pager -n 50 || true

hdr "4. Flag and runtime files"
FLAG_FILE="/var/lib/cafebox/first-boot-done"
PASSWORD_FILE="/run/cafebox/initial-password"
STATUS_JSON="/run/cafebox/portal-status.json"

if [ -f "$FLAG_FILE" ]; then
    ok "flag file present: $FLAG_FILE"
else
    fail "flag file MISSING: $FLAG_FILE  (first-boot.sh did not complete)"
fi

if [ -d /run/cafebox ]; then
    ok "/run/cafebox directory exists"
    ls -la /run/cafebox/
else
    fail "/run/cafebox directory MISSING"
fi

if [ -f "$PASSWORD_FILE" ]; then
    ok "password file present: $PASSWORD_FILE"
    ls -la "$PASSWORD_FILE"
else
    fail "password file MISSING: $PASSWORD_FILE"
fi

if [ -f "$STATUS_JSON" ]; then
    ok "portal-status.json present: $STATUS_JSON"
    ls -la "$STATUS_JSON"
    printf '  Contents: '
    cat "$STATUS_JSON"
    echo
else
    fail "portal-status.json MISSING: $STATUS_JSON"
fi

hdr "5. nginx service"
if systemctl is-active --quiet nginx; then
    ok "nginx is running"
else
    fail "nginx is NOT running"
    systemctl status nginx --no-pager || true
fi

hdr "6. nginx configuration (cafebox site)"
CONF_PATHS=(
    /etc/nginx/sites-enabled/cafebox.conf
    /etc/nginx/sites-available/cafebox.conf
)
for p in "${CONF_PATHS[@]}"; do
    if [ -e "$p" ]; then
        ok "found: $p"
    else
        warn "not found: $p"
    fi
done

printf '\n  nginx -T output (active config):\n'
nginx -T 2>&1 | grep -A10 "services/status" || warn "no /api/public/services/status location found in nginx config"

hdr "7. Fetch /api/public/services/status from localhost"
if curl -sf http://localhost/api/public/services/status; then
    echo
    ok "curl succeeded"
else
    STATUS=$?
    fail "curl failed (exit $STATUS)"
fi

hdr "8. nginx error log (last 20 lines)"
NGINX_ERROR_LOG="/var/log/nginx/error.log"
if [ -f "$NGINX_ERROR_LOG" ]; then
    tail -20 "$NGINX_ERROR_LOG"
else
    warn "nginx error log not found at $NGINX_ERROR_LOG"
fi

hdr "9. nftables ruleset (active)"
if command -v nft &>/dev/null; then
    nft list ruleset || warn "could not list nftables ruleset"
else
    warn "nft not installed"
fi

hdr "10. Listening ports on 80 and 8000"
ss -tlnp 'sport = :80 or sport = :8000' || true

hdr "Done"
printf '  Paste the full output above into the issue.\n'
