#!/usr/bin/env python3
# ==============================================================================
# SPDX-License-Identifier: CC-BY-SA-3.0
#
# Shadow Sentinel - Autonomous OS-Level Revision & Backup Guard
#
# Copyright (c) 2026 automatician (Torsten Frieser), Germany / Saxony / Zittau.
# All rights reserved.
#
# Licensed under the Creative Commons Attribution-ShareAlike 3.0 Germany
# (CC BY-SA 3.0 DE). You may redistribute and modify this software under the
# terms of the CC BY-SA 3.0 license.
# ==============================================================================

"""
Shadow Sentinel Core Engine v2.0.1
Interactive Guided ASCII Explorer with Nano Viewer, Decade Cascade & Marker Migration
"""

import os
import sys
import time
import json
import shutil
import hashlib
import difflib
import ctypes
import struct
import select
import signal
import re
import fnmatch
import subprocess
import urllib.request

try:
    import termios
    import tty
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

__version__   = "2.0.1"
__author__    = "automatician (Torsten Frieser)"
__copyright__ = "Copyright (c) 2026 automatician (Torsten Frieser), Germany / Saxony / Zittau"
__license__   = "CC-BY-SA-3.0"

# Satte Farbpalette: Eis-Weiss (mit Blauanteil), Kraeftiges Leucht-Blau, Reingelb
CLR_RESET    = "\033[0m"
CLR_ICE      = "\033[38;5;195m"       # Echtes Eis-Weiss (arktisch-helles Weiss)
CLR_LUM_BLUE = "\033[38;5;33m"        # Kraeftiges, leuchtendes Dunkelblau
CLR_CYAN     = "\033[38;5;33m"        # Alias fuer Leucht-Blau
CLR_YELLOW   = "\033[38;5;220m"       # Satte gelbe Ziffern
CLR_GREEN    = "\033[38;5;82m"        # Sattes Gruen
CLR_GRAY     = "\033[38;5;244m"
CLR_DIM      = "\033[2m"

def get_storage_dirs():
    env_dir = os.getenv("SENTINEL_STORAGE_DIR")
    if env_dir:
        base = os.path.abspath(env_dir)
    else:
        cfg_file = "/etc/shadow-sentinel/config.json" if os.geteuid() == 0 else os.path.expanduser("~/.config/shadow-sentinel/config.json")
        custom_base = None
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "storage_dir" in data:
                        custom_base = data["storage_dir"]
            except Exception:
                pass

        if custom_base:
            base = os.path.abspath(custom_base)
        elif os.geteuid() == 0:
            base = "/var/lib/shadow-sentinel"
        else:
            base = os.path.expanduser("~/.local/share/shadow-sentinel")

    backup_dir = os.path.join(base, "backups")
    vault_dir  = os.path.join(base, ".shadow_vault")
    index_file = os.path.join(backup_dir, "sentinel_index.json")
    return base, backup_dir, vault_dir, index_file

CENTRAL_BASE, BACKUP_DIR, VAULT_DIR, INDEX_FILE = get_storage_dirs()

MAX_COPIES_PER_TIER  = 10
MAX_ALLOWED_TIERS    = 128
DEFAULT_START_TIER   = 1
DEFAULT_END_TIER     = 4       # Standard T1..T4
DEFAULT_MAX_FILE_MB  = 5
MAX_LOG_AGE_DAYS     = 30
MAX_BACKUP_DIR_MB    = 500
PRUNE_INTERVAL_SEC   = 21600
COOLDOWN_SEC         = 3

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)

libc = ctypes.CDLL("libc.so.6", use_errno=True)

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM  = 0x00000040
IN_MOVED_TO    = 0x00000080
IN_CREATE      = 0x00000100
IN_DELETE      = 0x00000200
IN_ISDIR       = 0x40000000

EVENT_MASK = IN_CLOSE_WRITE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE

running = True
last_prune_ts = 0
pending_writes = {}
marker_targets = {}  # {abs_dir: (max_size_bytes, start_tier, end_tier)}
tier_last_snapshot = {}  # {(abs_path, tier_num): timestamp}

def get_file_type_icon(filename: str) -> str:
    fname = filename.lower()
    if fname.endswith(('.py', '.pyw')):
        return '🐍'
    if fname.endswith(('.sh', '.bash', '.zsh')):
        return '🐚'
    if fname.endswith('.md'):
        return '📚'
    if fname.endswith(('.txt', '.rst', '.csv')):
        return '📝'
    if fname.endswith(('.db', '.sqlite', '.sqlite3', '.sql', '.db-wal', '.db-shm')):
        return '🗄️'
    if fname.endswith(('.json', '.yaml', '.yml', '.toml', '.conf', '.cfg', '.ini', '.env', '.xml')):
        return '⚙️'
    if fname.endswith(('.log', '.out', '.err')):
        return '📋'
    return '📄'

def signal_handler(sig, frame):
    global running
    print(f"\n[SENTINEL] Signal {sig} received. Terminating guard service...")
    running = False

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def is_sentinel_internal(path: str) -> bool:
    abs_p = os.path.abspath(path)
    if abs_p == BACKUP_DIR or abs_p.startswith(BACKUP_DIR + os.sep):
        return True
    if abs_p == VAULT_DIR or abs_p.startswith(VAULT_DIR + os.sep):
        return True
    if abs_p == "/etc/shadow-sentinel" or abs_p.startswith("/etc/shadow-sentinel" + os.sep):
        return True
    return False

def get_tier_interval(tier_k: int) -> int:
    if tier_k < 1:
        tier_k = 1
    if tier_k > MAX_ALLOWED_TIERS:
        tier_k = MAX_ALLOWED_TIERS
    return 3 * (10 ** (tier_k - 1))

def get_tier_retention_days(tier_num: int) -> int:
    if tier_num <= 4:
        return 14       # 2 Wochen (T1-T4)
    elif tier_num <= 9:
        return 60       # 2 Monate (T5-T9)
    else:
        return 365      # 12 Monate (T10+)

