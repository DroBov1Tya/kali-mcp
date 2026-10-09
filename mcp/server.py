#!/usr/bin/env python3
"""
kali-shell-mcp — MCP server exposing a Kali Linux container to AI agents.

Transport: stdio.
Backend:   docker exec into a running kali-mcp container.

Tools (all callable directly by agents, no manual docker exec needed):
  kali_exec        Run any shell command inside the container.
  kali_exec_bg     Start a long-running command in the background (returns PID).
  kali_write_file  Write a text file directly into the container.
  kali_read_file   Read a text file from the container.
  kali_install     Install apt packages.
  kali_start       Ensure the container is running (start if stopped).
  kali_status      Report container state and network status.

Proxy: optional. If KALI_PROXY env or kali_set_proxy is set, proxy env vars
are injected. Without an explicit command proxy, the external gateway handles
traffic routing. Kali cannot change the gateway's firewall.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("kali-shell-mcp")

from mcp.server.fastmcp import FastMCP


def _load_dotenv() -> dict[str, str]:
    """Load .env from the project root (one level up). Does not override existing env vars."""
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_file = os.path.abspath(env_file)
    values: dict[str, str] = {}
    if not os.path.exists(env_file):
        return values
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            values[key] = val
            if key not in os.environ:
                os.environ[key] = val
    return values


def _resolve_transport() -> str:
    """Determine transport mode: sse (docker) or stdio (local).

    Resolution order:
      1. MCP_TRANSPORT env var (explicit override)
      2. COMPOSE_PROFILES env / .env: if contains 'mcp' → sse
      3. Interactive TTY: prompt the user to choose
      4. Default: stdio
    """
    if os.environ.get("MCP_TRANSPORT"):
        return os.environ["MCP_TRANSPORT"]

    profiles = os.environ.get("COMPOSE_PROFILES", "")
    if "mcp" in profiles:
        return "sse"

    # Running interactively — ask the user
    if sys.stdin.isatty() and sys.stderr.isatty():
        sys.stderr.write(
            "\nMCP transport not configured in .env (COMPOSE_PROFILES).\n"
            "  [1] stdio  — run locally, Claude Code spawns this process (default)\n"
            "  [2] sse    — run as HTTP server, docker compose manages the container\n"
            "Choice [1/2, default=1]: "
        )
        sys.stderr.flush()
        choice = sys.stdin.readline().strip()
        if choice == "2":
            return "sse"

    return "stdio"


_load_dotenv()

CONTAINER = os.environ.get("KALI_CONTAINER", "kali-mcp")

def _autostart_kali() -> None:
    """Start the kali container if it exists but is stopped. Skipped inside Docker."""
    if os.path.exists("/.dockerenv"):
        return
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            log.info("autostart: container '%s' not found, skipping", CONTAINER)
            return
        if proc.stdout.strip() == "true":
            log.info("autostart: container '%s' already running", CONTAINER)
            return
        subprocess.Popen(
            ["docker", "start", CONTAINER],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log.info("autostart: starting container '%s'", CONTAINER)
    except FileNotFoundError:
        log.warning("autostart: docker binary not found, skipping")
IMAGE = os.environ.get("KALI_IMAGE", "kali-mcp:latest")
DEFAULT_TIMEOUT = int(os.environ.get("KALI_EXEC_TIMEOUT", "120"))
WORKSPACE_HOST = os.path.expanduser(os.environ.get("KALI_WORKSPACE", "~/kali-workspace"))

mcp = FastMCP(
    "kali-shell",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8172")),
)

_env_proxy: str | None = os.environ.get("KALI_PROXY", "").strip() or None
_session_proxy: str | None = _env_proxy


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _proxy_env(proxy: str) -> str:
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    vars_ = (
        f"http_proxy={proxy} https_proxy={proxy} "
        f"HTTP_PROXY={proxy} HTTPS_PROXY={proxy} "
        f"all_proxy={proxy} ALL_PROXY={proxy} "
        f"no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1"
    )
    return f"export {vars_}; "


async def _exec(
    command: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str = "/workspace",
    as_root: bool = True,
    proxy: str | None = None,
    interactive: bool = False,
) -> str:
    """Core docker exec wrapper. Returns formatted output string."""
    resolved_proxy = (proxy or "").strip() or _session_proxy
    if resolved_proxy:
        command = _proxy_env(resolved_proxy) + command

    argv = ["docker", "exec"]
    if interactive:
        argv += ["-it"]
    else:
        argv += ["-i"]
    argv += ["-w", workdir]
    if as_root:
        argv += ["-u", "0"]
    argv += [CONTAINER, "sh", "-c", command]

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return "ERROR: 'docker' binary not found on PATH."
    except Exception as exc:
        return f"ERROR: spawn failed: {exc!r}"

    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"TIMEOUT after {timeout}s — command was killed."

    text = out.decode("utf-8", errors="replace") if out else ""
    rc = proc.returncode
    sep = "-" * 40
    return f"exit={rc}\n{sep}\n{text}"


async def _container_running() -> bool:
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect", "-f", "{{.State.Running}}", CONTAINER,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode().strip() == "true"


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def kali_exec(
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str = "/workspace",
    as_root: bool = True,
    proxy: str | None = None,
) -> str:
    """Run a shell command inside the Kali container.

    Use this instead of 'docker exec' — agents should call this tool directly.
    Supports pipes, &&, subshells, redirects — anything sh -c accepts.
    Output (stdout + stderr combined) and exit code are returned.

    Args:
        command:  shell command string, e.g. "nmap -sV 10.0.0.1 -oN /workspace/scan.txt"
        timeout:  seconds before the command is killed (default 120; use more for slow scans)
        workdir:  working directory inside the container (default /workspace)
        as_root:  run as root uid 0 (default True)
        proxy:    optional proxy URL, e.g. http://127.0.0.1:8080
    """
    if not await _container_running():
        return (
            f"ERROR: container '{CONTAINER}' is not running.\n"
            "Call kali_start first, or run: docker compose up -d gateway kali"
        )
    return await _exec(command, timeout=timeout, workdir=workdir, as_root=as_root, proxy=proxy)


@mcp.tool()
async def kali_exec_bg(
    command: str,
    workdir: str = "/workspace",
    logfile: str | None = None,
) -> str:
    """Start a long-running command in the background inside the container.

    Returns immediately with the PID. Stdout/stderr go to logfile (or
    /workspace/bg_<name>.log by default). Use kali_exec("cat <logfile>") to
    tail the output later.

    Args:
        command:  shell command to run in the background
        workdir:  working directory inside the container (default /workspace)
        logfile:  path inside container for output (auto-generated if omitted)
    """
    if not await _container_running():
        return f"ERROR: container '{CONTAINER}' is not running. Call kali_start first."

    safe_name = command.split()[0].replace("/", "_")[:20]
    log_path = logfile or f"/workspace/bg_{safe_name}.log"
    wrapped = f"nohup sh -c {command!r} > {log_path} 2>&1 & echo $!"

    result = await _exec(wrapped, workdir=workdir, timeout=10)
    pid_line = result.split("\n")[-1].strip()
    return f"Started in background. PID={pid_line}\nLog: {log_path}\nTail with: kali_exec(\"tail -f {log_path}\")"


@mcp.tool()
async def kali_write_file(path: str, content: str) -> str:
    """Write a text file directly into the container filesystem.

    Useful for dropping scripts, configs, wordlists, payloads, etc.
    Parent directories are created automatically.

    Args:
        path:    absolute path inside the container, e.g. /workspace/exploit.py
        content: file content as a string
    """
    if not await _container_running():
        return f"ERROR: container '{CONTAINER}' is not running. Call kali_start first."

    # Pipe content via stdin to avoid shell quoting issues with arbitrary content
    argv = [
        "docker", "exec", "-i", "-u", "0", CONTAINER,
        "sh", "-c", f"mkdir -p $(dirname {path!r}) && cat > {path!r}",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(
            proc.communicate(input=content.encode()),
            timeout=30,
        )
    except asyncio.TimeoutError:
        return "TIMEOUT: write_file timed out after 30s."
    except Exception as exc:
        return f"ERROR: {exc!r}"

    if proc.returncode != 0:
        return f"ERROR (exit={proc.returncode}): {out.decode(errors='replace')}"
    return f"OK: wrote {len(content)} bytes to {path}"


@mcp.tool()
async def kali_read_file(path: str, max_bytes: int = 102400) -> str:
    """Read a text file from the container filesystem.

    Args:
        path:      absolute path inside the container
        max_bytes: truncate output after this many bytes (default 100 KB)
    """
    if not await _container_running():
        return f"ERROR: container '{CONTAINER}' is not running. Call kali_start first."

    result = await _exec(f"cat {path!r}", timeout=15)
    if len(result) > max_bytes:
        result = result[:max_bytes] + f"\n... [truncated at {max_bytes} bytes]"
    return result


@mcp.tool()
async def kali_install(
    packages: str,
    update_first: bool = True,
    proxy: str | None = None,
) -> str:
    """Install apt packages inside the Kali container.

    Args:
        packages:     space-separated package names, e.g. "sqlmap john"
        update_first: run apt-get update before installing (default True)
        proxy:        optional proxy URL
    """
    if not await _container_running():
        return f"ERROR: container '{CONTAINER}' is not running. Call kali_start first."

    cmd = ""
    if update_first:
        cmd += "apt-get update -y && "
    cmd += f"DEBIAN_FRONTEND=noninteractive apt-get install -y {packages}"
    return await _exec(cmd, timeout=600, as_root=True, proxy=proxy)


@mcp.tool()
async def kali_start() -> str:
    """Ensure the kali-mcp container is running.

    If it already runs — reports OK.
    If it exists but is stopped — starts it.
    If it doesn't exist — returns Compose setup instructions.
    """
    # Check if container exists at all
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect", "-f", "{{.State.Status}}", CONTAINER,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()

    if proc.returncode != 0:
        return (
            f"Container '{CONTAINER}' does not exist.\n"
            "Build and start it with: docker compose up -d --build gateway kali\n"
        )

    status = out.decode().strip()
    if status == "running":
        return f"OK: container '{CONTAINER}' is already running."

    # Try to start it
    start = await asyncio.create_subprocess_exec(
        "docker", "start", CONTAINER,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    s_out, _ = await start.communicate()
    if start.returncode == 0:
        return f"OK: container '{CONTAINER}' started (was: {status})."
    return f"ERROR starting container: {s_out.decode(errors='replace')}"


@mcp.tool()
async def kali_status() -> str:
    """Report container state and basic network info.

    Call this first to understand the environment before running commands.
    """
    # Container state
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect",
        "-f", "{{.State.Status}}|{{.State.Running}}|{{.State.StartedAt}}",
        CONTAINER,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()

    if proc.returncode != 0:
        return (
            f"Container '{CONTAINER}' not found.\n"
            "Run: docker compose up -d --build gateway kali"
        )

    parts = out.decode().strip().split("|")
    state, running, started_at = (parts + ["?", "?", "?"])[:3]

    lines = [
        f"container : {CONTAINER}",
        f"state     : {state}",
        f"running   : {running}",
        f"started   : {started_at}",
        f"proxy     : {_session_proxy or 'not set (external SOCKS5 gateway handles routing)'}",
    ]

    if running == "true":
        # Quick network check inside container
        net = await _exec(
            "curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo 'unreachable'",
            timeout=10,
        )
        ext_ip = net.split("\n")[-1].strip() if "\n" in net else net.strip()
        lines.append(f"external IP (via container): {ext_ip}")
        lines.append("")
        lines.append("Ready. Use kali_exec to run commands.")
    else:
        lines.append("")
        lines.append("WARN: container not running. Call kali_start or run: docker compose up -d gateway kali")

    return "\n".join(lines)


@mcp.tool()
async def kali_set_proxy(proxy: str | None = None) -> str:
    """Set or clear the session-wide proxy injected into kali_exec/kali_install.

    Args:
        proxy: proxy URL, e.g. http://127.0.0.1:8080; omit to clear
    """
    global _session_proxy
    if proxy:
        p = proxy.strip()
        if "://" not in p:
            p = f"http://{p}"
        _session_proxy = p
        return f"OK: session proxy set to {p}"
    _session_proxy = _env_proxy
    return (
        f"OK: cleared. Using KALI_PROXY env default: {_env_proxy}"
        if _env_proxy else
        "OK: cleared command proxy. External SOCKS5 gateway still routes traffic."
    )


def main() -> None:
    _autostart_kali()
    transport = _resolve_transport()
    log.info("kali-shell-mcp starting: container=%s transport=%s", CONTAINER, transport)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
