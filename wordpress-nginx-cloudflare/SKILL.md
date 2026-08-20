---
name: wordpress-nginx-cloudflare
description: This skill should be used when deploying or migrating a WordPress site onto a native nginx + PHP-FPM + MariaDB stack (not Docker, not a managed host like GridPane/WP Engine), when hardening a WordPress origin behind Cloudflare with an Origin CA certificate and Authenticated Origin Pulls, when importing a BackWPup/GridPane export onto a new server, when WP-Cron needs a real heartbeat because DISABLE_WP_CRON is set or the site gets low traffic, or when debugging a WordPress 500 error that traces to a GridPane-specific absolute path or a stale object-cache.php drop-in. Trigger phrases include "migrate wordpress off gridpane", "wordpress nginx php-fpm deployment", "cloudflare origin ca certificate", "authenticated origin pulls", "wp-cron not running", "DISABLE_WP_CRON", "object-cache.php fatal error", "wordfence auto_prepend_file", "BackWPup import", "wp-config.php DB_HOST socket", "real_ip_header cloudflare nginx".
---

# WordPress on nginx + PHP-FPM + MariaDB, behind Cloudflare

Covers a from-scratch WordPress deployment (not Docker, not a managed panel) with Cloudflare
as the sole public entry point, plus the specific gotchas hit migrating a real site off
GridPane onto a fresh Debian host.

## Stack setup

Install `nginx php-fpm php-mysql php-curl php-gd php-mbstring php-xml php-zip php-imagick
php-intl php-bcmath php-soap mariadb-server` from the distro repos — verify the actual
available PHP version live (`apt-cache policy php-fpm`) rather than assuming one.

Create a dedicated system user for the site (no login shell) to own the docroot and run its
own PHP-FPM pool — don't share `www-data` across multiple sites/services on the same box.
Give the pool `pm = ondemand` for a low-traffic site (no idle workers sitting around).

Create a dedicated MariaDB database + user scoped to just that database, random password,
written only into `wp-config.php`.

## Importing a GridPane/BackWPup export

A BackWPup export lands as a `.tar` containing the DB dump (`.sql`), `wp-config.php`, the
full site tree, and a `manifest.json` describing the original `abspath`. Two known traps:

1. **GridPane's docroot convention is `/var/www/<domain>/htdocs/`** — a fresh flat extraction
   (no `htdocs` subdir) breaks any absolute path baked into a config file. The one that bites
   immediately: Wordfence's `.user.ini` has `auto_prepend_file =
   '/var/www/<domain>/htdocs/wordfence-waf.php'` — this fires on *every* PHP request via
   `php.ini`'s per-directory `.user.ini` mechanism, so a wrong path here is an instant 500 on
   the homepage, not a delayed/soft failure. Fix by rewriting the path in `.user.ini` to
   match wherever the new docroot actually is (or by preserving the `htdocs/` layout on
   import to avoid touching it at all).
2. **`wp-content/object-cache.php` is a live drop-in, not inert config.** If the export came
   from a site running the `redis-cache` plugin (or similar), this file is present and WP
   will use it automatically — even though the plugin's own PHP file may be inactive. If the
   new host has no Redis, this produces a **fatal** `Predis\Connection\ConnectionException`
   on every request, not a graceful fallback. Delete `wp-content/object-cache.php` outright
   if the new deployment isn't running the same cache backend; WordPress falls back cleanly
   to its built-in non-persistent object cache.

`wp-config.php`'s `DB_HOST` is often written as `localhost:/var/run/mysqld/mysqld.sock` (a
GridPane convention) — this works unchanged against a standard Debian MariaDB install, which
uses the same socket path. Only `DB_NAME`/`DB_USER`/`DB_PASSWORD` need updating for the new
database.

Check `wp-config.php`'s trailing custom-includes section (GridPane typically adds
`include __DIR__ . '/user-configs.php';` unconditionally near the bottom) — if that file
doesn't exist in the export, it's a soft `PHP Warning`, not fatal, but worth stubbing with an
empty file to keep logs clean.

## Cloudflare Origin CA + Authenticated Origin Pulls

For a Cloudflare-proxied domain, skip Let's Encrypt entirely and use a **Cloudflare Origin
CA certificate**: dashboard → SSL/TLS → Origin Server → Create Certificate (15-year default
is fine, covers apex + wildcard). This cert is only trusted by Cloudflare's edge, never by a
direct client — that's the point.

Pair it with **Authenticated Origin Pulls** so the origin only accepts connections that
actually came through Cloudflare:

1. Check whether "Global" AOP is already enabled account-wide (SSL/TLS → Origin Server →
   Authenticated Origin Pulls tab) — it very often already is, in which case no per-zone
   toggle is needed, just the origin-side nginx config.
2. Fetch Cloudflare's public Origin Pull CA cert (a fixed, non-secret file, safe to `curl`
   directly): `https://developers.cloudflare.com/ssl/static/authenticated_origin_pull_ca.pem`