def parse_marker_file(mpath: str) -> tuple:
    size_mb = DEFAULT_MAX_FILE_MB
    start_tier = DEFAULT_START_TIER
    end_tier = DEFAULT_END_TIER
    try:
        content = ""
        with open(mpath, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            with open(mpath, "w", encoding="utf-8") as f:
                f.write(f"{DEFAULT_MAX_FILE_MB} {DEFAULT_START_TIER} {DEFAULT_END_TIER}\n")
            return size_mb, start_tier, end_tier

        parts = re.split(r"[\s,]+", content)
        if len(parts) >= 1 and parts[0]:
            p1 = int(float(parts[0]))
            if p1 > 0:
                size_mb = p1

        if len(parts) == 2 and parts[1]:
            p2 = int(parts[1])
            if 1 <= p2 <= MAX_ALLOWED_TIERS:
                start_tier = 1
                end_tier = p2
        elif len(parts) >= 3:
            p_start = int(parts[1])
            p_end = int(parts[2])
            if 1 <= p_start <= MAX_ALLOWED_TIERS:
                start_tier = p_start
            if 1 <= p_end <= MAX_ALLOWED_TIERS:
                end_tier = p_end
            if start_tier > end_tier:
                start_tier, end_tier = end_tier, start_tier
    except Exception:
        pass
    return size_mb, start_tier, end_tier

def check_and_upgrade_markers():
    """Findet alte 1-Parameter Marker und bietet Upgrade auf [MB 1 4] an."""
    m_list = []
    cmd = ["find", "/", "-name", "sentinel_marker", "-o", "-name", ".sentinel_marker"]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        m_list = [l.strip() for l in res.stdout.splitlines() if l.strip()]
    except Exception:
        pass

    for mp in m_list:
        if is_sentinel_internal(mp) or not os.path.isfile(mp):
            continue
        try:
            with open(mp, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            parts = re.split(r"[\s,]+", raw) if raw else []
            if len(parts) < 3:
                # Altes Format erkannt!
                cur_mb = parts[0] if len(parts) >= 1 and parts[0] else str(DEFAULT_MAX_FILE_MB)
                print(f"\n{CLR_YELLOW}[MIGRATION HINWEIS]{CLR_RESET} Marker in {CLR_ICE}{mp}{CLR_RESET} hat altes Format ({raw or 'leer'}).")
                ans = input(f"Auf v2.x Standard '{cur_mb} 1 4' aktualisieren? [Y/n]: ").strip().lower()
                if ans in ("", "y", "ja", "yes"):
                    with open(mp, "w", encoding="utf-8") as f:
                        f.write(f"{cur_mb} 1 4\n")
                    print(f"{CLR_GREEN}✓ Marker aktualisiert:{CLR_RESET} {cur_mb} MB | Tiers T1..T4")
        except Exception:
            pass

def resolve_bak_path(bak_file: str) -> str:
    candidates = [
        os.path.join(BACKUP_DIR, bak_file),
        os.path.join("/opt/admin-agent/backups", bak_file),
        os.path.join(CENTRAL_BASE, "backups", bak_file)
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def load_index() -> list:
    entries = []
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    # Self-Healing: Geister-Eintraege physisch geloeschter Dateien entfernen
    valid_entries = []
    modified = False
    for item in entries:
        bp = resolve_bak_path(item.get("bak_file", ""))
        if os.path.exists(bp):
            valid_entries.append(item)
        else:
            modified = True
    entries = valid_entries

    existing_baks = {item.get("bak_file") for item in entries}
    pattern = re.compile(r"^(.*?)\.(T\d+)\.(\d{8}_\d{6})\.(bak|deleted\.bak)$")
    legacy_pattern = re.compile(r"^(.*?)\.(\d{8}_\d{6})\.(bak|deleted\.bak)$")

    if os.path.exists(BACKUP_DIR):
        for fname in sorted(os.listdir(BACKUP_DIR)):
            if fname in existing_baks:
                continue

            tier_label = "T1"
            ts_str = ""
            orig_name = ""

            m_tier = pattern.match(fname)
            if m_tier:
                orig_name = m_tier.group(1)
                tier_label = m_tier.group(2)
                ts_str = m_tier.group(3)
            else:
                m_leg = legacy_pattern.match(fname)
                if m_leg:
                    orig_name = m_leg.group(1)
                    tier_label = "T1"
                    ts_str = m_leg.group(2)
                else:
                    continue

            fpath = os.path.join(BACKUP_DIR, fname)
            orig_path = os.path.join(CENTRAL_BASE, orig_name)
            diff_file = fname.replace(".bak", ".diff")
            if not os.path.exists(os.path.join(BACKUP_DIR, diff_file)):
                diff_file = ""

            try:
                formatted_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.strptime(ts_str, "%Y%m%d_%H%M%S"))
            except Exception:
                formatted_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(fpath)))

            entries.append({
                "id": len(entries) + 1,
                "orig_path": os.path.abspath(orig_path),
                "bak_file": fname,
                "diff_file": diff_file,
                "tier": tier_label,
                "timestamp": formatted_ts,
                "size_bytes": os.path.getsize(fpath)
            })
            existing_baks.add(fname)
            modified = True

    if modified or not os.path.exists(INDEX_FILE):
        entries.sort(key=lambda x: x.get("timestamp", ""))
        for idx, item in enumerate(entries, 1):
            item["id"] = idx
        save_index(entries)

    return entries

def save_index(index_list: list):
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index_list, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[SENTINEL-INDEX-ERR] {e}")

def record_backup(orig_path: str, bak_name: str, diff_name: str, size_bytes: int, tier_label: str):
    idx = load_index()
    next_id = max([item.get("id", 0) for item in idx], default=0) + 1

    entry = {
        "id": next_id,
        "orig_path": os.path.abspath(orig_path),
        "bak_file": bak_name,
        "diff_file": diff_name,
        "tier": tier_label,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "size_bytes": size_bytes
    }
    idx.append(entry)
    save_index(idx)

