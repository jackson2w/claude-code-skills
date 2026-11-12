---
name: macos-pre-erase-audit
description: This skill should be used before a Mac is erased, traded in, sold or handed down, to check over SSH what would be lost — whether iCloud Drive (incl. Desktop & Documents), iCloud Photos, Messages in iCloud, Notes and Voice Memos are fully synced, and what lives only locally (Trash, Downloads, app data, keys, credentials). Also covers the fleet cleanup after. Trigger phrases include "trade in my mac", "erase my mac", "before I wipe", "anything I should back up", "sell my mac mini", "is everything in icloud", "photos not uploaded", "decommission a mac".
---

# Pre-erase audit of a Mac (read-only, over SSH)

Done 2026-11-11 on Will's M1 Mac mini (macOS 27.2) before trade-in. All reads; no osascript (it pops
an Automation prompt on the Mac's screen and hangs). Remote shell may be zsh: use `/usr/bin/log`.

1. **Space map:** `df -h /System/Volumes/Data`; `du -sh ~/* ~/.[!.]* | sort -h`, then drill into the
   big ones (`~/Library/{Application Support,Containers,Group Containers,Messages,Photos}`).
2. **iCloud Drive:** `brctl status` → "caught-up", last-sync time, and
   `Desktop & Documents: current=YES`. `xattr ~/Desktop` shows `com.apple.icloud.desktop` when synced.
   Downloads is NOT part of Desktop & Documents.
3. **Photos:** read-only `sqlite3 "file:$LIB/database/Photos.sqlite?mode=ro"`:
   `select ZCLOUDLOCALSTATE, ZSAVEDASSETTYPE, count(*) from ZASSET where ZTRASHEDSTATE=0 group by 1,2`.
   State 1 = uploaded. Un-uploaded rows with ZSAVEDASSETTYPE 12 imported by `com.apple.MobileSMS`
   (`ZADDITIONALASSETATTRIBUTES.ZIMPORTEDBYBUNDLEIDENTIFIER`) are Messages "Shared with You" items:
   covered by Messages, not lost.
4. **Messages:** `defaults read com.apple.madrid | grep CloudKit` → `CloudKitSyncingEnabled = 1` and a
   recent `CloudKitSyncDate`.
5. **Notes:** `NoteStore.sqlite` (group.com.apple.notes): `select ZACCOUNTTYPE, ZNAME from
   ZICCLOUDSYNCINGOBJECT where ZACCOUNTTYPE is not null` → only iCloud means no "On My Mac" notes.
6. **Voice Memos:** count `.m4a` in `group.com.apple.VoiceMemos.shared/Recordings` vs rows in
   `CloudRecordings.db` (ZCLOUDRECORDING); have the user spot-check the oldest on the phone.
7. **Mail:** no `~/Library/Mail/V10/Mailboxes` = no local mailboxes.
8. **Local-only leftovers to show the user:** `~/.Trash` (names only), `~/Downloads`, `~/.ssh` (private
   keys?), app configs like Raycast (`~/.config/raycast`; export in-app), credential files (compare a
   hash with the vault copy, never print: `tr -d '\n' < f | shasum -a 256 | cut -c1-12`).
9. **Before erase (user):** sign out of iCloud (Find My / Activation Lock), unlink Signal/WhatsApp/
   Dropbox, unpair Bluetooth, then Erase All Content and Settings (FileVault on = crypto erase).
10. **Fleet cleanup after:** Pi-hole records (`pihole-dns-hosts.yml`, LAN + tailnet IP), Tailscale
    device (`tailscale-devices.sh delete <id> --yes`), UniFi: `cmd/stamgr {"cmd":"forget-sta","macs":[…]}`
    for EVERY record of the machine (wired, Wi-Fi, old private-MAC entries: search `rest/user` by
    name/hostname). UniFi re-creates a bare record for a recently seen MAC at once: harmless, no
    reservation. Then grep repos for the hostname/IPs and update memory.
