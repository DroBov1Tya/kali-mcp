#!/usr/bin/env bash
set -euo pipefail
test -f /run/gateway-ready
pgrep -x redsocks >/dev/null
pgrep -x unbound >/dev/null
iptables -w -C OUTPUT -d 127.0.0.11/32 -j DROP
iptables -w -C OUTPUT -d 127.0.0.1/32 -j ACCEPT
ip6tables -w -S OUTPUT | head -n 1 | grep -qx -- '-P OUTPUT DROP'