def discover_markers() -> dict:
    targets = {}
    cmd = ["find", "/", "-name", "sentinel_marker", "-o", "-name", ".sentinel_marker"]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"[SENTINEL] Find error: {e}")
        lines = []

    for mpath in lines:
        if not os.path.isfile(mpath):
            continue
        watch_root = os.path.abspath(os.path.dirname(mpath))
        if is_sentinel_internal(watch_root):
            continue

        size_mb, start_tier, end_tier = parse_marker_file(mpath)
        targets[watch_root] = (size_mb * 1024 * 1024, start_tier, end_tier)

    return targets

def find_nearest_marker(start_dir: str):
    cur = os.path.abspath(start_dir)
    while True:
        m1 = os.path.join(cur, "sentinel_marker")
        m2 = os.path.join(cur, ".sentinel_marker")
        if os.path.isfile(m1):
            return cur, m1
        if os.path.isfile(m2):
            return cur, m2
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None, None

def get_sha256(filepath: str) -> str:
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def is_monitored_file(path: str) -> bool:
    base = os.path.basename(path)
    if base in ("sentinel_marker", ".sentinel_marker"):
        return False
    if is_sentinel_internal(path):
        return False
    return True

def get_vault_path(abs_path: str) -> str:
    clean_path = os.path.abspath(abs_path).lstrip("/")
    return os.path.join(VAULT_DIR, clean_path)

def get_params_for_file(abs_path: str) -> tuple:
    matched_root = None
    matched_params = (DEFAULT_MAX_FILE_MB * 1024 * 1024, DEFAULT_START_TIER, DEFAULT_END_TIER)
    abs_p = os.path.abspath(abs_path)
    for root, params in marker_targets.items():
        if abs_p == root or abs_p.startswith(root + "/"):
            if matched_root is None or len(root) > len(matched_root):
                matched_root = root
                matched_params = params
    return matched_params

def auto_prune_backups():
    global last_prune_ts
    now = time.time()
    last_prune_ts = now

    deleted_count = 0
    freed_bytes = 0

    pattern = re.compile(r"^(.*?)\.(T\d+)\.(\d{8}_\d{6})\.(bak|diff|deleted\.bak)$")
    file_groups = {}

    for fname in os.listdir(BACKUP_DIR):
        fpath = os.path.join(BACKUP_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        if fname.startswith("diff-") and fname.endswith(".log"):
            try:
                st = os.stat(fpath)
                if (now - st.st_mtime) > (MAX_LOG_AGE_DAYS * 86400):
                    freed_bytes += st.st_size
                    os.remove(fpath)
                    deleted_count += 1
            except Exception:
                pass
            continue

        match = pattern.match(fname)
        if match:
            orig_name = match.group(1)
            tier_tag = match.group(2)
            ext_type = match.group(4)
            key = (orig_name, tier_tag, ext_type)
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append((fname, fpath, os.path.getmtime(fpath), os.path.getsize(fpath)))

    # Haltedauer: T1-T4 = 14d, T5-T9 = 60d, T10+ = 365d
    for key, items in file_groups.items():
        orig_name, tier_tag, ext_type = key
        try:
            tier_num = int(tier_tag.replace("T", ""))
        except Exception:
            tier_num = 1

        tier_retention_sec = get_tier_retention_days(tier_num) * 86400

        items.sort(key=lambda x: x[2], reverse=True)
        for idx, (fname, fpath, mtime, size) in enumerate(items):
            should_prune = False
            if idx >= MAX_COPIES_PER_TIER:
                should_prune = True
            elif idx > 0 and (now - mtime) > tier_retention_sec:
                should_prune = True

            if should_prune:
                try:
                    os.remove(fpath)
                    deleted_count += 1
                    freed_bytes += size
                    diff_twin = fpath.replace(".bak", ".diff")
                    if os.path.exists(diff_twin):
                        try:
                            os.remove(diff_twin)
                        except Exception:
                            pass
                except Exception:
                    pass

    # 500 MB Notbremse
    total_size = sum(os.path.getsize(os.path.join(BACKUP_DIR, f)) for f in os.listdir(BACKUP_DIR) if os.path.isfile(os.path.join(BACKUP_DIR, f)))
    max_bytes = MAX_BACKUP_DIR_MB * 1024 * 1024

    if total_size > max_bytes:
        all_backups = []
        for fname in os.listdir(BACKUP_DIR):
            fpath = os.path.join(BACKUP_DIR, fname)
            if os.path.isfile(fpath):
                all_backups.append((fpath, os.path.getmtime(fpath), os.path.getsize(fpath)))
        all_backups.sort(key=lambda x: x[1])
        for fpath, _, size in all_backups:
            if total_size <= max_bytes * 0.8:
                break
            try:
                os.remove(fpath)
                total_size -= size
                freed_bytes += size
                deleted_count += 1
            except Exception:
                pass

    if deleted_count > 0:
        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        print(f"[PRUNE] Cascade pruning complete: {deleted_count} versions cleaned ({freed_mb} MB freed).")

def sync_initial_vault():
    count = 0
    ejected_count = 0

    for root_dir, (max_bytes, _, _) in marker_targets.items():
        if not os.path.exists(root_dir) or is_sentinel_internal(root_dir):
            continue
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if not is_sentinel_internal(os.path.join(root, d))]
            for f in files:
                full_path = os.path.join(root, f)
                if not is_monitored_file(full_path):
                    continue

                try:
                    cur_size = os.path.getsize(full_path)
                except Exception:
                    continue

                vault_path = get_vault_path(full_path)

                if cur_size > max_bytes:
                    if os.path.exists(vault_path):
                        try:
                            os.remove(vault_path)
                            ejected_count += 1
                        except Exception:
                            pass
                    continue

                os.makedirs(os.path.dirname(vault_path), exist_ok=True)
                if not os.path.exists(vault_path) or get_sha256(full_path) != get_sha256(vault_path):
                    shutil.copy2(full_path, vault_path)
                    count += 1

    print(f"[VAULT] Sync complete: {count} active files tracked ({ejected_count} oversized files ejected).")
    auto_prune_backups()

