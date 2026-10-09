#!/usr/bin/env bash
set -euo pipefail

# The gateway resolver forwards DNS over TCP through SOCKS5.
printf 'nameserver 127.0.0.1\noptions timeout:2 attempts:2\n' > /etc/resolv.conf

echo "[kali-mcp] root shell ready; network policy is owned by the gateway"
exec "$@"
