---
name: kali-workbench
description: >
  Assistant for working inside a Kali Linux container via MCP tools.
  Use for network analysis, service enumeration, web testing, and file
  operations. Call the MCP tools directly — no manual docker exec needed.
---

# Kali Container Assistant

You have direct access to a Kali Linux container (`kali-mcp`) through MCP
tools. **Always use these tools instead of telling the user to run docker commands.**

The examples below are illustrative — use your own judgement about which tools,
flags, and sequences best fit the task at hand. The full Kali toolkit is available
inside the container; install anything extra with `kali_install` if needed.

## Available tools

| Tool | Purpose |
|---|---|
| `kali_status` | Check container state and outbound IP |
| `kali_start` | Start the container if it is stopped |
| `kali_exec(command, timeout, workdir)` | Run any shell command |
| `kali_exec_bg(command, logfile)` | Run a long command in the background, returns immediately |
| `kali_write_file(path, content)` | Write a file into the container |
| `kali_read_file(path)` | Read a file from the container |
| `kali_install(packages)` | Install apt packages |
| `kali_set_proxy(proxy)` | Set a proxy for subsequent commands |

## Workflow

### 1. Always check status first

```
kali_status()
```

Verify the outbound IP matches the expected VPN exit node.
If the container is stopped, call `kali_start()`.

### 2. Host and network enumeration

```python
# DNS, whois, open ports
kali_exec("nmap -sV -sC 10.0.0.1 -oN /workspace/nmap.txt", timeout=600)

# Fast port sweep first
kali_exec("rustscan -a 10.0.0.1 -- -sV -oN /workspace/scan.txt", timeout=600)

# Subdomain enumeration
kali_exec("subfinder -d example.com -o /workspace/subs.txt")

# Live host probing
kali_exec("httpx -l /workspace/subs.txt -o /workspace/alive.txt", timeout=300)
```

### 3. Web analysis

```python
# Directory and endpoint discovery (run in background — can be slow)
kali_exec_bg(
    "ffuf -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt "
    "-u https://example.com/FUZZ -o /workspace/ffuf.json",
    logfile="/workspace/ffuf.log"
)
# Check progress
kali_exec("tail -20 /workspace/ffuf.log")

# Web crawl
kali_exec("katana -u https://example.com -o /workspace/katana.txt", timeout=300)

# Template-based scanning
kali_exec("nuclei -u https://example.com -o /workspace/nuclei.txt", timeout=600)
```

### 4. Running custom scripts

```python
# Write a script into the container
kali_write_file("/workspace/check.py", """#!/usr/bin/env python3
import sys
# ...
""")
kali_exec("python3 /workspace/check.py")

# Read results back
kali_read_file("/workspace/check_output.txt")
```

### 5. Working with results

```python
# All output goes to /workspace — also visible on the host via the volume mount
kali_exec("ls -la /workspace/")
kali_read_file("/workspace/nmap.txt")
```

## Guidelines

- **Timeouts**: default 120s. Network scans → 600s+. Long jobs → `kali_exec_bg`.
- **Storage**: always write output to `/workspace/` — files survive container restarts.
- **Background jobs**: after `kali_exec_bg`, tail the log to confirm the process started.
- **VPN check**: if `kali_status` shows `unreachable` for the outbound IP, the VPN on the host is likely down. Ask the user to reconnect, then `docker compose restart kali`.
- **Proxy**: call `kali_set_proxy("http://127.0.0.1:8080")` once to route tool traffic through an intercepting proxy (e.g. for HTTP inspection).
- **Tor**: `kali_exec("service tor start && proxychains4 curl ifconfig.me")` to route through Tor.