def handle_file_written(abs_path: str):
    if not os.path.exists(abs_path) or not is_monitored_file(abs_path):
        return

    vault_path = get_vault_path(abs_path)
    max_bytes, start_tier, end_tier = get_params_for_file(abs_path)

    try:
        cur_size = os.path.getsize(abs_path)
    except Exception:
        return

    if cur_size > max_bytes:
        if os.path.exists(vault_path):
            try:
                os.remove(vault_path)
                size_mb = round(cur_size / (1024 * 1024), 2)
                limit_mb = round(max_bytes / (1024 * 1024), 1)
                print(f"[VAULT-EJECT] Ceiling exceeded ({size_mb} MB > {limit_mb} MB): {abs_path}")
            except Exception:
                pass
        return

    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    new_hash = get_sha256(abs_path)
    if not new_hash:
        return

    ts = time.strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(abs_path)
    now = time.time()

    if os.path.exists(vault_path):
        old_hash = get_sha256(vault_path)
        if old_hash != new_hash:
            for k in range(start_tier, end_tier + 1):
                tier_interval = get_tier_interval(k)
                last_shot = tier_last_snapshot.get((abs_path, k), 0)

                if (now - last_shot) >= tier_interval:
                    bak_name = f"{base_name}.T{k}.{ts}.bak"
                    bak_path = os.path.join(BACKUP_DIR, bak_name)
                    shutil.copy2(vault_path, bak_path)

                    diff_name = f"{base_name}.T{k}.{ts}.diff"
                    diff_path = os.path.join(BACKUP_DIR, diff_name)
                    try:
                        with open(vault_path, "r", encoding="utf-8", errors="replace") as fo, \
                             open(abs_path, "r", encoding="utf-8", errors="replace") as fn:
                            old_lines = fo.readlines()
                            new_lines = fn.readlines()
                        diff = list(difflib.unified_diff(
                            old_lines, new_lines,
                            fromfile=f"CURRENT: {abs_path}",
                            tofile=f"TARGET: {abs_path}",
                            lineterm="\n"
                        ))
                        if diff:
                            with open(diff_path, "w", encoding="utf-8") as df:
                                df.write(f"=== AUTO-DIFF (T{k}): {abs_path} ===\n")
                                df.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} | Interval: {tier_interval}s\n\n")
                                df.writelines(diff)
                    except Exception:
                        diff_name = ""

                    record_backup(abs_path, bak_name, diff_name, cur_size, f"T{k}")
                    tier_last_snapshot[(abs_path, k)] = now
                    print(f"[BACKUP-T{k}] {abs_path} -> {bak_name}")

            shutil.copy2(abs_path, vault_path)
    else:
        shutil.copy2(abs_path, vault_path)
        print(f"[VAULT-NEW] {abs_path}")

def handle_file_deleted(abs_path: str):
    if not is_monitored_file(abs_path):
        return

    vault_path = get_vault_path(abs_path)
    base_name = os.path.basename(abs_path)
    _, start_tier, _ = get_params_for_file(abs_path)

    if os.path.exists(vault_path):
        ts = time.strftime("%Y%m%d_%H%M%S")
        del_bak = f"{base_name}.T{start_tier}.{ts}.deleted.bak"
        bak_path = os.path.join(BACKUP_DIR, del_bak)
        shutil.copy2(vault_path, bak_path)

        record_backup(abs_path, del_bak, "", 0, f"T{start_tier}")
        os.remove(vault_path)
        print(f"[DELETION] {abs_path} -> {del_bak}")

def open_in_nano(target_path: str):
    if not os.path.exists(target_path):
        print(f"[ERROR] File does not exist: {target_path}")
        return
    try:
        subprocess.run(["nano", "-v", target_path])
    except Exception:
        try:
            subprocess.run(["nano", target_path])
        except Exception as e:
            print(f"[ERROR] Could not launch nano: {e}")

def run_daemon():
    global last_prune_ts, pending_writes, marker_targets
    marker_targets = discover_markers()

    print(f"[DAEMON] Guard active v{__version__}. Storage: {CENTRAL_BASE}")
    for root, (max_bytes, start_tier, end_tier) in marker_targets.items():
        print(f"  * {root} [Limit: {max_bytes // (1024*1024)} MB | Active Tiers: T{start_tier}..T{end_tier}]")

    sync_initial_vault()

    inotify_fd = libc.inotify_init1(0)
    if inotify_fd < 0:
        print("[ERROR] inotify_init1 failed!")
        sys.exit(1)

    wd_to_dir = {}

    def add_watch_recursive(path: str):
        if not os.path.exists(path) or is_sentinel_internal(path):
            return
        for root, dirs, _ in os.walk(path):
            dirs[:] = [d for d in dirs if not is_sentinel_internal(os.path.join(root, d))]
            wd = libc.inotify_add_watch(inotify_fd, root.encode("utf-8"), EVENT_MASK)
            if wd >= 0:
                wd_to_dir[wd] = root

    for p in marker_targets.keys():
        add_watch_recursive(p)

    print(f"[DAEMON] Watching {len(wd_to_dir)} directories recursively.")

    poll = select.poll()
    poll.register(inotify_fd, select.POLLIN)

    while running:
        try:
            now = time.time()
            if now - last_prune_ts > PRUNE_INTERVAL_SEC:
                auto_prune_backups()

            if pending_writes:
                ready_to_write = []
                for fpath, (first_ts, last_ts) in list(pending_writes.items()):
                    if (now - last_ts >= COOLDOWN_SEC) or (now - first_ts >= 30.0):
                        ready_to_write.append(fpath)

                for fpath in ready_to_write:
                    del pending_writes[fpath]
                    handle_file_written(fpath)

            events = poll.poll(500)
            if not events:
                continue

            raw = os.read(inotify_fd, 65536)
            offset = 0
            while offset < len(raw):
                wd, mask, cookie, length = struct.unpack_from("iIII", raw, offset)
                offset += 16
                name = raw[offset:offset + length].rstrip(b"\x00").decode("utf-8", errors="replace")
                offset += length

                dir_path = wd_to_dir.get(wd)
                if not dir_path or not name:
                    continue

                full_path = os.path.join(dir_path, name)

                if mask & IN_ISDIR:
                    if (mask & (IN_CREATE | IN_MOVED_TO)) and not is_sentinel_internal(full_path):
                        new_wd = libc.inotify_add_watch(inotify_fd, full_path.encode("utf-8"), EVENT_MASK)
                        if new_wd >= 0:
                            wd_to_dir[new_wd] = full_path
                    continue

                if mask & (IN_CLOSE_WRITE | IN_MOVED_TO):
                    if COOLDOWN_SEC <= 0:
                        handle_file_written(full_path)
                    else:
                        event_time = time.time()
                        if full_path in pending_writes:
                            pending_writes[full_path] = (pending_writes[full_path][0], event_time)
                        else:
                            pending_writes[full_path] = (event_time, event_time)

                elif mask & (IN_DELETE | IN_MOVED_FROM):
                    if full_path in pending_writes:
                        del pending_writes[full_path]
                    handle_file_deleted(full_path)

        except Exception as e:
            if running:
                print(f"[ERROR] {e}")
                time.sleep(1)

    if pending_writes:
        for fpath in list(pending_writes.keys()):
            handle_file_written(fpath)
        pending_writes.clear()

    os.close(inotify_fd)
    print("[DAEMON] Stopped.")