3. On the origin's nginx vhost: `ssl_client_certificate /path/to/that-ca.pem;` and
   `ssl_verify_client on;`. A request without Cloudflare's client cert gets a clean
   `400 No required SSL certificate was sent` — verify this directly (`curl` straight to the
   origin's public IP) as proof the gate works, separate from verifying the real domain works
   through Cloudflare.

**Verification technique that doesn't touch live DNS**: before cutting over a real domain's
A record, create a throwaway subdomain (e.g. `migration-test.example.com`), proxied, pointed
at the new origin. This exercises the *real* Cloudflare→AOP→origin path end-to-end with zero
risk to the live site, and gets deleted afterward.

## The nginx-vs-tailscaled port conflict

If the same host already runs Tailscale Serve/Funnel for another service, binding nginx to
`listen 443 ssl;` (wildcard `0.0.0.0:443`) can fail with `bind() to 0.0.0.0:443 failed
(98: Address already in use)` even though `tailscaled` is bound to a *different*, specific IP
(its own Tailscale address) on the same port — Linux won't let a wildcard bind coexist with
an existing specific-IP bind on the same port, regardless of which IP the wildcard would
otherwise prefer. Fix: bind nginx explicitly to the host's public IP
(`listen <public-ip>:443 ssl;`) instead of the wildcard. Drop bare `listen [::]:443;` too if
the host has no real public IPv6 (check `ip -6 addr show`, excluding Tailscale's `fd7a::`
ULA range and link-local `fe80::`) — it serves no purpose and can hit the identical conflict
against `tailscaled`'s own IPv6 listener.

## real_ip_header for Cloudflare

Without `set_real_ip_from` + `real_ip_header CF-Connecting-IP;`, nginx logs Cloudflare's edge
IP as the client for every request — not the real visitor. This silently breaks anything that
reads `$remote_addr` downstream, most importantly **fail2ban**: a jail built against
unpatched logs will end up banning Cloudflare's own shared edge IP ranges, taking the site
down for everyone. Fetch Cloudflare's current IP ranges live
(`https://www.cloudflare.com/ips-v4` and `/ips-v6`) rather than hardcoding them — they do
change. Verify the fix by making a real request and confirming the access log shows the
actual originating IP, not a Cloudflare range.

## WP-Cron needs a real heartbeat on a low-traffic site

WordPress's default "cron" is a pseudo-cron that only fires on an incoming page request —
useless for a near-zero-traffic site, and **already broken entirely** (not just unreliable)
if `DISABLE_WP_CRON` is set to `true` in `wp-config.php` (a common managed-host convention,
since panels like GridPane normally run their own external cron driver that doesn't survive
a migration). Check for this constant before assuming pseudo-cron is even a fallback.

Fix with a systemd timer driving `wp cron event run --due-now` via wp-cli, running as the
site's own system user:

```ini
[Service]
Type=oneshot
User=<site-user>
WorkingDirectory=/path/to/site
ExecStart=/usr/local/bin/wp cron event run --due-now
```
```ini
[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true
```

Verify by checking `wp cron event list` shows real hooks (`wp_update_plugins`,
`wp_version_check`, etc.) with sane `next_run_relative` values, and by tailing
`journalctl -u <the service>` after a manual `systemctl start` to confirm events actually
executed (not just that the unit exited 0).

## Verifying auto-update settings and the mail path

`auto_update_core_major`/`_minor`/`_dev` and `auto_update_plugins` live in `wp_options` —
check them directly with `wp option get <name>` rather than assuming WordPress's documented
defaults apply; a managed-host export can carry a more (or less) aggressive setting than
vanilla WordPress ships with.

To verify WordPress's own update-failure email notifications will actually work (the same
`wp_mail()` path they use), don't wait for a real failure — trigger a real send directly:
`wp eval 'var_dump(wp_mail("you@example.com", "test", "body"));'`. A `bool(true)` confirms
the configured mail transport (SMTP plugin, Postmark, etc.) accepted the message; for
stronger proof of actual delivery, check the transport's own delivery log (e.g. Postmark's
Messages API) rather than trusting the boolean alone.
