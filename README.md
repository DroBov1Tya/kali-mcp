# kali-mcp

Kali Linux container with an MCP server for AI agents.
Agents call tools directly -- no manual docker exec needed.

## Requirements

- Docker Desktop (arm64 or amd64)
- Python 3.10+ with uv
- A SOCKS5 proxy (system proxy / VPN client with proxy mode)

## Setup

    cp .env.example .env
    # edit .env: set PROXY_PORT to your SOCKS5 proxy port
    docker compose up -d --build

## Kill-switch

The 'gateway' service owns the network namespace and its firewall. Kali shares
that namespace but runs without 'NET_ADMIN' and 'NET_RAW', with
'no-new-privileges'. Commands still run as root: package installation and file
operations work, but changing routes, interfaces or firewall rules is denied,
including through 'docker exec -u 0'.

Public IPv4 TCP is transparently routed through the configured SOCKS5 endpoint
via redsocks. Local DNS uses Unbound, forwarding over TCP through the same proxy.
Direct private/link-local connections, Docker's embedded DNS, outbound UDP,
IPv6 and unsolicited inbound network connections are blocked. Loopback remains
available for local services. Only the configured SOCKS5 endpoint is allowed as
a direct external connection. If the proxy or gateway daemons fail, there is
no fallback to direct egress.

Set 'PROXY_PORT' in '.env' (default: 7897). 'PROXY_HOST' defaults to
'host.docker.internal'; custom values must be IPv4 literals or '/etc/hosts'
entries in the gateway. 'DNS_UPSTREAM' defaults to '1.1.1.1'.
'KILL_SWITCH=0' is rejected; changing policy requires access to the Compose
configuration or Docker daemon outside Kali.

Raw/SYN scans and packet capture are unavailable. For nmap use '-sT -Pn'.
SOCKS5 controls which remote destinations are reachable: local firewall rules
do not restrict destinations requested explicitly through SOCKS5. Apply target
ACLs on the proxy if needed. The shared namespace also shares loopback ports;
this is isolation from network administration, not isolation of local services.
Do not mount the Docker socket or host credentials into Kali.

After upgrading, recreate both services together:

    docker compose up -d --build --force-recreate gateway kali

'kali_start' can start an existing container, but cannot migrate an old container
to this network topology. Recreate Kali whenever the gateway is replaced.

## MCP server modes

### stdio (default)

Claude Code spawns the server as a subprocess.

Config in ~/.claude.json or claude_desktop_config.json:

    "kali-shell": {
      "command": "uv",
      "args": ["run", "python", "-u", "server.py"],
      "cwd": "/path/to/kali-mcp/mcp"
    }

### SSE (docker container)

Set COMPOSE_PROFILES=mcp in .env, then:

    docker compose up -d

Claude Code connects via HTTP:

    "kali-shell": {
      "url": "http://localhost:8172/sse"
    }

## Available MCP tools

    kali_status         -- container state and external IP
    kali_start          -- start container if stopped
    kali_exec           -- run any shell command
    kali_exec_bg        -- run a long command in the background
    kali_write_file     -- write a file into the container
    kali_read_file      -- read a file from the container
    kali_install        -- install apt packages
    kali_set_proxy      -- set an HTTP/SOCKS proxy for commands

## Configuration (.env)

    PLATFORM            linux/arm64 or linux/amd64
    PROXY_PORT          SOCKS5 proxy port (default: 7897)
    PROXY_HOST          SOCKS5 IPv4 or gateway /etc/hosts entry (default: host.docker.internal)
    DNS_UPSTREAM        upstream IPv4 resolver, reached through SOCKS5 (default: 1.1.1.1)
    KILL_SWITCH         must be 1; unrestricted mode is rejected
    KALI_WORKSPACE      host path mounted as /workspace (default: ./workspace)
    KALI_CONTAINER      container name (default: kali-mcp)
    KALI_EXEC_TIMEOUT   command timeout in seconds (default: 120)
    MCP_PORT            SSE server port (default: 8172)
    COMPOSE_PROFILES    set to "mcp" to run MCP as a container

## Toolkit included

    Network:      nmap, masscan, rustscan, netcat, tcpdump, traceroute
    Web:          ffuf, gobuster, feroxbuster, katana, httpx, nuclei
    Recon:        subfinder, dnsx, gau, anew
    Exploit:      metasploit-framework
    Post-expl:    impacket, responder, nxc, bloodhound-python
    Passwords:    hashcat, john, hydra, medusa
    Wordlists:    seclists, wordlists
    Proxy/Anon:   proxychains4, tor, torsocks, redsocks
    Python:       uv