def manage_service(action: str):
    service_file = "/etc/systemd/system/shadow-sentinel.service"
    py_exec = shutil.which("python3") or sys.executable

    # ZOMBIE-KILLER: Beendet vor jeder Dienst-Aktion alle alten Geister-Prozesse
    if action in ("install", "restart", "start"):
        try:
            subprocess.run(["pkill", "-9", "-f", "mre_filesystem_sentinel.py"], stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "test_user_env"], stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "shadow_sentinel.core"], stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "stop", "mre_filesystem_sentinel"], stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "disable", "mre_filesystem_sentinel"], stderr=subprocess.DEVNULL)
        except Exception:
            pass

    if action == "install":
        content = f"""[Unit]
Description=Shadow Sentinel - Autonomous Filesystem Revision & Backup Guard
After=network.target

[Service]
Type=simple
ExecStart={py_exec} -m shadow_sentinel.core daemon
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        try:
            with open(service_file, "w", encoding="utf-8") as f:
                f.write(content)
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "enable", "--now", "shadow-sentinel"], check=True)
            print(f"[SERVICE] Installed and started cleanly: {service_file}")
        except Exception as e:
            print(f"[ERROR] Service install failed: {e}")

    elif action in ("status", "restart", "stop", "start"):
        if action == "restart":
            manage_service("install")
        else:
            subprocess.run(["systemctl", action, "shadow-sentinel"])

def print_version():
    print(f"Shadow Sentinel v{__version__}")
    print(f"{__copyright__}")
    print(f"License: {__license__} (Creative Commons Attribution-ShareAlike 3.0 Germany)")
    print("Project: https://github.com/automatician/shadow-sentinel")

def fetch_release_notes(ver: str) -> dict:
    local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release_notes", f"v{ver}.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"https://raw.githubusercontent.com/automatician/shadow-sentinel/main/release_notes/v{ver}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "shadow-sentinel-cli"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}

def show_whats_new(target_version=None):
    ver = target_version or __version__
    data = fetch_release_notes(ver)

    div = f"{CLR_ICE}{'─' * 83}{CLR_RESET}"
    print(f"\n{div}")
    print(f" {CLR_LUM_BLUE}Shadow Sentinel v{ver}{CLR_RESET}  {CLR_DIM}Release Notes & Patch Highlights{CLR_RESET}")
    print(f"{div}")

    if not data:
        print(f"  {CLR_YELLOW}No patch notes found for v{ver}. Visit: https://github.com/automatician/shadow-sentinel{CLR_RESET}")
    else:
        print(f"  {CLR_ICE}Title:{CLR_RESET}        {CLR_CYAN}{data.get('title', 'Maintenance Release')}{CLR_RESET}")
        print(f"  {CLR_ICE}Date:{CLR_RESET}         {CLR_DIM}{data.get('date', 'Recent')}{CLR_RESET}")
        print(f"\n  {CLR_ICE}What was fixed & improved:{CLR_RESET}")
        for item in data.get("highlights", []):
            print(f"    {CLR_GREEN}•{CLR_RESET} {item}")
        print(f"\n  {CLR_ICE}Upgrade:{CLR_RESET}      {CLR_CYAN}{data.get('upgrade_command', 'pip install --upgrade shadow-sentinel')}{CLR_RESET}")
    print(f"{div}\n")

def check_for_updates():
    try:
        url = "https://pypi.org/pypi/shadow-sentinel/json"
        req = urllib.request.Request(url, headers={"User-Agent": "shadow-sentinel-cli"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode())
            latest_v = data.get("info", {}).get("version")
            def parse_v(v):
                return [int(x) for x in re.findall(r'\d+', v)]
            if latest_v and parse_v(latest_v) > parse_v(__version__):
                notes = fetch_release_notes(latest_v)
                print(f"\n{CLR_YELLOW}───────────────────────────────────────────────────────────────────────────────────{CLR_RESET}")
                print(f"  {CLR_ICE}[UPDATE AVAILABLE]{CLR_RESET} New version on PyPI: {CLR_CYAN}v{__version__}{CLR_RESET} ➔ {CLR_GREEN}v{latest_v}{CLR_RESET}")
                if notes and "highlights" in notes:
                    print(f"  {CLR_ICE}Patch highlights in v{latest_v}:{CLR_RESET}")
                    for h in notes.get("highlights", [])[:3]:
                        print(f"    {CLR_GREEN}•{CLR_RESET} {h}")
                print(f"  {CLR_ICE}Upgrade command:{CLR_RESET}   {CLR_CYAN}pip install --upgrade shadow-sentinel && sentinel service restart{CLR_RESET}")
                print(f"  {CLR_DIM}Run 'sentinel whatsnew' for full changelog details.{CLR_RESET}")
                print(f"{CLR_YELLOW}───────────────────────────────────────────────────────────────────────────────────{CLR_RESET}\n")
    except Exception:
        pass

def show_help():
    manual = f"""
