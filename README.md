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

All TCP traffic from the container is transparently routed through the
system SOCKS5 proxy via redsocks. If the proxy goes down, connections
fail immediately -- no polling, no leak window.

Set PROXY_PORT in .env to your proxy port (default: 7897).
Set KILL_SWITCH=0 to disable (not recommended).

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
    KILL_SWITCH         1 to enable, 0 to disable (default: 1)
    KALI_WORKSPACE      host path mounted as /workspace (default: ./workspace)
    KALI_CONTAINER      container name (default: kali-mcp)
    KALI_EXEC_TIMEOUT   command timeout in seconds (default: 120)
    MCP_PORT            SSE server port (default: 8172)

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
