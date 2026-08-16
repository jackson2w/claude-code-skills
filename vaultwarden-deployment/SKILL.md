---
name: vaultwarden-deployment
description: This skill should be used when deploying Vaultwarden (self-hosted Bitwarden-compatible server) via Docker on a bare Debian/Ubuntu VPS or VM — not a Proxmox LXC/VM fleet host. Covers loopback-only binding, Tailscale Serve exposure, the admin-token hashing tool's TTY requirement, and locking down signups after the first account exists. Trigger phrases include "deploy vaultwarden", "vaultwarden docker", "vaultwarden admin token", "vaultwarden hash preset", "No such device or address vaultwarden", "SIGNUPS_ALLOWED", "vaultwarden signups disabled verify".
---

# Vaultwarden deployment (Docker, single-user personal instance)

Built and verified 2026-08-15 on a Vultr VPS (`dfw`) as the secrets store for a broader
multi-service box. Docker is fine here specifically because this is a personal/single-purpose
VPS, not part of the homelab's Proxmox fleet (where Docker is banned outside LXCs/VMs — see
`proxmox-node-systemd-service` for the native-systemd alternative used on that fleet instead).

## Loopback-only bind — the port mapping syntax matters

Docker's short-form `-p 8080:80` (or Compose `ports: - '8080:80'`) publishes to `0.0.0.0` on the
host, not just loopback — this is true regardless of what firewall rules exist elsewhere, and
`docker ps` looks identical either way. Always bind explicitly:

```bash
docker run -d \
  --name vaultwarden \
  --restart unless-stopped \
  --env-file /root/.config/vaultwarden-admin.env \
  -e SIGNUPS_ALLOWED=false \
  -e WEBSOCKET_ENABLED=true \
  -v /opt/vaultwarden/data:/data \
  -p 127.0.0.1:8080:80 \
  vaultwarden/server:latest
```

Verify with `ss -tlnp | grep 8080` — should show `127.0.0.1:8080`, never `0.0.0.0:8080` or `*:8080`.

## Expose via Tailscale Serve on a dedicated, non-default port

If the box will eventually host other services too, don't claim port 443 for Vaultwarden — leave
that free for whatever ends up being the box's primary/default service, and give Vaultwarden its
own:

```bash
tailscale serve --bg --https=8443 http://127.0.0.1:8080
```

## The `vaultwarden hash` admin-token tool needs a REAL TTY — can't be scripted

Vaultwarden ships `/vaultwarden hash --preset owasp|bitwarden` to generate a properly-hashed
Argon2id `ADMIN_TOKEN` (the documented best practice over a plaintext token). It reads the
password via a library that opens `/dev/tty` directly, bypassing piped stdin entirely — running
it non-interactively (`echo "$TOKEN" | docker run --rm -i vaultwarden/server /vaultwarden hash
...`) fails with:

```
thread 'main' panicked at src/main.rs:...: called `Result::unwrap()` on an `Err` value:
Os { code: 6, kind: Uncategorized, message: "No such device or address" }
```

No `-t`/`-it` combination fixes this over a non-interactive SSH command — it needs an actual
attached terminal. For a personal, tailnet-only, loopback-bound instance (not internet-facing),
the pragmatic trade-off is a strong random **plaintext** `ADMIN_TOKEN` instead, generated and
stored server-side in one step so it never transits a chat transcript or shell history:

```bash
TOKEN=$(openssl rand -base64 48 | tr -d '\n')
printf 'ADMIN_TOKEN=%s\n' "$TOKEN" | sudo tee /root/.config/vaultwarden-admin.env >/dev/null
sudo chmod 600 /root/.config/vaultwarden-admin.env
```

If the instance will ever be more broadly reachable, redo this properly (via an actual
interactive terminal session on the host) rather than carrying the plaintext token forward.

## Signups: allow for first account, then lock down

Leave `SIGNUPS_ALLOWED=true` (or default) until the intended owner has created their account
through the web UI — that's a personal master-password choice, never something to script or
have an assistant do on someone's behalf. Once the account exists, recreate the container (env
vars only take effect at container creation, not via a plain restart) with signups closed:

```bash
docker stop vaultwarden && docker rm vaultwarden
docker run -d ... -e SIGNUPS_ALLOWED=false ... vaultwarden/server:latest   # same flags as above
```

Verify the flag actually took — Vaultwarden's public `/api/config` endpoint does **not** expose
signup status, so checking it there proves nothing. Check the container's own environment
instead, and confirm the existing account's data survived the recreate:

```bash
docker exec vaultwarden printenv SIGNUPS_ALLOWED     # expect: false
curl -sk -o /dev/null -w '%{http_code}\n' https://<tailnet-url>/   # expect: 200, login page loads
```

## Verification checklist

- `ss -tlnp` shows `127.0.0.1:8080` only, never a wildcard bind
- Tailscale Serve URL loads (may take ~30-60s on first request — container health check
  cold-start, not a failure)
- Direct connection to the tailnet IP on the container's raw port (bypassing the Serve proxy)
  fails — confirms the only path in is through Serve, not a second exposed route
- Public IP has no route to the port at all
- `SIGNUPS_ALLOWED=false` confirmed via container env after the owner's account exists
