---
name: jellyfin-media-permissions
description: This skill should be used when Jellyfin shows "Playback failed due to a fatal player error" for a newly-added title, when a library item has empty/stub metadata (title from the folder name only, no overview/poster/runtime), or when media was ingested via an rsync pipeline from macOS. Trigger phrases include "fatal player error", "jellyfin playback failed", "jellyfin permission denied", "jellyfin metadata empty", "openrsync chown", "rsync macOS uid gid Linux permissions".
---

# Jellyfin media permission/metadata troubleshooting

Covers a specific, reproducible failure mode: media lands on disk via some sync pipeline (rsync,
scp, etc.), Jellyfin's library scan picks up the *filename* fine, but the file is unreadable by
the Jellyfin service account — surfacing as a playback error and/or a stub library entry with no
real metadata. First hit 2026-07-17 debugging a movie synced in over the Jellyfin dropbox-sync
pipeline (see the homelab project's own memory for that pipeline's specifics); the underlying
mechanism generalizes to any media-server-behind-a-sync-job setup.

## The macOS rsync root cause

macOS's built-in `rsync` is **openrsync** (protocol 29), not classic GPL rsync — check with
`rsync --version`. It has **no `--chown`, `--no-owner`, or `--no-group` flags**. `-a` (archive)
still preserves the local macOS account's uid/gid and file mode verbatim onto the remote side.
If the source file has a restrictive mode (`600`, owner-only — common for browser downloads,
which often carry a quarantine xattr too) and the remote consumer runs as a *different* service
account (e.g. `jellyfin`, not the account that owns the transferred bytes), that account can't
read it. **This is silent on the sync side** — rsync exits 0, the transfer looks completely
successful — and only manifests as an error on the Jellyfin side, often much later when someone
tries to play the file.

Because there's no rsync flag to fix this from the macOS end, fix it with a **post-transfer
remote command** instead, folded into whatever script does the sync:

```bash
ssh "$REMOTE" "chown -R jellyfin:jellyfin /path/to/media && \
    find /path/to/media -type d -exec chmod 755 {} + && \
    find /path/to/media -type f -exec chmod 644 {} +"
```

Don't try to reshape the rsync invocation to work around this (e.g. stripping `-a` down to
`-rlptD` still leaves ownership ambiguous depending on how the receiving process is invoked) —
a dedicated fixup step after the transfer is simpler and unambiguous.

## Diagnosing: two things break together, not just playback

A permission-denied file blocks **both**:
1. **Playback** — the transcoder (or direct-play file read) can't open the file. This is what
   surfaces to the user as "Playback failed due to a fatal player error."
2. **Metadata identification** — Jellyfin's probe step (`ffprobe`-equivalent, needed to get
   runtime/codec info) fails for the same reason, which can abort the rest of that item's
   scan before it reaches online provider lookup (TMDb/etc.) or before it can write
   `.nfo`/extracted images back into the media folder (needs the *directory* to be writable by
   `jellyfin`, not just the file to be readable — check both, they can differ, e.g. `755` on
   the parent dir has no write bit for anyone but the owner).

**Diagnostic signature in the library**: an item whose `Overview`/`Genres` are empty and whose
runtime is null, with `Name`/`ProductionYear` that look exactly like a straight parse of the
folder name — that's the fingerprint of the scan erroring out *before* it got to identification,
not a genuine "no provider match" (a real failed match still completes the probe, so runtime
would be populated). Query directly if the Jellyfin API/dashboard isn't handy:

```bash
# sqlite3 CLI often isn't installed on a minimal Debian LXC — python3's stdlib module works fine:
python3 -c "
import sqlite3
c = sqlite3.connect('/var/lib/jellyfin/data/jellyfin.db').cursor()
c.execute(\"SELECT Name, ProductionYear, Overview, RunTimeTicks, Path FROM BaseItems WHERE Name LIKE '%<title fragment>%'\")
for row in c.fetchall(): print(row)
"
```

Confirm the actual cause (don't guess from `ls -la` alone — that shows *a* permission, not
whether the specific service account can use it) by testing as the real service user:

```bash
sudo -u jellyfin test -r /path/to/file.mkv && echo READABLE || echo NOT_READABLE
sudo -u jellyfin touch /path/to/parent-dir/.write-test && echo WRITABLE
```

Also check `journalctl -u jellyfin` for the literal `Permission denied` line from the jellyfin
binary itself (distinct from its own `[ERR]` log lines) plus `Error in Probe Provider` / `Error
in metadata saver` / `UnauthorizedAccessException ... .nfo` — these three together are the
fingerprint of this exact failure, not a codec/container problem.

## Rule out a real media problem first

Before assuming permissions, a quick `ffprobe` **as root** (root bypasses file permission checks
entirely, so this works even on a file the jellyfin user can't read yet) confirms whether the
file itself is fine:

```bash
/usr/lib/jellyfin-ffmpeg/ffprobe -v error -show_entries stream=index,codec_type,codec_name -of default=noprint_wrappers=0 /path/to/file.mkv
```

Plain H.264/HEVC/VP9 video + AAC/AC3/etc. audio is fine for Jellyfin's default transcoder. If
there's an extra video stream, check its disposition — a cover-art thumbnail should show
`DISPOSITION:attached_pic=1` and `DISPOSITION:default=0`; if so it's correctly excluded from
playback stream selection and isn't the problem.

## After fixing permissions

Playback works on the very next attempt with no further action — probing happens live at
playback time. The **library metadata does not self-heal** though; Jellyfin doesn't
automatically retry a previously-failed identify pass. Trigger it manually: on the item, "⋮" →
**Refresh Metadata → Replace All Metadata and Images** (or Scan All Libraries for the whole
library). Verify the fix actually took by re-running the same `sudo -u jellyfin` read/write test
above, not just by re-checking `ls -la` permission bits.

**Separate gotcha this can uncover**: if metadata refresh still comes back with no real
overview/poster after permissions are confirmed fixed, that's a provider (TMDb) title-match
miss, not a permissions problem — e.g. a folder name that drops punctuation from a person's
billed name (`Louis CK` vs. the actual `Louis C.K.`) can fail online lookup outright. Fix via
Jellyfin's own "Identify" search on that item (search by a corrected title or a known provider
ID) rather than re-chasing permissions.
