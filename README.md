# claude-code-skills

Willie Jackson's Claude Code skills — infrastructure, Cloudflare development, and web/design
utilities. Distinct from [`claude-skills`](https://github.com/jackson2w/claude-skills), which
holds a separate catalog (11ty sites, document formats, presentation/spreadsheet tooling) used
with Cowork and Claude Code.

Drop any of these directories into `~/.claude/skills/` (or a project's `.claude/skills/`) and
Claude Code auto-discovers them — no install step beyond having the `SKILL.md` on disk.

## Proxmox / homelab infrastructure

- **proxmox-ansible-provisioning** — creating a new Proxmox LXC/VM and writing Ansible playbooks
  against Proxmox/Debian hosts (Debian 13/trixie locale and `apt_repository` gotchas, `lineinfile`
  idempotency traps, TUN passthrough for Tailscale in unprivileged LXCs).
- **proxmox-terraform-provisioning** — the `bpg/proxmox` Terraform provider: scoped API tokens,
  importing existing LXCs/VMs as a no-op baseline, and VM-specific gotchas (`SDN.Use`, disk
  import needing host SSH, appliance images like Home Assistant OS/pfSense with no cloud-init).
- **proxmox-node-systemd-service** — running a Node.js/pnpm app as a native systemd service in an
  unprivileged LXC instead of Docker: NodeSource install, Ansible git-module idempotency traps,
  and the "binds 0.0.0.0 by default" gotcha common to Next.js and similar frameworks.
- **proxmox-pbs-backup-job** — adding a new host to an existing Proxmox Backup Server nightly
  schedule via `pvesh`, and the `Datastore.Prune` permission gotcha that fails silently per-job.
- **home-assistant** — configuring/troubleshooting a Home Assistant OS (HAOS) instance: add-ons
  (now "Apps"), `configuration.yaml`, Tailscale remote access, Supervisor, backups.
- **paperless-ngx-bare-metal** — installing Paperless-ngx from its release tarball instead of
  Docker Compose: the tarball's real directory layout, the `mysqlclient` build dependency needed
  even for SQLite, Granian (not Gunicorn) as the ASGI server, and verifying OCR actually ran
  rather than just "upload succeeded."
- **jellyfin-media-permissions** — diagnosing "fatal player error" / empty-metadata library
  items caused by a macOS `rsync` pipeline leaving files unreadable by Jellyfin's service
  account (openrsync has no `--chown`/`--no-owner` flags).
- **pihole-local-dns-records** — getting Pi-hole's dashboard/Query Log to show device names
  instead of raw IPs, identifying unlabeled devices via mDNS/DHCP without router access, and
  why the dashboard label can lag a correct `dns.hosts` record.
- **proxmox-no-subscription-nag** — suppressing the "No valid subscription" login popup on a
  free/no-subscription PVE or PBS install.
- **proxmox-vzdump-notifications** — customizing Proxmox's Handlebars backup-notification
  templates and testing them without waiting for (or triggering) a real backup job.
- **proxmox-zfs-root-mirror** — converting a single-disk ZFS root pool (`rpool`) into a live
  mirror, swapping a drive out, and growing the mirror to full capacity — all via `zpool
  attach`/`detach`/`online -e`, no Proxmox reinstall or guest restore-from-backup needed.
- **tailscale-pihole-dns-routing** — the interaction between Tailscale's tailnet-wide DNS
  override, MagicDNS, and Pi-hole — why a host can silently bypass Pi-hole even though DNS
  still resolves, and the systemd-resolved split-DNS fix.
- **n8n-workflow-api-authoring** — authoring n8n workflow JSON for import via its REST API
  instead of the editor UI: credential/expression/Code-node gotchas that don't show up until
  a workflow actually runs.

## Cloudflare

- **cloudflare** — general-purpose Cloudflare platform skill: Workers, Pages, KV/D1/R2, Workers
  AI, networking, security, infra-as-code.
- **cloudflare-r2-rclone-backup** — nightly offsite backups to R2 via rclone's S3-compatible API
  (the `--delete` flag trap, `-v`/`--log-level` conflict, R2's `501 NotImplemented` on modtime
  fixups).
- **cloudflare-cron-telegram-alert** — scaffolding a cron-triggered Worker that checks something
  external and alerts to Telegram only on failure (uptime monitors, dead-man's-switches).
- **cloudflare-workers-cron-email** — debugging Cron Triggers that don't fire (or fire on the
  wrong day), `send_email` binding setup, subrequest limits, R2 rename/delete verification.
- **cloudflare-pages-gotchas** — Pages Functions platform quirks: no Images binding, empty
  `[env.*]` blocks dropping bindings, PBKDF2's 100k-iteration cap, `_redirects` precedence.
- **cloudflare-email-service** — transactional email via Cloudflare Email Service (sending +
  routing), SPF/DKIM/DMARC, any runtime (Workers, Node, Python, Go).
- **cloudflare-one** / **cloudflare-one-migrations** — Zero Trust/SASE design and migrations from
  Zscaler/Palo Alto/legacy VPN stacks.
- **agents-sdk** — stateful agents, Durable Workflows, MCP servers, and voice/chat apps on the
  Cloudflare Agents SDK.
- **durable-objects** — stateful coordination (chat rooms, booking systems), RPC methods, SQLite
  storage, alarms.
- **sandbox-sdk** — sandboxed code execution (interpreters, CI/CD, untrusted-code execution).
- **turnstile-spin** — end-to-end Cloudflare Turnstile setup: widget creation, siteverify Worker,
  frontend snippets.
- **workers-best-practices** — production best practices for Worker code and `wrangler.jsonc`.
- **wrangler** — the Workers CLI: KV, R2, D1, Vectorize, Hyperdrive, Queues, Workflows, Secrets
  Store.
- **cloudflare-worker-tailscale-shield** — putting a Worker in front of a Tailscale-Funnel-exposed
  homelab service (edge auth/rate-limit + Queue retry-on-failure): why Workers can't reach
  tailnet-private addresses, forwarding the origin's own auth header through, and a `wrangler
  secret put` misuse that leaks a secret's value as its *name*.

## Web / design / verification

- **frontend-design** — distinctive, production-grade frontend interfaces that avoid generic AI
  aesthetics.
- **web-perf** — Core Web Vitals auditing via Chrome DevTools MCP (LCP/INP/CLS, render-blocking
  resources, layout shifts).
- **cdp-layout-verification** — verifying precise CSS layout/spacing/alignment via direct DOM
  measurement, not just an eyeballed screenshot.
- **artifact-font-embedding** — sourcing real Google/Fontsource fonts and embedding them as
  base64 `@font-face` data URIs inside a Claude Artifact (works around CSP blocking external
  fonts).
- **image-crop-focal-point** — picking a normalized focal point / CSS `background-position` so a
  subject stays in frame across aspect-ratio crops.

## Other

- **postmark** — transactional email via Postmark's SMTP relay or HTTP API, including from
  non-Workers systems (Proxmox, cron jobs, backend services).
- **find-skills** — discovering and installing skills based on a described capability gap.
- **skill-development** — guidance for creating/improving Claude Code skills (structure,
  progressive disclosure, description quality).
