#!/usr/bin/env bash
# scripts/test-vagrant.sh — Integration test suite for the Hearth Vagrant VM
#
# Usage:
#   ./scripts/test-vagrant.sh
#
# Requires a running Vagrant VM (vagrant up).
# Tests are split into two layers:
#   HTTP  — curl requests through the forwarded port (localhost:8080)
#   VM    — service/port/file checks over vagrant ssh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HEARTH_YAML="${REPO_ROOT}/hearth.yaml"
BASE_URL="http://localhost:8080"
PASS=0; FAIL=0; WARN=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YEL='\033[0;33m'; GRN='\033[0;32m'; RST='\033[0m'; BOLD='\033[1m'
ok()   { printf "${GRN}  [PASS]${RST} %s\n" "$1"; PASS=$((PASS+1)); }
fail() { printf "${RED}  [FAIL]${RST} %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "${YEL}  [WARN]${RST} %s\n" "$1"; WARN=$((WARN+1)); }
hdr()  { printf "\n${BOLD}=== %s ===${RST}\n" "$1"; }
sub()  { printf "\n${BOLD}--- %s ---${RST}\n" "$1"; }

# Run a command inside the VM and return its output
vm() { vagrant ssh -- "$*" 2>/dev/null | tr -d '\r'; }

# HTTP test: assert response code
# Usage: http_check LABEL URL EXPECTED_CODE [extra curl args...]
http_check() {
    local label="$1" url="$2" expected="$3"
    shift 3
    local actual
    actual=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$@" "$url" 2>/dev/null || echo "000")
    if [ "$actual" = "$expected" ]; then
        ok "$label → HTTP $actual"
    else
        fail "$label → expected HTTP $expected, got HTTP $actual"
    fi
}

# HTTP test: assert response contains a string
# Usage: http_contains LABEL URL STRING [extra curl args...]
http_contains() {
    local label="$1" url="$2" expected="$3"
    shift 3
    local body
    body=$(curl -s --max-time 5 "$@" "$url" 2>/dev/null || echo "")
    if echo "$body" | grep -q "$expected"; then
        ok "$label → body contains \"$expected\""
    else
        fail "$label → body missing \"$expected\""
    fi
}

# HTTP test: assert Location header value on redirect
http_redirects_to() {
    local label="$1" url="$2" expected_location="$3"
    shift 3
    local headers
    headers=$(curl -s -I --max-time 5 "$@" "$url" 2>/dev/null || echo "")
    local location
    location=$(echo "$headers" | grep -i "^location:" | tr -d '\r' | awk '{print $2}')
    if [ "$location" = "$expected_location" ]; then
        ok "$label → Location: $location"
    else
        fail "$label → expected Location: $expected_location, got: ${location:-none}"
    fi
}

# VM: assert a systemd service is in the expected state
svc_check() {
    local label="$1" unit="$2" expected_sub="$3"
    local actual
    actual=$(vm "systemctl show '$unit' --property=SubState --value" 2>/dev/null | tr -d '[:space:]')
    if [ "$actual" = "$expected_sub" ]; then
        ok "$label ($unit) is $expected_sub"
    else
        fail "$label ($unit) expected $expected_sub, got ${actual:-unknown}"
    fi
}

# VM: assert a port is listening
port_check() {
    local label="$1" port="$2"
    local result
    # Grep runs locally to avoid pipe-in-PTY issues with vagrant ssh -t
    result=$(vm "sudo ss -tlnp" | grep ":$port ")
    if [ -n "$result" ]; then
        ok "$label listening on :$port"
    else
        fail "$label NOT listening on :$port"
    fi
}

# VM: assert a file exists (sudo — some paths are root:hestia 0750)
file_check() {
    local label="$1" path="$2"
    local result
    result=$(vm "sudo test -e '$path' && echo yes || echo no")
    if [ "$result" = "yes" ]; then
        ok "$label present ($path)"
    else
        fail "$label MISSING ($path)"
    fi
}

# Parse a boolean from hearth.yaml: yaml_bool <dot.path> → 0 (true) or 1 (false/missing)
yaml_bool() {
    python3 - "$HEARTH_YAML" "$1" <<'EOF'
import sys, yaml
with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)
keys = sys.argv[2].split('.')
val = cfg
for k in keys:
    val = val.get(k, {}) if isinstance(val, dict) else {}
sys.exit(0 if val is True else 1)
EOF
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
hdr "PRE-FLIGHT"

if ! command -v vagrant >/dev/null 2>&1; then
    echo "vagrant not found — aborting." >&2; exit 1
fi
if ! vagrant status 2>/dev/null | grep -q "running"; then
    echo "Vagrant VM is not running. Start it with: vagrant up" >&2; exit 1
fi
ok "Vagrant VM is running"

if ! curl -s --max-time 3 "$BASE_URL/" -H "Host: hearth.local" -o /dev/null; then
    fail "localhost:8080 unreachable — is port forwarding active?"
    exit 1
fi
ok "localhost:8080 reachable"

# Determine which services are enabled from hearth.yaml
CHAT_ON=false;    yaml_bool "services.chat.enabled"         && CHAT_ON=true
JUKEBOX_ON=false; yaml_bool "services.music.enabled"        && JUKEBOX_ON=true
KIWIX_ON=false;   yaml_bool "services.kiwix.enabled"        && KIWIX_ON=true
CAPTIVE_ON=false; yaml_bool "captive_portal.enabled"        && CAPTIVE_ON=true

printf "  Services: chat=%s  jukebox=%s  kiwix=%s  captive_portal=%s\n" \
    "$CHAT_ON" "$JUKEBOX_ON" "$KIWIX_ON" "$CAPTIVE_ON"

BOX_DOMAIN=$(python3 -c "
import yaml
with open('$HEARTH_YAML') as f: cfg = yaml.safe_load(f)
print(cfg.get('box', {}).get('domain', 'hearth.local'))
" 2>/dev/null || echo "hearth.local")

# ---------------------------------------------------------------------------
# HTTP — Portal
# ---------------------------------------------------------------------------
hdr "HTTP — PORTAL"

http_check  "Portal landing page" \
    "$BASE_URL/" 200 -H "Host: $BOX_DOMAIN"
http_contains "Portal references hearth stylesheet" \
    "$BASE_URL/" "hearth.css" -H "Host: $BOX_DOMAIN"

# ---------------------------------------------------------------------------
# HTTP — Admin
# ---------------------------------------------------------------------------
hdr "HTTP — ADMIN"

http_redirects_to "/admin redirects to /admin/" \
    "$BASE_URL/admin" "http://$BOX_DOMAIN/admin/" -H "Host: $BOX_DOMAIN"
http_check "Admin login page" \
    "$BASE_URL/admin/" 200 -H "Host: $BOX_DOMAIN"
http_contains "Admin login has login form" \
    "$BASE_URL/admin/login.html" "password" -H "Host: $BOX_DOMAIN"

sub "Admin backend API"
http_check "/healthz reachable (seeds CSRF cookie)" \
    "$BASE_URL/healthz" 200 -H "Host: $BOX_DOMAIN"
CSRF_COOKIE=$(curl -s -D - -o /dev/null --max-time 5 "$BASE_URL/healthz" -H "Host: $BOX_DOMAIN" 2>/dev/null \
    | grep -i "set-cookie" | grep -o "csrf_token=[^;]*" | head -1)
if [ -n "$CSRF_COOKIE" ]; then
    ok "CSRF cookie set by /healthz ($CSRF_COOKIE)"
else
    fail "CSRF cookie NOT set by /healthz"
fi

# ---------------------------------------------------------------------------
# HTTP — Captive portal
# ---------------------------------------------------------------------------
if [ "$CAPTIVE_ON" = "true" ]; then
    hdr "HTTP — CAPTIVE PORTAL"

    http_check "/captive-portal.html accessible on box domain" \
        "$BASE_URL/captive-portal.html" 200 -H "Host: $BOX_DOMAIN"

    sub "Hostname catch-all redirects"
    for check_host in \
        "connectivity-check.ubuntu.com." \
        "connectivity-check.ubuntu.com" \
        "nmcheck.gnome.org" \
        "network-test.debian.org" \
        "example.com"; do
        http_redirects_to "Host: $check_host → /captive-portal.html" \
            "$BASE_URL/" "http://$BOX_DOMAIN/captive-portal.html" \
            -H "Host: $check_host"
    done

    sub "Path-based redirects (external host)"
    for path in /hotspot-detect.html /library/test/success.html /generate_204 \
                /ncsi.txt /connecttest.txt /redirect /success.txt /canonical.html; do
        http_redirects_to "Host: example.com$path → /captive-portal.html" \
            "$BASE_URL$path" "http://$BOX_DOMAIN/captive-portal.html" \
            -H "Host: example.com"
    done

    sub "Box domain is NOT redirected"
    http_check "Host: $BOX_DOMAIN / stays at 200" \
        "$BASE_URL/" 200 -H "Host: $BOX_DOMAIN"
else
    hdr "HTTP — CAPTIVE PORTAL"
    warn "captive_portal.enabled is false — skipping captive portal tests"
fi

# ---------------------------------------------------------------------------
# HTTP — Services
# ---------------------------------------------------------------------------
hdr "HTTP — SERVICES"

if [ "$CHAT_ON" = "true" ]; then
    http_redirects_to "/chat redirects to /chat/" \
        "$BASE_URL/chat" "http://$BOX_DOMAIN/chat/" -H "Host: $BOX_DOMAIN"
    http_check "Chat frontend" \
        "$BASE_URL/chat/" 200 -H "Host: $BOX_DOMAIN"
else
    warn "chat disabled — skipping"
fi

if [ "$JUKEBOX_ON" = "true" ]; then
    http_redirects_to "/jukebox redirects to /jukebox/" \
        "$BASE_URL/jukebox" "http://$BOX_DOMAIN/jukebox/" -H "Host: $BOX_DOMAIN"
    http_check "Jukebox frontend" \
        "$BASE_URL/jukebox/" 200 -H "Host: $BOX_DOMAIN"
    http_check "Jukebox health endpoint" \
        "$BASE_URL/jukebox/health" 200 -H "Host: $BOX_DOMAIN"
else
    warn "jukebox disabled — skipping"
fi

if [ "$KIWIX_ON" = "true" ]; then
    http_redirects_to "/library redirects to /library/" \
        "$BASE_URL/library" "http://$BOX_DOMAIN/library/" -H "Host: $BOX_DOMAIN"
    http_check "Kiwix library" \
        "$BASE_URL/library/" 200 -H "Host: $BOX_DOMAIN"
else
    warn "kiwix disabled — skipping"
fi

# ---------------------------------------------------------------------------
# VM — Systemd services
# ---------------------------------------------------------------------------
hdr "VM — SYSTEMD SERVICES"

svc_check "nginx"                nginx.service              "running"
svc_check "Admin backend"        hearth-admin-backend.service running
svc_check "First-boot"           hearth-first-boot.service  exited
[ "$CHAT_ON"    = "true" ] && svc_check "Chat"    hearth-chat.service    running || warn "chat disabled — skipping"
[ "$JUKEBOX_ON" = "true" ] && svc_check "Jukebox" hearth-jukebox.service running || warn "jukebox disabled — skipping"
[ "$KIWIX_ON"   = "true" ] && svc_check "Kiwix"   kiwix.service          running || warn "kiwix disabled — skipping"

# ---------------------------------------------------------------------------
# VM — Listening ports
# ---------------------------------------------------------------------------
hdr "VM — LISTENING PORTS"

port_check "nginx"          80
port_check "Admin backend"  8000
[ "$CHAT_ON"    = "true" ] && port_check "Chat backend"    8765 || warn "chat disabled — skipping"
[ "$JUKEBOX_ON" = "true" ] && port_check "Jukebox backend" 8766 || warn "jukebox disabled — skipping"
[ "$KIWIX_ON"   = "true" ] && port_check "Kiwix"           8888 || warn "kiwix disabled — skipping"

# ---------------------------------------------------------------------------
# VM — Key files
# ---------------------------------------------------------------------------
hdr "VM — KEY FILES"

file_check "Admin backend source"       /opt/hearth/admin/backend/main.py
file_check "Admin backend virtualenv"   /opt/hearth/admin/venv/bin/uvicorn
file_check "Admin env file"             /etc/hearth/admin.env
file_check "Hearth config"              /etc/hearth/hearth.yaml
file_check "Portal index"               /var/www/hearth/portal/index.html
file_check "Admin login page"           /var/www/hearth/admin/login.html
file_check "First-boot script"          /usr/local/sbin/hearth-first-boot.sh
file_check "Boot diagnostics script"    /usr/local/share/hearth/diag/diagnose-boot-dump.sh
[ "$CAPTIVE_ON" = "true" ] && \
    file_check "Captive portal page" /var/www/hearth/portal/captive-portal.html || \
    warn "captive_portal disabled — skipping"

# ---------------------------------------------------------------------------
# VM — nginx config
# ---------------------------------------------------------------------------
hdr "VM — NGINX CONFIG"

NGINX_TEST=$(vm "sudo nginx -t 2>&1")
if echo "$NGINX_TEST" | grep -q "syntax is ok"; then
    ok "nginx config syntax is ok"
else
    fail "nginx config syntax error:"
    echo "$NGINX_TEST" | sed 's/^/    /'
fi

# Check captive portal if block is present in rendered config
if [ "$CAPTIVE_ON" = "true" ]; then
    CAPTIVE_IN_CONF=$(vm "grep -c 'http_host' /etc/nginx/sites-available/hearth.conf 2>/dev/null || echo 0")
    if [ "${CAPTIVE_IN_CONF:-0}" -gt 0 ]; then
        ok "Captive portal if-block present in rendered nginx config"
    else
        fail "Captive portal if-block MISSING from rendered nginx config (re-provision?)"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
hdr "SUMMARY"
TOTAL=$((PASS + FAIL))
printf "  Passed: ${GRN}%d${RST}  Failed: ${RED}%d${RST}  Warned: ${YEL}%d${RST}  Total: %d\n" \
    "$PASS" "$FAIL" "$WARN" "$TOTAL"
echo ""
if [ "$FAIL" -gt 0 ]; then
    printf "${RED}${BOLD}%d test(s) failed.${RST}\n\n" "$FAIL"
    exit 1
fi
printf "${GRN}${BOLD}All tests passed.${RST}\n\n"
exit 0
