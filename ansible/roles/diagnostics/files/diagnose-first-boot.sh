#!/usr/bin/env bash
# diagnose-first-boot.sh — collect diagnostic information for the Hearth
# first-boot password flow.
#
# Deployed to /usr/local/share/hearth/diag/ on the target host by the
# diagnostics Ansible role (development only by default).
#
# Run inside the VM as root when the initial password banner is not
# appearing in the portal:
#
#   vagrant ssh -- sudo /usr/local/share/hearth/diag/diagnose-first-boot.sh
#
# The script checks every component in the chain:
#   first-boot service → /run/hearth/portal-status.json → nginx → browser
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
for user in hearth hestia; do
    if id "$user" &>/dev/null; then
        ok "user '$user' exists: $(id "$user")"
    else
        fail "user '$user' does NOT exist"
    fi
done

hdr "2. First-boot service status"
systemctl status hearth-first-boot.service --no-pager --full || true

hdr "3. First-boot service journal (last 50 lines)"
journalctl -u hearth-first-boot.service --no-pager -n 50 || true

hdr "4. Flag and runtime files"
FLAG_FILE="/var/lib/hearth/first-boot-done"
PASSWORD_FILE="/run/hearth/initial-password"
STATUS_JSON="/run/hearth/portal-status.json"

if [ -f "$FLAG_FILE" ]; then
    ok "flag file present: $FLAG_FILE"
else
    fail "flag file MISSING: $FLAG_FILE  (first-boot.sh did not complete)"
fi

if [ -d /run/hearth ]; then
    ok "/run/hearth directory exists"
    ls -la /run/hearth/
else
    fail "/run/hearth directory MISSING"
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

hdr "6. nginx configuration (hearth site)"
CONF_PATHS=(
    /etc/nginx/sites-enabled/hearth.conf
    /etc/nginx/sites-available/hearth.conf
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

hdr "7. Portal web root files"
PORTAL_ROOT="/var/www/hearth/portal"
if [ -d "$PORTAL_ROOT" ]; then
    ok "portal root exists: $PORTAL_ROOT"
    ls -la "$PORTAL_ROOT/"
    if [ -f "$PORTAL_ROOT/index.html" ]; then
        ok "index.html present ($(wc -c < "$PORTAL_ROOT/index.html") bytes)"
    else
        fail "index.html MISSING from $PORTAL_ROOT  (nginx cannot serve the portal page)"
    fi
else
    fail "portal root directory MISSING: $PORTAL_ROOT"
fi

hdr "8. Fetch portal root page from localhost"
HTTP_CODE="$(curl -so /dev/null -w '%{http_code}' http://localhost/ || true)"
if [ "$HTTP_CODE" = "200" ]; then
    ok "GET http://localhost/ → HTTP $HTTP_CODE"
else
    fail "GET http://localhost/ → HTTP $HTTP_CODE  (expected 200)"
fi

hdr "9. Fetch /api/public/services/status from localhost"
if curl -sf http://localhost/api/public/services/status; then
    echo
    ok "curl succeeded"
else
    STATUS=$?
    fail "curl failed (exit $STATUS)"
fi

hdr "10. nginx error log (last 20 lines)"
NGINX_ERROR_LOG="/var/log/nginx/error.log"
if [ -f "$NGINX_ERROR_LOG" ]; then
    tail -20 "$NGINX_ERROR_LOG"
else
    warn "nginx error log not found at $NGINX_ERROR_LOG"
fi

hdr "11. nginx access log (last 20 lines)"
NGINX_ACCESS_LOG="/var/log/nginx/access.log"
if [ -f "$NGINX_ACCESS_LOG" ]; then
    if [ -s "$NGINX_ACCESS_LOG" ]; then
        tail -20 "$NGINX_ACCESS_LOG"
    else
        warn "nginx access log is empty — no requests have reached nginx yet"
        warn "This means the host browser is not reaching the VM (check VirtualBox port forwarding)"
    fi
else
    warn "nginx access log not found at $NGINX_ACCESS_LOG"
fi

hdr "12. Network interfaces"
ip addr show || ip link show || warn "ip command not available"

hdr "13. nftables ruleset (active)"
if command -v nft &>/dev/null; then
    nft list ruleset || warn "could not list nftables ruleset"
    echo
    # Explicit pass/fail: check whether tcp/80 has an accept rule from non-AP interfaces
    if nft list ruleset 2>/dev/null | grep -qE 'tcp dport 80 accept'; then
        ok "nftables has an accept rule for tcp/80"
        # Check the rule is NOT limited to a specific positive iifname match (old bug)
        if nft list ruleset 2>/dev/null | grep -E 'tcp dport 80 accept' | grep -v 'iifname !=' | grep -q 'iifname'; then
            warn "tcp/80 accept rule is a positive iifname match — may not work on all interface names"
            warn "Expected: iifname != \"wlan0\" tcp dport 80 accept"
            warn "Fix: vagrant provision (ensure latest nftables template is applied)"
        else
            ok "tcp/80 accept rule is a negative iifname match (interface-name-independent)"
        fi
    else
        fail "nftables has NO accept rule for tcp/80"
        fail "Portal traffic from the host will be dropped by the firewall"
        fail "Fix: vagrant provision to apply the latest firewall configuration"
    fi

    echo
    # Show packet/byte counters to reveal whether traffic is hitting any rule
    printf '  nftables byte/packet counters (shows if traffic is arriving):\n'
    nft list ruleset -a 2>/dev/null | grep -E 'bytes|packets|tcp dport|iif' | head -30 || true
else
    warn "nft not installed"
fi

hdr "14. Listening ports on 80 and 8000"
ss -tlnp 'sport = :80 or sport = :8000' || true

hdr "Done"
printf '  Paste the full output above into the issue.\n'