====================================================================================================
SHADOW SENTINEL v{__version__} - INTERACTIVE DECADE-TIER CASCADE REVISION GUARD
====================================================================================================

VERSION & LICENSE
  Version:     v{__version__}
  Author:      {__author__}
  Copyright:   {__copyright__}
  License:     {__license__} (Creative Commons Attribution-ShareAlike 3.0 DE)
  Repository:  https://github.com/automatician/shadow-sentinel

DECADE-TIER CASCADE ARCHITECTURE
  Sentinel organizes backups into geometric decade ring buffers (powers of 10):
    - T1 (3s):       Immediate typos and script interruptions.
    - T2 (30s):      Micro crashes and loop bugs.
    - T3 (300s):     5-minute session checkpoints.
    - T4 (3000s):    50-minute work shift states (full 8.3h workday span).
    - T5 (30000s):   8.3-hour multi-shift / weekend anchors.
    - T6 (300000s):  3.5-day milestones covering over a month (35+ days).
    - Up to T128:    Configurable decades scaling up to years and decades.

MARKER HIERARCHY & RANGE SYNTAX
  Drop 'sentinel_marker' in any root directory or nested subfolder:
    Format:  <max_size_mb> [start_tier] [end_tier]
    Example: 5 1 4   (5 MB limit, Tiers 1 through 4 active)
    Example: 50 3 8  (50 MB limit, Tiers 3 through 8 only - skips rapid 3s/30s spam)
  Nested subfolders automatically override parent settings via longest-prefix matching.

COMMANDS & WORKFLOWS
  sentinel                          Launches Interactive Guided Live-Filter Explorer.
  sentinel [filter_term]            Lists backup revisions. Filter by wildcard (*.py) or Tier (T4).
  sentinel nano <ID>                Opens the exact .bak file directly in nano (read-only view).
  sentinel view <ID>                Alias for 'sentinel nano <ID>'.
  sentinel restore <ID>             Restores revision <ID> with loop-coupling safety.
  sentinel diff <ID>                Outputs unified diff of revision <ID>.
  sentinel init [MB] [start] [end]  Creates 'sentinel_marker' (default: 5 1 4).
  sentinel markers                  Lists active marked roots with size limits and active tiers.
  sentinel whatsnew                 Displays patch notes and bugfixes for current/target release.
  sentinel service <cmd>            Manages systemd daemon: install | restart | status | stop | start.
  sentinel version                  Displays version, copyright, and license.
  sentinel help                     Displays this manual.

