---
name: paperless-ngx-bare-metal
description: This skill should be used when installing, upgrading, or troubleshooting a Paperless-ngx deployment via its bare-metal (non-Docker) release tarball rather than Docker Compose — especially inside a Proxmox LXC. Trigger phrases include "paperless-ngx bare metal", "paperless-ngx without docker", "pip install requirements.txt paperless", "granian paperless", "PAPERLESS_BIND_ADDR", "mysqlclient pkg-config error", "liblept", "paperless-ngx tarball structure", "paperless systemd service", "paperless-webserver.service".
---

# Paperless-ngx bare-metal (non-Docker) install

Covers the gap between Paperless-ngx's official bare-metal docs and what actually happens on a
fresh Debian 13 install — first hit 2026-07-18 building a home document-management LXC
(`paperless`, VMID 144, in the `homelab` repo) with no Docker (Gotenberg is Docker-only and has
no bare-metal alternative at all, but that only matters if Office-document conversion is
needed — pure PDF/scan use, the common "paperless" use case, doesn't need it).

## The release tarball's actual layout — don't assume a versioned top-level dir

`paperless-ngx-v<version>.tar.xz` extracts to a top-level directory literally named
`paperless-ngx/` — **not** version-named. `requirements.txt` sits at that root; `manage.py` is
under `src/` inside it (i.e. `paperless-ngx/src/manage.py`). Confirmed by inspecting the actual
tarball contents (`tar -tJf`), not assumed from docs, which don't spell this out.

If you want side-by-side versions (so a future upgrade doesn't clobber a running install),
extract with `--strip-components=1` into a version-named directory of your own choosing, then
symlink a stable path (e.g. `/opt/paperless/src`) to it:

```bash
mkdir -p /opt/paperless-ngx-2.20.15
tar -xJf paperless-ngx-v2.20.15.tar.xz -C /opt/paperless-ngx-2.20.15 --strip-components=1
ln -sfn /opt/paperless-ngx-2.20.15 /opt/paperless/src
```

With Ansible's `unarchive` module, `extra_opts: ["--strip-components=1"]` does the same thing —
`dest` must already exist as a directory first (unarchive doesn't create it).

## Missing system package: `mysqlclient` needs its dev headers even when using SQLite

The bare-metal docs' package list is incomplete. `requirements.txt` is a single lockfile that
unconditionally includes `mysqlclient` regardless of which `PAPERLESS_DBENGINE` you actually
use — so `pip install -r requirements.txt` fails during `mysqlclient`'s build step with:

```
Trying pkg-config --exists mysqlclient / mariadb / libmariadb / perconaserverclient
...
Exception: Can not find valid pkg-config name.
```

Fix: install `default-libmysqlclient-dev` (the Debian metapackage) even for a pure-SQLite
deployment. This is easy to miss since nothing about a SQLite-only setup suggests you'd need
MySQL client headers.

## Debian 13 package-name drift from older guides

Some bare-metal walkthroughs (and even parts of the current docs) reference package names that
don't exist on Debian 13 (`trixie`). Confirmed via `apt-cache search` rather than assumed:

- Leptonica dev/runtime library is `libleptonica6`, **not** `liblept5`.

If `apt install <package>` 404s on a name from a guide, search first (`apt-cache search
<library-name>`) rather than assuming the package was removed — it's very likely just renamed.

## The webserver is Granian (ASGI), not Gunicorn

Current Paperless-ngx (2.x) uses **Granian** as its production ASGI server
(`granian --interface asginl --ws --loop uvloop paperless.asgi:application`), pulled in via
`requirements.txt` alongside `uvloop`. Older guides/assumptions referencing Gunicorn are stale.
Get the real, current systemd unit templates from the upstream repo before writing your own —
they live at `scripts/paperless-webserver.service`, `paperless-consumer.service`,
`paperless-scheduler.service`, `paperless-task-queue.service` (not under a `systemd/`
subdirectory, despite what the name might suggest) — `gh api
repos/paperless-ngx/paperless-ngx/contents/scripts` to list them, fetch with `--jq '.content' |
base64 -d`.

**`PAPERLESS_BIND_ADDR` defaults to `::`** (all interfaces, IPv4+IPv6) — confirmed directly
against the upstream unit template's `GRANIAN_HOST` handling, not assumed. Same "binds
everywhere by default" gotcha as Next.js/Jellyfin elsewhere in this homelab — set it explicitly
to `127.0.0.1` if the plan is to front it with Tailscale Serve (or any reverse proxy) and verify
with a negative check (confirm the plain LAN IP:port is actually refused), not just that the
proxied hostname works.

The systemd templates' `Requires=redis.service` may not match your distro's actual unit name —
Debian's `redis-server` package installs as `redis-server.service`; don't assume a `redis.service`
alias exists, use the real name.

## `PAPERLESS_URL` is the one env var to set, not three

Setting `PAPERLESS_URL=https://your-hostname` configures `ALLOWED_HOSTS`, `CORS_ALLOWED_HOSTS`,
and `CSRF_TRUSTED_ORIGINS` together — simpler and less error-prone than setting Django's usual
three separate variables by hand, and the CSRF piece specifically matters (Django 4+ requires
`CSRF_TRUSTED_ORIGINS` for POST through any reverse proxy, including Tailscale Serve).

## `sudo` may not exist on a minimal LXC template

If your automation tries to run `manage.py migrate`/`createsuperuser`/`collectstatic` as the
dedicated `paperless` service user via Ansible's `become`/`become_user`, it can fail with a
literal `/bin/sh: 1: sudo: not found` if the base template doesn't ship `sudo` — common for
minimal Debian LXC templates in this kind of homelab fleet. Rather than adding `sudo` just for
this, run these one-off setup commands as root (same as they'd run over a root SSH connection
regardless) and let a recursive ownership-fix step afterward (`chown -R paperless:paperless
...`) correct any root-owned files those commands created — this matches the existing
root-then-chown pattern already used for other native-install services in this fleet (n8n,
Homepage) rather than introducing a new dependency.

## Verifying OCR for real, not just "upload succeeded"

A `200`/task-`SUCCESS` response only proves the document was accepted and processed *some* way
— it doesn't prove OCR actually ran. To verify OCR text extraction genuinely works:

1. Generate an **image-only** test PDF (no embedded text layer) so the pipeline can't cheat by
   reusing an existing text layer instead of actually running Tesseract:
   ```bash
   convert -size 1000x300 xc:white -gravity center -pointsize 48 -fill black \
     -annotate 0 "SOME_UNIQUE_TEST_STRING" /tmp/test.png
   convert /tmp/test.png /tmp/test.pdf
   ```
2. Upload via the API (`POST /api/documents/post_document/`, `Authorization: Token <token>`,
   multipart `document=@test.pdf`) — returns a task UUID.
3. Poll `GET /api/tasks/?task_id=<uuid>` until `status` is `SUCCESS` (or `FAILURE`).
4. Confirm via `GET /api/documents/?query=SOME_UNIQUE_TEST_STRING` that the document is found
   **and** its `content` field contains the exact string — this is the actual proof OCR read
   the image correctly, not just that a file landed on disk.
5. `GET /api/documents/<id>/thumb/` should return `200` with real image bytes — confirms
   thumbnail generation, a separate pipeline step from OCR.

Delete the test document afterward (`DELETE /api/documents/<id>/`) — don't leave synthetic test
data in a personal document archive.

## A shell-quoting trap when generating credentials over nested SSH

If a generated password (e.g. `openssl rand -base64 N`) needs to pass through more than one
layer of shell quoting (e.g. a local script building a remote command that itself runs a
further-nested SSH command), characters like `+`, `/`, `=` can silently get mangled without any
error at creation time — `createsuperuser --noinput` reports success, but the account then
can't log in, and the failure only surfaces later at the login attempt, disconnected from the
actual cause. **Use `openssl rand -hex N` instead** (alphanumeric-only output) for any credential
that has to transit multiple shell layers, sidestepping the whole class of quoting bugs rather
than trying to escape correctly through every layer. If a password already went in wrong, fix it
with `manage.py changepassword <username>` reading the new value from its own interactive
prompt (via a here-string/heredoc on stdin) rather than as a command-line argument.
