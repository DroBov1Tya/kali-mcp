FROM kalilinux/kali-rolling:latest

ARG DEBIAN_FRONTEND=noninteractive

# ── 1. Base ───────────────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        ca-certificates gnupg curl wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 2. Core CLI ───────────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        bash git vim nano tmux less jq unzip zip \
        build-essential libssl-dev libffi-dev \
        python3 python3-pip python3-venv python3-dev \
        iptables iproute2 net-tools procps iputils-ping \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 3. Network / recon ────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        nmap masscan \
        netcat-openbsd dnsutils whois \
        traceroute tcpdump \
        proxychains4 tor torsocks \
        redsocks \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 4. Web fuzzing & scanning ─────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        ffuf gobuster feroxbuster nikto \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 5. Exploitation ───────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        metasploit-framework \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 6. Post-exploitation / AD (best-effort) ───────────────────────────────────
RUN apt-get update -y && \
    { apt-get install -y --no-install-recommends impacket-scripts 2>/dev/null || true; } && \
    { apt-get install -y --no-install-recommends responder            2>/dev/null || true; } && \
    { apt-get install -y --no-install-recommends nxc                  2>/dev/null || true; } && \
    { apt-get install -y --no-install-recommends bloodhound-python    2>/dev/null || true; } && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 7. Password attacks ───────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        hashcat john hydra medusa \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 8. Wordlists ──────────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        seclists wordlists \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 9. nuclei (binary release, ARM64) ────────────────────────────────────────
RUN ARCH=arm64 && \
    VER=$(curl -fsSL https://api.github.com/repos/projectdiscovery/nuclei/releases/latest \
          | grep tag_name | cut -d'"' -f4 | tr -d v) && \
    curl -fsSL "https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_${VER}_linux_${ARCH}.zip" \
         -o /tmp/nuclei.zip && \
    unzip -q /tmp/nuclei.zip nuclei -d /usr/local/bin/ && \
    rm /tmp/nuclei.zip

# ── 10. Go-based tools ────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends golang-go && \
    export GOPATH=/tmp/gobuild && \
    go install github.com/projectdiscovery/katana/cmd/katana@latest && \
    go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest && \
    go install github.com/tomnomnom/anew@latest && \
    go install github.com/lc/gau/v2/cmd/gau@latest && \
    mv /tmp/gobuild/bin/* /usr/local/bin/ && \
    apt-get remove -y golang-go && apt-get autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/gobuild

# ── 11. rustscan ─────────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends cargo && \
    cargo install rustscan --locked && \
    mv /root/.cargo/bin/rustscan /usr/local/bin/rustscan && \
    apt-get remove -y cargo && apt-get autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /root/.cargo

# ── 12. Python uv ─────────────────────────────────────────────────────────────
RUN curl -LsSf "https://astral.sh/uv/install.sh" | UV_INSTALL_DIR=/usr/local/bin sh

# ── 13. proxychains config (→ tor 9050) ──────────────────────────────────────
RUN printf 'strict_chain\nproxy_dns\nquiet_mode\ntcp_read_time_out 15000\ntcp_connect_time_out 8000\n\n[ProxyList]\nsocks5  127.0.0.1 9050\n' \
    > /etc/proxychains4.conf

RUN mkdir -p /workspace /tools
WORKDIR /workspace

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
