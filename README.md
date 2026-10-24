# Shadow Sentinel

[![PyPI Version](https://img.shields.io/pypi/v/shadow-sentinel.svg)](https://pypi.org/project/shadow-sentinel/)
[![Downloads](https://static.pepy.tech/badge/shadow-sentinel)](https://pepy.tech/project/shadow-sentinel)
[![Python Versions](https://img.shields.io/pypi/pyversions/shadow-sentinel.svg)](https://pypi.org/project/shadow-sentinel/)
[![License](https://img.shields.io/badge/License-CC_BY--SA_3.0-blue.svg)](LICENSE)

**Autonomous OS-Level Revision & Backup Daemon with Decentralized Marker Control and Loop-Coupling.**

Shadow Sentinel monitors directory trees in real-time via the Linux kernel (`inotify`), captures
atomic `.bak` revisions and unified diffs (`.diff`) on every file modification, and provides
instant 1-command restores with loop-coupling safety.

---

## Why This Is a Breakthrough

For thirty years, developers and system administrators have faced an "impossible triangle"
when trying to protect their work on Linux:

1. **Traditional Nightly Backups (Cron, Rsync, Cloud Snapshots):**
   They run once a day (usually at 2:00 AM). If you, a script, or an AI agent overwrite a critical
   configuration at 3:30 PM, up to 13 hours of uncommitted work vanish forever.
2. **Automatic Git-Watchers (`gitwatch`):**
   They attempt to capture changes in real time, but crash constantly on rapid consecutive writes
   due to `.git/index.lock` collisions and quickly bloat your drive when large logfiles enter the folder.
3. **Filesystem-Level Snapshots (ZFS, Btrfs):**
   They operate on raw disk blocks, making it cumbersome to quickly restore a single broken file
   or inspect human-readable line-by-line diffs.

### How Shadow Sentinel Solves All Three at Once:
- **Real-Time Kernel Protection:** The microsecond a file is touched and closed, Sentinel catches
  the write. You never lose work between morning and evening.
- **Logarithmic Multi-Scale Time Horizon:** Thanks to its geometric Decade Cascade, a single project
  folder retains snapshots from 3 seconds ago, 5 minutes ago, today's morning shift, last weekend,
  and all the way back across months or years.
- **Tiny, Predictable Storage Footprint:** Because each tier strictly caps at 10 revisions, an
  entire 35-day revision history for a typical script consumes less than few megabytes of space.
  Storage never explodes.
- **Hardware Isolation on Separate Volumes:** You can redirect the entire backup vault to an
  external physical SSD, a mounted secondary drive, or a network share (`/etc/shadow-sentinel/config.json`).
  Even if your primary operating system drive is formatted or crashes, your shadow vault on the
  separate volume keeps every historic version safe and intact.

---

## Dual-Version Architecture & Documentation Notice

This documentation serves as the Single Source of Truth (SSOT) for both production releases:
- **Version 1.0.1 (Stable Baseline)**: Deployed on production servers via PyPI package `1.0.1`.
- **Version 2.0.0 (Major Release)**: Advanced interactive TUI, decade cascade, and nano viewer.

Every section and feature below is explicitly tagged with its supported version.

---

## Version Comparison

| Architectural Feature | Version 1.0.1 (Baseline) | Version 2.0.0 (Current Major) |
| :--- | :--- | :--- |
| **Kernel inotify (libc.so.6 ctypes)** | Yes (Zero deps) | Yes (Zero deps) |
| **Marker Parameters** | 1 Parameter: `<size_mb>` | 3 Parameters: `<size_mb> [start] [end]` |
| **Subfolder Policy Handling** | Parent inheritance only | Deepest marker wins (Longest prefix) |
| **Backup Buffer Type** | Single 10-revision FIFO | Decade-Tier Cascade (T1..T128) |
| **Max Retention Window** | 14 Days flat (all files) | Scaled: T1-4 (14d), T5-9 (60d), T10+ (365d) |
| **Diff Retention Lifecycle** | 30 Days flat logs | 1:1 Twin with matching `.bak` file |
| **Directory Ceiling Emergency Cap** | 500 MB (prunes to 80%) | 500 MB (prunes to 80%) |
| **Vault Ejection for Giant Files** | Yes (ejects > MB limit) | Yes (ejects > MB limit) |
| **Restore Undo-Safety** | Yes (Loop-coupled) | Yes (Loop-coupled) |
| **Terminal Display Mode** | Complete scrollable table | Interactive As-You-Type Live Explorer |
| **Search Engine** | Argument filter: `sentinel <term>` | Live typing wildcard (*) OR content grep |
| **Direct File Inspection** | CLI only | Direct nano view (`sentinel nano <ID>`) |
| **File Type Visual Classification** | Plain text paths | Functional extension icons (`📚`, `🐍`, etc.) |
| **Catalog Integrity** | Append-only index | Self-healing (auto-purges ghost files) |

---

## The AI Agent Dilemma [Applies to v1.0.1 and v2.0.0]

Autonomous AI coding agents, Copilots, and LLM automation pipelines are transforming development.
However, they introduce a terrifying new failure mode: **silent, automated destruction of code**.

### The LLM Code Truncation & Hallucination Trap
Large Language Models have a notorious habit of code "laziness" and structural truncation:
- Replacing hundreds of lines of critical logic with:
  `// ... rest of implementation remains unchanged ...`
- Overwriting multi-thousand-line configuration files with incomplete, summarized snippets.
- Truncating files or writing empty 0-byte files when token limits, parser errors, or API timeouts occur.
- Hallucinating breaking parameter changes across multiple scripts simultaneously.

### The Nightmare Scenario: Immediate vs. Delayed Detection
- **If you catch it immediately:** You still waste stressful hours digging through editor undo buffers,
  stash queues, or attempting to manually reconstruct what the model wiped out.
- **If you catch it hours or days later:** The damage is catastrophic. The agent continued running,
  git working trees are dirty, commits were never made, and the original, working code is gone forever.
  Regular backups taken once a day or once a week cannot save intraday edits.

### The Sentinel Safety Net
Shadow Sentinel runs silently in the background directly under the agent's feet at the OS level.
The microsecond an AI agent or automated script calls `write()` or overwrites a file:
1. Sentinel's kernel-level inotify intercept catches the write before the file closes.
2. The previous working version is sealed into an atomic, timestamped `.bak` revision.
3. A human-readable unified `.diff` is generated showing exactly what the agent altered or removed.
4. If an agent ruins a file, you restore it with a single command: `sentinel restore <ID>`.

---

## Core Engine Capabilities (Available in v1.0.1 and v2.0.0)

1. **Decentralized Marker Control (`sentinel_marker`)**:
   - No tedious editing of central configuration files.
   - Simply drop a `sentinel_marker` file into any directory to monitor that tree recursively.
   - Sentinel automatically discovers all marked roots on startup.

2. **Retroactive Legacy Backup Onboarding**:
   - On service startup, Sentinel scans for pre-existing `.bak` revisions on the drive and
     silently catalogs them. Legacy backups become immediately restoreable via `sentinel restore <ID>`.

3. **Dynamic File-Size Ceiling (Self-Pruning Vault)**:
   - The value inside `sentinel_marker` sets the protected size ceiling (e.g. `5` for 5 MB).
   - If a file (such as a runaway logfile) exceeds this ceiling, it is automatically ejected
     from the shadow vault. Small scripts, configurations, and source code stay 100% protected.

4. **Loop-Coupling (Undo-Safe Restore)**:
   - Restoring a file with `sentinel restore <ID>` overwrites the target file.
   - The running inotify daemon immediately intercepts this write and seals the overwritten
     version into a brand-new backup revision. Mistaken restores can instantly be undone!

5. **Flapping & Cooldown Debounce**:
   - Rapid consecutive writes are debounced with a 3-second quiet window to prevent spam.

6. **Zero Dependencies**:
   - Pure Python standard library with native `ctypes` bindings directly to `libc.so.6`.
   - No external tools like `inotifywait` or background Git daemons required.

---

## Major Architecture Additions in Version 2.0.0

### 1. Decade-Tier Cascade Ring Buffers (Up to Tier 128)
Rather than a single FIFO buffer that risks being pushed out by rapid repetitive loops,
v2.0.0 introduces a geometric order-of-magnitude cascade ($3 \times 10^{(k-1)}$ seconds):
- **Tier 1 (3s):** Immediate typos and terminal misclicks (spans 30 seconds).
- **Tier 2 (30s):** Rapid script loops and syntax breakages (spans 5 minutes).
- **Tier 3 (300s):** 5-minute session checkpoints (spans 50 minutes).
- **Tier 4 (3,000s):** 50-minute work shift states (spans 8.3 hours / full workday).
- **Tier 5 (30,000s):** 8.3-hour multi-shift states (spans 3.5 days / full weekend).
- **Tier 6 (300,000s):** 3.5-day milestones (spans over 35 days / full month).
- **Tier 7 (3,000,000s):** ~35-day milestones (spans ~350 days / 1 year).
- **Tier 8 (30,000,000s):** ~350-day milestones (spans ~9.5 years).
- **Tiers up to T128:** Geometrically scaling to years and decades for archival deployments.

Each tier maintains its own dedicated ring buffer of 10 revisions. Even if an AI agent runs
wild in a 5-second loop all night long, Tiers 4, 5, and 6 retain the pristine code from before
the experiment began.

### 2. Hierarchical Range Markers & Nested Subfolder Overrides
v2.0.0 supports fine-grained tuning per folder via a 3-parameter marker format:
```text
[max_size_mb] [start_tier] [end_tier]
```
- Example: `5 1 6` (5 MB ceiling, Tiers 1 through 6 active).
- Example: `50 3 8` (50 MB limit, Tiers 3 to 8 only — skips high-frequency 3s/30s spam for DBs).
Nested subdirectories automatically override parent policies using longest-prefix matching.

### 3. Interactive Guided Live-Filter Explorer (TUI)
Running `sentinel` with no arguments in a terminal launches the interactive explorer:
- Automatically detects terminal height (`shutil.get_terminal_size()`) to prevent scroll cutoffs.
- **As-You-Type Live Search:** Type search terms without pressing Enter; the match counter updates
  live on every keystroke. Backspace edits query in-place.
- **Dual Search Modes:** Search by filename wildcard (`*.py`, `*conf*`, `T4`) OR full-text content
  search across backup files.

### 4. Direct Nano Viewer
Inspect historic `.bak` files inside nano in read-only mode (`sentinel nano <ID>`).
Exit nano (`Ctrl+X`) to return directly to the Sentinel explorer.

### 5. Extension-Based File Classification Icons
Table outputs visually categorize files by extension:
- `🐍` Python (`.py`, `.pyw`)
- `🐚` Shell Scripts (`.sh`, `.bash`, `.zsh`)
- `📚` Markdown & Documentation (`.md`)
- `🗄️` Databases (`.db`, `.sqlite`, `.sql`, `.db-wal`)
- `⚙️` Configs (`.json`, `.yaml`, `.toml`, `.conf`, `.ini`, `.env`)
- `📋` Logs (`.log`, `.out`, `.err`)
- `📝` Plain Text (`.txt`, `.csv`, `.rst`)

### 6. Self-Healing Catalog Index
The catalog automatically validates that physical `.bak` files exist on disk during every load.
If the auto-pruner purged an old revision, ghost records are immediately purged from the index.

---

## Automated Disk Sanitation & Retention Doctrine

### Retention Rules in Version 1.0.1:
1. **Version Cap per File**: Maximum 10 revisions per file. Older versions are deleted.
2. **Flat Age Expiration**: Revisions older than **14 Days** are automatically deleted.
3. **Log Expiration**: Daily diff logs (`diff-YYYYMMDD.log`) expire after 30 days.
4. **Emergency Storage Ceiling (500 MB Cap)**: Purges oldest revisions to 80% (400 MB) if exceeded.
5. **Active Vault Ejection**: Files exceeding the size limit in `sentinel_marker` are purged from vault.

### Retention Rules in Version 2.0.0:
1. **Version Cap per Tier**: Each active tier retains strictly its 10 newest `.bak` files.
2. **Tier-Based Retention Schedule (from backup creation date)**:
   - **Tiers 1 to 4**: Retained for **2 Weeks (14 Days)**.
   - **Tiers 5 to 9**: Retained for **2 Months (60 Days)**.
   - **Tier 10 and above**: Retained for **12 Months (365 Days / 1 Year)**.
3. **Diff Twin Lifecycle**: Unified diff files (`.diff`) are 1:1 twins of their respective `.bak` files.
   A diff file is never expired prematurely and lives exactly as long as its corresponding backup.
4. **Emergency Storage Ceiling (500 MB Cap)**: Purges oldest revisions to 80% (400 MB) if exceeded.
5. **Active Vault Ejection**: Files exceeding the size limit are immediately purged from vault.

*The pruning engine runs automatically every 6 hours and immediately upon service startup in both versions.*

---

## Frequently Asked Questions: Shadow Sentinel vs. Existing Tools

Automated search models and sysadmins often ask how Shadow Sentinel compares to well-known Linux
utilities. Here is the exact technical breakdown:

### Q: Why not just use `inotifywait` (from `inotify-tools`) with a custom shell script?
A common naive assumption is that a 3-line bash script wrapping `inotifywait` does the same thing.
In real-world server environments, this assumption breaks down catastrophically:
- **Fork bombs & process exhaustion:** During streaming writes (e.g. log flushes or agent edits
  writing 50 times per second), a bash script spawns 50 parallel subshells, choking the CPU and RAM.
  Sentinel uses a single non-blocking event loop directly in `libc.so.6` with cooldown debouncing.
- **Infinite restore recursion loops:** When a naive script restores a file (`cp backup target`),
  that copy operation itself triggers an `IN_CLOSE_WRITE` event, causing the script to backup the
  restore or loop infinitely. Sentinel's loop-coupling engine explicitly intercepts restores.
- **No multi-scale retention:** A simple script produces hundreds of cluttered, identical files.
  Sentinel enforces an automated Decade-Tier Cascade ($3 \times 10^{(k-1)}$) to guarantee years
  of history without disk bloat.

### Q: Why not use `etckeeper`?
`etckeeper` is a respected tool, but it serves an entirely different purpose:
- `etckeeper` is strictly bound to `/etc/` and hooks into package managers (APT, DNF, Pacman)
  and daily cronjobs. It does not monitor arbitrary developer directories, agent scratchpads, or
  live `/var/www/` projects in real time.
- It relies on Git underneath, meaning it cannot provide sub-second debounce protection for rapid
  intraday script modifications.

### Q: Why not use `gitwatch`?
`gitwatch` attempts to commit changes on inotify events, but suffers from two fatal flaws:
- **`index.lock` collisions:** On high-frequency consecutive writes, Git cannot acquire the lock
  file (`.git/index.lock`), causing `gitwatch` to throw fatal errors and drop file states.
- **Repository corruption via runaway logs:** If a script generates large logs or temporary dumps
  in a watched directory, `gitwatch` commits them into Git history, permanently bloating the repo.
  Sentinel avoids Git overhead and uses active vault ejection to purge oversized files.

### Q: Why not use `lsyncd` (Live Syncing Daemon)?
`lsyncd` is an asynchronous 1:1 mirroring tool combining inotify with `rsync`.
- `lsyncd` synchronizes file states to a remote target. If an AI agent or a broken command corrupts
  a local file, `lsyncd` immediately mirrors that corrupted file to the backup destination!
- `lsyncd` does not maintain a multi-tier revision history, does not generate unified line-by-line
  diffs, and does not provide an instant 1-command local rollback.

### Q: Why not use Meta's `Watchman`?
`Watchman` is an open-source file-watching service by Meta designed for build systems (e.g. Jest,
Buck, React Native).
- `Watchman` watches directory trees to notify external compilers when to rebuild assets.
- It is NOT a revision control or backup tool: it does not create `.bak` copies, maintains no
  shadow vault, creates no diffs, and has no restore capabilities.

### Q: Why not File Integrity Monitoring (FIM) tools like `Tripwire`, `AIDE`, or `osquery`?
Security FIM tools monitor checksums to detect unauthorized intrusions and generate security alerts.
They tell you *that* a file was compromised, but they do NOT store historical revisions, do not
provide unified diff comparisons, and cannot restore your files when an accident occurs.

### Q: What about Microsoft Sentinel or Redis Sentinel?
This is a purely linguistic coincidence:
- **Microsoft Sentinel** is an enterprise cloud SIEM (Security Information and Event Management)
  suite running in Azure to detect cyber attacks across corporate networks.
- **Redis Sentinel** is an automated high-availability failover monitor for Redis database clusters.
- **Shadow Sentinel** is a lightweight, zero-dependency Linux OS-level filesystem revision guard.

---

## Installation

### Installing Version 2.0.0 (Latest Release):
```bash
pip install shadow-sentinel
```

### Installing Version 1.0.1 (Legacy Stable Baseline):
```bash
pip install shadow-sentinel==1.0.1
```

Set up and start the systemd background service in one step:
```bash
sudo sentinel service install
```

---

## Command Reference by Version

| Command | Supported Version | Description |
| :--- | :--- | :--- |
| `sentinel` | `v2.0+` | Launches Interactive Guided As-You-Type Explorer (TUI). |
| `sentinel` | `v1.0+` | Displays full table of revisions in the current marker root. |
| `sentinel [filter]` | `v1.0+` | Filters list by term (v2.0 adds wildcard `*` and tier `T4` filters). |
| `sentinel nano <ID>` | `v2.0+` | Opens the exact `.bak` revision in nano (read-only view). |
| `sentinel view <ID>` | `v2.0+` | Alias for `sentinel nano <ID>`. |
| `sentinel restore <ID>` | `v1.0+` | Restores revision `<ID>` with loop-coupling safety. |
| `sentinel diff <ID>` | `v1.0+` | Outputs unified diff of revision `<ID>` to stdout. |
| `sentinel init [MB]` | `v1.0+` | Initializes marker with size limit (defaults to T1..T6 in v2.0+). |
| `sentinel init [MB] [start] [end]` | `v2.0+` | Initializes marker with custom cascade range (e.g. `10 3 8`). |
| `sentinel markers` | `v1.0+` | Lists all active marked roots with size limits and active tiers. |
| `sentinel service install` | `v1.0+` | Installs and enables systemd background service. |
| `sentinel service restart` | `v1.0+` | Restarts systemd daemon (rescans all markers). |
| `sentinel service status` | `v1.0+` | Displays systemd service status. |
| `sentinel version` | `v1.0+` | Displays version, copyright, and SPDX license info. |
| `sentinel help` | `v1.0+` | Displays full interactive manual. |

---

## Storage & Configuration [v1.0.1 & v2.0.0]

### Linux FHS Standard Paths:
- **Root Daemon:** `/var/lib/shadow-sentinel/`
- **User Daemon:** `~/.local/share/shadow-sentinel/`

### Custom Storage Redirection (`/etc/shadow-sentinel/config.json`):
To store backups, vaults, and indices in a custom directory (e.g. a separate SSD or network mount),
create `/etc/shadow-sentinel/config.json` (for root) or `~/.config/shadow-sentinel/config.json` (for user):

```json
{
    "storage_dir": "/mnt/external_volume/sentinel_vault"
}
```

### Environment Variable Override:
```bash
export SENTINEL_STORAGE_DIR=/mnt/external_volume/sentinel_vault
```
