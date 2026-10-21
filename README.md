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

## Dual-Version Architecture & Documentation Notice

This documentation serves as the Single Source of Truth (SSOT) for both production releases:
- **Version 1.0.1 (Stable Baseline)**: Deployed on production servers via PyPI package `1.0.1`.
- **Version 2.0.0 (Major Release)**: Advanced interactive TUI, decade cascade, and nano viewer.

Every section and feature below is explicitly tagged with its supported version.

---

## Version Comparison Matrix

| Architectural Feature | Version 1.0.1 (Baseline) | Version 2.0.0 (Current Major) |
| :--- | :--- | :--- |
| **Kernel inotify (libc.so.6 ctypes)** | Yes (Zero dependencies) | Yes (Zero dependencies) |
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
| **Direct File Inspection** | CLI / external editor | Direct read-only nano view (`sentinel nano`) |
| **File Type Classification** | Plain text paths | Functional extension icons (`📚`, `🐍`, etc.) |
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

## Detailed Feature Breakdown by Version

### Feature 1: Kernel inotify & Zero Dependencies [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Description:** Direct C bindings to standard Linux `libc.so.6` using Python's built-in `ctypes`.
  Does not require external tools (`inotifywait`), third-party daemons, or compiler toolchains.
  Runs out-of-the-box on Python 3.9+.

### Feature 2: Decentralized Marker Control [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Syntax in v1.0.1:** Single parameter:
  ```text
  <max_file_size_mb>
  ```
  Example: `5` creates a 5 MB ceiling. Monitored subdirectories inherit this setting.
- **Syntax in v2.0.0:** Up to three parameters:
  ```text
  <max_file_size_mb> [start_tier] [end_tier]
  ```
  Example: `5 1 6` (5 MB, Tiers 1 through 6).
  Example: `50 3 8` (50 MB, Tiers 3 to 8 only — skips 3s/30s high-frequency churn for DB files).

### Feature 3: Nested Subfolder Overrides [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only (v1.0.1 uses parent inheritance).
- **Description:** If a subfolder contains its own `sentinel_marker`, that subfolder completely
  overrides the parent policy. Sentinel resolves the most specific rule using longest prefix matching.

### Feature 4: Dynamic Size Ceiling & Vault Ejection [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Description:** Prevents server disk exhaustion from runaway logs or binary dumps.
  If a monitored file grows past the configured MB ceiling in `sentinel_marker`:
  1. The file is excluded from future backups.
  2. If the file was previously stored in the shadow vault, it is **immediately deleted from the vault**
     to reclaim storage space in real time.

### Feature 5: Loop-Coupled Undo-Safe Restores [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Description:** Running `sentinel restore <ID>` copies the historic `.bak` file over the target file.
  Because Sentinel's daemon is actively monitoring the directory, this restore write triggers
  an inotify event that captures the state *before the restore* as a brand-new backup.
  Restoring the wrong revision can never destroy data; any restore can be reverted immediately.

### Feature 6: Retroactive Legacy Backup Onboarding [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Description:** When Sentinel boots or displays history, it automatically scans the backup directory
  for pre-existing `.bak` files from previous runs and catalogs them with assigned IDs.

### Feature 7: Flapping & Cooldown Debounce [v1.0.1 & v2.0.0]
- **Supported in:** Version 1.0.1 and Version 2.0.0.
- **Description:** Rapid consecutive write events to the same file are debounced with a 3-second
  quiet window. An application writing 50 chunks over 2 seconds generates exactly 1 clean backup
  of the pre-write state rather than 50 corrupt intermediate fragments.

### Feature 8: Decade-Tier Cascade Ring Buffers [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only (v1.0.1 uses a flat 10-revision FIFO buffer).
- **Description:** Organizes revisions into geometric decade intervals ($3 \times 10^{(k-1)}$ seconds):
  - **Tier 1 (3s):** Immediate typos and terminal misclicks (spans 30 seconds).
  - **Tier 2 (30s):** Rapid script loops and syntax breakages (spans 5 minutes).
  - **Tier 3 (300s):** 5-minute session checkpoints (spans 50 minutes).
  - **Tier 4 (3,000s):** 50-minute work shift states (spans 8.3 hours / full workday).
  - **Tier 5 (30,000s):** 8.3-hour multi-shift states (spans 3.5 days / full weekend).
  - **Tier 6 (300,000s):** 3.5-day milestones (spans over 35 days / full month).
  - **Tier 7 (3,000,000s):** ~35-day milestones (spans ~350 days / 1 year).
  - **Tier 8 (30,000,000s):** ~350-day milestones (spans ~9.5 years).
  - **Scales up to Tier 128.**
  Each active tier retains strictly up to 10 copies. If an AI agent loops 50 times in 5 minutes,
  Tiers 1 and 2 rotate, but Tiers 4, 5, and 6 retain the pristine pre-agent code.

### Feature 9: Interactive Guided Live-Filter Explorer (TUI) [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only (v1.0.1 prints non-interactive table).
- **Description:** Launching `sentinel` with no arguments in a terminal opens the guided explorer:
  - Dynamically reads terminal height (`shutil.get_terminal_size()`) to prevent scroll cutoffs.
  - **As-You-Type Live Search:** Type queries (`*.py`, `*conf*`, `T4`); match counter updates on
    every keystroke without pressing Enter. Backspace edits query in-place.
  - **Dual Mode:** Search by Filename/Path wildcard OR search by File Content (grep inside backups).
  - Execute restore, diff, view in nano, or change filters directly from the menu prompt.

### Feature 10: Direct Read-Only Nano Viewer [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only.
- **Description:** Inspect any historical `.bak` file inside nano (`sentinel nano <ID>`).
  Opens nano in read-only view mode (`nano -v`) to prevent accidental corruption of backup vaults.
  Exiting nano (`Ctrl+X`) returns directly to the terminal explorer.

### Feature 11: Extension-Based File Classification Icons [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only (v1.0.1 displays plain text paths).
- **Description:** Categorizes revisions visually in tables:
  - `🐍` Python (`.py`, `.pyw`)
  - `🐚` Shell Scripts (`.sh`, `.bash`, `.zsh`)
  - `📚` Markdown & Documentation (`.md`)
  - `🗄️` Databases (`.db`, `.sqlite`, `.sql`, `.db-wal`)
  - `⚙️` Configs (`.json`, `.yaml`, `.toml`, `.conf`, `.ini`, `.env`)
  - `📋` Logs (`.log`, `.out`, `.err`)
  - `📝` Plain Text (`.txt`, `.csv`, `.rst`)

### Feature 12: Self-Healing Catalog Index [v2.0.0 Only]
- **Supported in:** Version 2.0.0 only.
- **Description:** On every index load, Sentinel cross-verifies that physical backup files exist
  on disk. If the auto-pruner purged an old file, ghost records are instantly purged from the catalog.

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
| `sentinel markers` | `v1.0+` | Lists active marked roots with size limits and active tiers. |
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
