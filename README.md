# 🛡️ Shadow Sentinel

**Autonomous OS-Level Revision & Backup Daemon with Decentralized Marker Control and Loop-Coupling.**

Shadow Sentinel monitors directory trees in real-time via the Linux kernel (`inotify`), captures
atomic `.bak` revisions and unified diffs (`.diff`) on every file modification, and provides
instant 1-command restores with loop-coupling safety.

---

## 🚀 Key Features

1. **Decentralized Marker Control (`sentinel_marker`)**:
   - No tedious editing of central configuration files.
   - Simply run `sentinel init [MB]` in any directory or place a `sentinel_marker` file.
   - The daemon automatically scans the system on startup and binds all marked roots.

2. **Dynamic File-Size Ceiling (Self-Pruning Vault)**:
   - The value inside `sentinel_marker` sets the protected size ceiling (e.g. `5` for 5 MB).
   - If a file (such as a runaway logfile) exceeds this ceiling, it is automatically ejected
     from the shadow vault. Small scripts, configurations, and source code stay 100% protected.

3. **Loop-Coupling (Undo-Safe Restore)**:
   - Restoring a file with `sentinel restore <ID>` overwrites the target file.
   - The running inotify daemon immediately intercepts this write and seals the overwritten
     version into a brand-new backup revision. Mistaken restores can instantly be undone!

4. **Flapping & Cooldown Debounce**:
   - Rapid consecutive writes are debounced with a 3-second quiet window to prevent spam.

5. **Zero Dependencies**:
   - Pure Python standard library with native `ctypes` bindings directly to `libc.so.6`.
   - No external tools like `inotifywait` or background Git daemons required.

---

## 🧹 Automated Disk Sanitation & Retention Doctrine

Sentinel guarantees that it will never exhaust disk space through a 4-tier automated policy:

1. **Version Cap per File (Max 10 Revisions)**:
   Only the 10 most recent `.bak` and `.diff` files per target are kept. Older versions are deleted.

2. **Version Age Expiration (14 Days)**:
   Revisions older than 14 days are automatically pruned.

3. **Log Expiration (30 Days)**:
   Daily audit diff logs (`diff-YYYYMMDD.log`) are removed after 30 days.

4. **Emergency Storage Ceiling (500 MB Cap)**:
   If total backup directory size exceeds 500 MB, an emergency purge trims the oldest backups
   across all files until total disk usage drops back down to 80% (400 MB).

5. **Active Vault Ejection**:
   Files that grow beyond the MB ceiling in `sentinel_marker` are immediately removed from
   the `.shadow_vault` to recover disk space instantly.

*The pruning engine runs automatically every 6 hours and immediately upon service startup.*

---

## 📦 Installation

```bash
pip install shadow-sentinel
```

Set up and start the systemd background service in one step:
```bash
sudo sentinel service install
```

---

## 🛠️ Usage

### Protect a Directory
Navigate to the directory and run:
```bash
sentinel init 5
```
*(Creates `sentinel_marker` with a 5 MB file size limit).*

### List Backups
Simply type in any terminal:
```bash
sentinel
```
Automatically detects the nearest marker upwards and lists all protected revisions.

### Restore a File
```bash
sentinel restore 3
```

### View Unified Diff
```bash
sentinel diff 3
```

### List All Active Markers on System
```bash
sentinel markers
```

### Full Interactive Manual
```bash
sentinel help
```

---

## ⚙️ Storage & Configuration

### Linux FHS Standard Paths:
- **Root Daemon:** `/var/lib/shadow-sentinel/`
- **User Daemon:** `~/.local/share/shadow-sentinel/`

### Custom Storage Redirection (`/etc/shadow-sentinel/config.json`):
To store backups, vaults, and indices in a custom directory, create:
`/etc/shadow-sentinel/config.json` (for root) or `~/.config/shadow-sentinel/config.json` (for user):

```json
{
    "storage_dir": "/custom/path/to/backups"
}
```

### Environment Variable Override:
```bash
export SENTINEL_STORAGE_DIR=/custom/path/to/backups
```
