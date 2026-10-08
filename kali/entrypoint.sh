#!/usr/bin/env bash
# Kill-switch via redsocks: all TCP traffic is transparently routed through
# Clash Verge's SOCKS5 proxy on the host (host.docker.internal:CLASH_PROXY_PORT).
# If Clash is down → proxy unreachable → connections fail immediately (0ms delay).
set -euo pipefail

KILL_SWITCH="${KILL_SWITCH:-1}"
PROXY_HOST="${PROXY_HOST:-host.docker.internal}"
PROXY_PORT="${PROXY_PORT:-7897}"
REDSOCKS_PORT=12345

# ── redsocks config ───────────────────────────────────────────────────────────

start_redsocks() {
    cat > /etc/redsocks.conf << EOF
base {
    log_debug = off;
    log_info  = on;
    log       = "stderr";
    daemon    = off;
    redirector = iptables;
}

redsocks {
    local_ip   = 127.0.0.1;
    local_port = ${REDSOCKS_PORT};
    ip         = ${PROXY_HOST};
    port       = ${PROXY_PORT};
    type       = socks5;
}
EOF
    redsocks -c /etc/redsocks.conf &
    sleep 0.5
    echo "[killswitch] redsocks started → ${PROXY_HOST}:${PROXY_PORT}"
}

# ── iptables: redirect all outbound TCP through redsocks ─────────────────────

apply_iptables() {
    # Nat table — REDSOCKS chain
    iptables -t nat -N REDSOCKS 2>/dev/null || iptables -t nat -F REDSOCKS

    # Skip private / loopback / link-local ranges
    iptables -t nat -A REDSOCKS -d 0.0.0.0/8      -j RETURN
    iptables -t nat -A REDSOCKS -d 10.0.0.0/8     -j RETURN
    iptables -t nat -A REDSOCKS -d 127.0.0.0/8    -j RETURN
    iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
    iptables -t nat -A REDSOCKS -d 172.16.0.0/12  -j RETURN
    iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
    iptables -t nat -A REDSOCKS -d 224.0.0.0/4    -j RETURN
    iptables -t nat -A REDSOCKS -d 240.0.0.0/4    -j RETURN

    # Redirect all remaining TCP to redsocks listener
    iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports ${REDSOCKS_PORT}

    # Apply to all outbound TCP
    iptables -t nat -A OUTPUT -p tcp -j REDSOCKS

    echo "[killswitch] iptables NAT rules applied — all TCP → redsocks"
}

# ── startup ───────────────────────────────────────────────────────────────────

if [[ "$KILL_SWITCH" != "1" ]]; then
    echo "[killswitch] disabled"
    exec "$@"
fi

start_redsocks
apply_iptables

echo "[kali-mcp] ready — traffic via ${PROXY_HOST}:${PROXY_PORT}"
exec "$@"
