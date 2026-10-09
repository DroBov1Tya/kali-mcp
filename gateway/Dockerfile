FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

RUN apt-get update && apt-get install -y --no-install-recommends \
        iptables redsocks unbound procps tini \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh healthcheck.sh /
RUN chmod 755 /entrypoint.sh /healthcheck.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
