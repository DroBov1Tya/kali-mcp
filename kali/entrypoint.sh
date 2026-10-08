#!/usr/bin/env bash
# Kill-switch: allow traffic only through VPN gateway, block everything else.
# VPN_GATEWAY can be set explicitly in .env or auto-detected from the default route.
set -euo pipefail

KILL_SWITCH="${KILL_SWITCH:-1}"
VPN_GATEWAY="${VPN_GATEWAY:-}"

resolve_gateway() {
    # Auto-detect: use the container's default route (set by Docker Desktop,
    # which already routes through the host's VPN on macOS)
    ip route 2>/dev/null | awk '/default/{print $3; exit}'
}

apply_kill_switch() {
    [[ "$KILL_SWITCH" != "1" ]] && { echo "[killswitch] disabled"; return; }

    if [[ -z "$VPN_GATEWAY" ]]; then
        VPN_GATEWAY=$(resolve_gateway)
    fi

    iptables -F OUTPUT 2>/dev/null || true
    iptables -F INPUT  2>/dev/null || true

    # Always allow loopback
    iptables -A OUTPUT -o lo -j ACCEPT
    iptables -A INPUT  -i lo -j ACCEPT

    # Allow established/related
    iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

    if [[ -n "$VPN_GATEWAY" ]]; then
        iptables -A OUTPUT -d "$VPN_GATEWAY" -j ACCEPT
        iptables -A INPUT  -s "$VPN_GATEWAY" -j ACCEPT
        iptables -P OUTPUT DROP
        iptables -P INPUT  DROP
        echo "[killswitch] ACTIVE — gateway=${VPN_GATEWAY}"
    else
        # No gateway found = VPN is down, block everything
        iptables -P OUTPUT DROP
        iptables -P INPUT  DROP
        echo "[killswitch] VPN DOWN — all outbound traffic BLOCKED"
    fi
}

apply_kill_switch
echo "[kali-mcp] ready"
exec "$@"