====================================================================================================
"""
    print(manual)

def render_table(items: list, nearest_root: str):
    header = f"{CLR_GRAY}{'─' * 102}{CLR_RESET}\n"
    header += f"{CLR_ICE}{'ID':<6} {'TIMESTAMP':<20} {'TIER':<8} {'FILE SIZE':<12} {'DIFF':<6} {'TYPE':<6} ORIGINAL PATH{CLR_RESET}\n"
    header += f"{CLR_GRAY}{'─' * 102}{CLR_RESET}"
    print(header)

    for item in reversed(items):
        diff_label = f"{CLR_GREEN}[YES]{CLR_RESET}" if item.get("diff_file") else f"{CLR_GRAY}[--]{CLR_RESET}"
        tier_label = f"{CLR_CYAN}[{item.get('tier', 'T1')}]{CLR_RESET}"
        size_kb = f"{round(item.get('size_bytes', 0) / 1024, 1)} KB"
        display_path = item["orig_path"]
        if nearest_root and display_path.startswith(nearest_root):
            display_path = os.path.relpath(display_path, nearest_root)
        type_icon = get_file_type_icon(display_path)
        print(f"[{item['id']}]   {item['timestamp']:<20} {tier_label:<17} {size_kb:<12} {diff_label:<15} {type_icon:<6} {display_path}")

    print(f"{CLR_GRAY}{'─' * 102}{CLR_RESET}")

def search_content_matches(pool: list, search_term: str) -> list:
    if not search_term or not os.path.exists(BACKUP_DIR):
        return []

    try:
        cmd = ["grep", "-l", "-F", "-m", "1", search_term]
        bak_files = [os.path.join(BACKUP_DIR, item["bak_file"]) for item in pool if item.get("bak_file")]
        if not bak_files:
            return []

        matched_filenames = set()
        chunk_size = 2000
        for i in range(0, len(bak_files), chunk_size):
            chunk = bak_files[i:i + chunk_size]
            res = subprocess.run(cmd + chunk, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            for line in res.stdout.splitlines():
                matched_filenames.add(os.path.basename(line.strip()))

        return [item for item in pool if item.get("bak_file") in matched_filenames]
    except Exception:
        results = []
        term_bytes = search_term.encode("utf-8", errors="ignore")
        for item in pool:
            fpath = os.path.join(BACKUP_DIR, item.get("bak_file", ""))
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "rb") as bf:
                        if term_bytes in bf.read():
                            results.append(item)
                except Exception:
                    pass
        return results

def live_as_you_type_filter(pool: list, search_mode: str) -> list:
    if not HAS_TERMIOS or not sys.stdin.isatty():
        val = input("> ").strip()
        if search_mode == "content":
            return search_content_matches(pool, val)
        return [item for item in pool if fnmatch.fnmatch(os.path.basename(item["orig_path"]).lower(), val.lower())]

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    query = ""
    matches = list(pool)
    mode_label = "Dateiname (*)" if search_mode == "filename" else "Volltext (Inhalt)"

    print()
    try:
        tty.setcbreak(fd)
        while True:
            if not query:
                matches = list(pool)
            else:
                if search_mode == "filename":
                    pattern = f"*{query.lower()}*" if "*" not in query else query.lower()
                    matches = [
                        item for item in pool
                        if fnmatch.fnmatch(os.path.basename(item["orig_path"]).lower(), pattern)
                        or fnmatch.fnmatch(item.get("tier", "").lower(), pattern)
                        or query.lower() in item["orig_path"].lower()
                    ]
                else:
                    if len(query) >= 3:
                        matches = search_content_matches(pool, query)
                    else:
                        matches = pool

            count_color = CLR_GREEN if len(matches) <= 45 else (CLR_YELLOW if len(matches) <= 200 else CLR_CYAN)

            status_line = f"  {CLR_ICE}[Modus: {mode_label}]{CLR_RESET}  {CLR_ICE}Funde: {count_color}{len(matches):,}{CLR_RESET}  {CLR_ICE}|{CLR_RESET}  {CLR_ICE}ENTER = Anzeigen  |  ESC = Abbruch{CLR_RESET}"
            input_line  = f"  {CLR_LUM_BLUE}>{CLR_RESET} {CLR_ICE}{query}{CLR_RESET}"

            UP = chr(27) + "[1A"
            CLEAR = chr(27) + "[K"
            sys.stdout.write(UP + chr(13) + CLEAR + status_line + chr(10) + chr(13) + CLEAR + input_line)
            sys.stdout.flush()

            ch = sys.stdin.read(1)

            if ch in ("\r", "\n"):
                sys.stdout.write(chr(10))
                sys.stdout.flush()
                return matches

            elif ch in ("\x7f", "\x08"):
                if len(query) > 0:
                    query = query[:-1]

            elif ch in ("\x03", "\x1b"):
                sys.stdout.write(chr(10))
                sys.stdout.flush()
                return []

            elif ord(ch) >= 32:
                query += ch

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def interactive_explorer():
    check_for_updates()
    check_and_upgrade_markers()

    cwd = os.getcwd()
    nearest_root, marker_path = find_nearest_marker(cwd)
    idx = load_index()

    div = f"{CLR_ICE}{'─' * 83}{CLR_RESET}"

    print(f"\n{div}")
    print(f" {CLR_LUM_BLUE}Shadow Sentinel v{__version__}{CLR_RESET}")
    print(f"{div}")

    if nearest_root:
        size_mb, start_t, end_t = parse_marker_file(marker_path)
        print(f"  {CLR_ICE}Context:{CLR_RESET}   {CLR_LUM_BLUE}{cwd}{CLR_RESET}")
        print(f"  {CLR_ICE}Root:{CLR_RESET}      {nearest_root} {CLR_ICE}[Limit: {size_mb} MB | Tiers: T{start_t}..T{end_t}]{CLR_RESET}")
        pool = [item for item in idx if item["orig_path"].startswith(nearest_root)]
    else:
        print(f"  {CLR_ICE}Context:{CLR_RESET}   {CLR_LUM_BLUE}{cwd}{CLR_RESET} {CLR_ICE}(Global Catalog){CLR_RESET}")
        pool = idx

    print(f"  {CLR_ICE}Catalog:{CLR_RESET}   {CLR_GREEN}{len(pool):,} backups tracked{CLR_RESET}")
    print(f"{div}")

    print(f"\n{CLR_ICE}Select:{CLR_RESET}")
    print(f"  {CLR_YELLOW}[1]{CLR_RESET} {CLR_ICE}Search by Filename / Path / Tier (Wildcards *.py, *conf*, T4){CLR_RESET}")
    print(f"  {CLR_YELLOW}[2]{CLR_RESET} {CLR_ICE}Search by File Content (Full-text in backups){CLR_RESET}")
    print(f"  {CLR_YELLOW}[A]{CLR_RESET} {CLR_ICE}Display all {len(pool):,} entries{CLR_RESET}")
    print(f"  {CLR_YELLOW}[Q]{CLR_RESET} {CLR_ICE}Quit{CLR_RESET}")

    choice = input(f"\n{CLR_ICE}Choice [1/2/A/Q]: {CLR_RESET}").strip().lower()

    if choice in ("q", "quit", "exit"):
        return

    if choice == "2":
        search_mode = "content"
    elif choice == "a":
        matches = list(pool)
        render_table(matches, nearest_root)
        action_subloop(pool, nearest_root)
        return
    else:
        search_mode = "filename"

    matches = live_as_you_type_filter(pool, search_mode)

    if not matches:
        print(f"\n{CLR_YELLOW}No matching revisions found.{CLR_RESET}")
        return

    render_table(matches, nearest_root)
    action_subloop(pool, nearest_root)

def action_subloop(pool: list, nearest_root: str):
    while True:
        prompt = f"\n{CLR_ICE}Action: {CLR_CYAN}[R]estore <ID>{CLR_RESET} | {CLR_CYAN}[D]iff <ID>{CLR_RESET} | {CLR_CYAN}[V]iew/Nano <ID>{CLR_RESET} | {CLR_CYAN}[N]ew Search{CLR_RESET} | {CLR_CYAN}[Q]uit{CLR_RESET} -> "
        action_line = input(prompt).strip()
        if not action_line:
            continue

        parts = action_line.split()
        cmd_char = parts[0].lower()
        arg_id = parts[1] if len(parts) > 1 else None

        if cmd_char in ("q", "quit", "exit"):
            return

        if cmd_char in ("n", "new", "f", "filter", "s", "search"):
            interactive_explorer()
            return

        if cmd_char in ("r", "restore"):
            if not arg_id:
                arg_id = input(f"{CLR_ICE}Enter ID to restore: {CLR_RESET}").strip()
            execute_restore(arg_id)
        elif cmd_char in ("d", "diff"):
            if not arg_id:
                arg_id = input(f"{CLR_ICE}Enter ID for diff: {CLR_RESET}").strip()
            execute_diff(arg_id)
        elif cmd_char in ("v", "view", "nano"):
            if not arg_id:
                arg_id = input(f"{CLR_ICE}Enter ID for nano view: {CLR_RESET}").strip()
            execute_view(arg_id)
        else:
            print(f"{CLR_YELLOW}Unknown action. Enter r <ID>, d <ID>, v <ID>, n (new search), or q.{CLR_RESET}")

def execute_restore(target_id: str):
    idx = load_index()
    found = next((item for item in idx if str(item.get("id")) == str(target_id)), None)
    if not found:
        print(f"{CLR_YELLOW}[ERROR] Revision ID {target_id} not found.{CLR_RESET}")
        return
    bak_path = resolve_bak_path(found["bak_file"])
    orig_path = found["orig_path"]
    if not os.path.exists(bak_path):
        print(f"{CLR_YELLOW}[ERROR] Backup file missing: {bak_path}{CLR_RESET}")
        return
    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
    shutil.copy2(bak_path, orig_path)
    print(f"\n{CLR_GREEN}[SUCCESS] Revision {target_id} restored to:{CLR_RESET}\n  -> {orig_path}")
    print(f"{CLR_CYAN}[SAFETY] Loop-coupling active: Overwritten state captured into fresh safety backup!{CLR_RESET}\n")

def execute_diff(target_id: str):
    idx = load_index()
    found = next((item for item in idx if str(item.get("id")) == str(target_id)), None)
    if not found or not found.get("diff_file"):
        print(f"{CLR_YELLOW}[INFO] No diff available for ID {target_id}.{CLR_RESET}")
        return
    diff_path = os.path.join(BACKUP_DIR, found["diff_file"])
    if os.path.exists(diff_path):
        with open(diff_path, "r", encoding="utf-8", errors="replace") as df:
            print(f"{CLR_CYAN}{df.read()}{CLR_RESET}")
    else:
        print(f"{CLR_YELLOW}[ERROR] Diff file missing: {diff_path}{CLR_RESET}")

def execute_view(target_id: str):
    idx = load_index()
    found = next((item for item in idx if str(item.get("id")) == str(target_id)), None)
    if not found:
        print(f"{CLR_YELLOW}[ERROR] Revision ID {target_id} not found.{CLR_RESET}")
        return
    bak_path = resolve_bak_path(found["bak_file"])
    print(f"{CLR_CYAN}[NANO] Opening revision [{target_id}]: {found['bak_file']} (read-only)...{CLR_RESET}")
    open_in_nano(bak_path)

def cli_main():
    args = sys.argv[1:]

    if not args:
        if sys.stdin.isatty():
            interactive_explorer()
            return
        else:
            args = ["list"]

    cmd = args[0]

    # Intuitive Dienst-Schnellbefehle ohne 'service'
    if cmd in ("restart", "--restart", "-restart"):
        manage_service("restart")
        return

    if cmd in ("status", "--status", "-status"):
        manage_service("status")
        return

    if cmd in ("stop", "--stop", "-stop"):
        manage_service("stop")
        return

    if cmd in ("start", "--start", "-start"):
        manage_service("start")
        return

    if cmd in ("whatsnew", "changes", "changelog"):
        ver_arg = args[1] if len(args) > 1 else None
        show_whats_new(ver_arg)
        return

    if cmd in ("version", "--version", "-v"):
        print_version()
        return

    if cmd in ("help", "--help", "-h"):
        show_help()
        return

    if cmd in ("daemon", "--daemon", "run"):
        run_daemon()
        return

    if cmd == "service":
        subaction = args[1] if len(args) > 1 else "status"
        manage_service(subaction)
        return

    if cmd == "init":
        limit = args[1] if len(args) > 1 else str(DEFAULT_MAX_FILE_MB)
        start_t = args[2] if len(args) > 2 else str(DEFAULT_START_TIER)
        end_t = args[3] if len(args) > 3 else str(DEFAULT_END_TIER)
        mfile = os.path.join(os.getcwd(), "sentinel_marker")
        with open(mfile, "w", encoding="utf-8") as f:
            f.write(f"{limit} {start_t} {end_t}\n")
        print(f"[INIT] Marker created: {mfile} (Ceiling: {limit} MB | Tiers: T{start_t}..T{end_t})")
        print("Reload daemon with: sentinel restart")
        return

    if cmd == "markers":
        print("\n" + "=" * 80)
        print(" SHADOW SENTINEL - ACTIVE MARKERS & CASCADE CONFIGURATION")
        print("=" * 80)
        targets = discover_markers()
        if not targets:
            print("  (No markers found. Use 'sentinel init [MB] [start] [end]' to set one)")
        for root, (max_bytes, start_t, end_t) in targets.items():
            print(f"  * {root:<40} [Ceiling: {max_bytes // (1024*1024)} MB | Tiers: T{start_t}..T{end_t}]")
        print("=" * 80 + "\n")
        return

    if cmd in ("nano", "view"):
        if len(args) < 2:
            print("Usage: sentinel nano <ID>")
            sys.exit(1)
        execute_view(args[1])
        return

    if cmd == "diff":
        if len(args) < 2:
            print("Usage: sentinel diff <ID>")
            sys.exit(1)
        execute_diff(args[1])
        return

    if cmd == "restore":
        if len(args) < 2:
            print("Usage: sentinel restore <ID>")
            sys.exit(1)
        execute_restore(args[1])
        return

    cwd = os.getcwd()
    nearest_root, marker_path = find_nearest_marker(cwd)
    idx = load_index()

    filter_pattern = args[0] if (args and args[0] != "list") else None

    if nearest_root:
        size_mb, start_t, end_t = parse_marker_file(marker_path)
        filtered = [item for item in idx if item["orig_path"].startswith(nearest_root)]
    else:
        filtered = idx

    if filter_pattern:
        filtered = [
            item for item in filtered
            if fnmatch.fnmatch(os.path.basename(item["orig_path"]).lower(), filter_pattern.lower())
            or fnmatch.fnmatch(item.get("tier", "").lower(), filter_pattern.lower())
            or filter_pattern.lower() in item["orig_path"].lower()
        ]

    if not filtered:
        print("  No revisions matched the filter.")
    else:
        render_table(filtered, nearest_root)

if __name__ == "__main__":
    cli_main()
