#!/usr/bin/env bash
set -euo pipefail

# Kali shares only this network namespace, not processes/files/capabilities.
PROXY_HOST="${PROXY_HOST:-host.docker.internal}"
PROXY_PORT="${PROXY_PORT:-7897}"
DNS_UPSTREAM="${DNS_UPSTREAM:-1.1.1.1}"

# Install restrictive policies before configuration/startup. Existing rules
# stay effective on restart until their replacements are committed.
for tool in iptables ip6tables; do
    "$tool" -w -P INPUT DROP
    "$tool" -w -P OUTPUT DROP
    "$tool" -w -P FORWARD DROP
done
rm -f /run/gateway-ready

if [[ "${KILL_SWITCH:-1}" != 1 ]]; then
    echo "[gateway] KILL_SWITCH must be 1; unrestricted mode is unsupported" >&2
    exit 1
fi
if [[ ! "$PROXY_PORT" =~ ^[0-9]{1,5}$ ]] || (( 10#$PROXY_PORT < 1 || 10#$PROXY_PORT > 65535 )); then
    echo "[gateway] invalid PROXY_PORT" >&2
    exit 1
fi

ipv4_valid() {
    local value="$1" octet
    [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
    local -a octets
    IFS=. read -r -a octets <<< "$value"
    for octet in "${octets[@]}"; do
        (( 10#$octet <= 255 )) || return 1
    done
}

# Resolve only a literal or /etc/hosts entry. No bootstrap DNS exception is
# exposed to Kali. Compose supplies host.docker.internal through extra_hosts.
if ipv4_valid "$PROXY_HOST"; then
    PROXY_IP="$PROXY_HOST"
else
    PROXY_IP=$(awk -v host="$PROXY_HOST" '
        { for (i=2; i<=NF; i++) if ($i == host && $1 ~ /^[0-9.]+$/) { print $1; exit } }
    ' /etc/hosts)
fi
if ! ipv4_valid "$PROXY_IP" || ! ipv4_valid "$DNS_UPSTREAM"; then
    echo "[gateway] PROXY_HOST must be IPv4 or in /etc/hosts; DNS_UPSTREAM must be IPv4" >&2
    exit 1
fi
case "$PROXY_IP" in
    0.*|127.*|169.254.*) echo "[gateway] invalid proxy address" >&2; exit 1 ;;
esac
case "$DNS_UPSTREAM" in
    0.*|10.*|127.*|169.254.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*)
        echo "[gateway] DNS_UPSTREAM must be public IPv4" >&2; exit 1 ;;
esac

# Only SOCKS5 endpoint traffic can leave directly. Block Docker's embedded
# resolver even after its loopback DNAT changes the destination port.
# TCP-only conntrack replies avoid ICMP/UDP exceptions.
iptables-restore -w <<EOF
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT DROP [0:0]
-A INPUT -s 127.0.0.11/32 -j DROP
-A INPUT -i lo -j ACCEPT
-A INPUT -p tcp -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
-A OUTPUT -d 127.0.0.11/32 -j DROP
-A OUTPUT -d 127.0.0.1/32 -j ACCEPT
-A OUTPUT -d ${PROXY_IP}/32 -p tcp --dport ${PROXY_PORT} -j ACCEPT
-A OUTPUT -p tcp -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
:REDSOCKS - [0:0]
-A OUTPUT -p tcp -j REDSOCKS
-A REDSOCKS -d ${PROXY_IP}/32 -p tcp --dport ${PROXY_PORT} -j RETURN
-A REDSOCKS -d 0.0.0.0/8 -j RETURN
-A REDSOCKS -d 10.0.0.0/8 -j RETURN
-A REDSOCKS -d 100.64.0.0/10 -j RETURN
-A REDSOCKS -d 127.0.0.0/8 -j RETURN
-A REDSOCKS -d 169.254.0.0/16 -j RETURN
-A REDSOCKS -d 172.16.0.0/12 -j RETURN
-A REDSOCKS -d 192.168.0.0/16 -j RETURN
-A REDSOCKS -d 224.0.0.0/4 -j RETURN
-A REDSOCKS -d 240.0.0.0/4 -j RETURN
-A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
COMMIT
EOF

ip6tables-restore -w <<'EOF'
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT DROP [0:0]
COMMIT
EOF

cat > /run/redsocks.conf <<EOF
base {
    log_debug = off;
    log_info = off;
    log = "stderr";
    daemon = off;
    redirector = iptables;
}
redsocks {
    local_ip = 127.0.0.1;
    local_port = 12345;
    ip = ${PROXY_IP};
    port = ${PROXY_PORT};
    type = socks5;
}
EOF

cat > /run/unbound.conf <<EOF
server:
    interface: 127.0.0.1
    port: 53
    access-control: 127.0.0.0/8 allow
    do-ip6: no
    username: "unbound"
    chroot: ""
    directory: "/run"
    pidfile: ""
    use-syslog: no
    logfile: ""
    module-config: "iterator"
    auto-trust-anchor-file: ""
remote-control:
    control-enable: no
forward-zone:
    name: "."
    forward-addr: ${DNS_UPSTREAM}
    forward-tcp-upstream: yes
    forward-first: no
EOF

unbound-checkconf /run/unbound.conf
# The relay does not need root or NET_ADMIN. Local clients can reach it, so
# discard root credentials before parsing their traffic.
setpriv --reuid=nobody --regid=nogroup --clear-groups --no-new-privs \
    redsocks -c /run/redsocks.conf &
redsocks_pid=$!
unbound -d -c /run/unbound.conf &
unbound_pid=$!

cleanup() {
    rm -f /run/gateway-ready
    kill "$redsocks_pid" "$unbound_pid" 2>/dev/null || true
    wait "$redsocks_pid" "$unbound_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT

# Health means policy and listeners are ready; proxy availability is not
# required. An offline proxy leaves egress closed.
for (( attempt=0; attempt<50; attempt++ )); do
    if (echo > /dev/tcp/127.0.0.1/12345) 2>/dev/null && \
       (echo > /dev/tcp/127.0.0.1/53) 2>/dev/null; then
        touch /run/gateway-ready
        break
    fi
    kill -0 "$redsocks_pid" "$unbound_pid"
    sleep 0.1
done
[[ -f /run/gateway-ready ]]
echo "[gateway] ready; TCP/DNS via SOCKS5 ${PROXY_IP}:${PROXY_PORT}; direct UDP/IPv6 blocked"

# Firewall rules persist in the shared namespace after a daemon/container
# exits. Restart both daemons if either fails.
wait -n "$redsocks_pid" "$unbound_pid"
exit 1
