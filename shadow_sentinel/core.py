#!/usr/bin/env python3
# ==============================================================================
# core.py - Autonomous OS-Level Revision & Backup Guard
# Single Source of Truth - Linux FHS Compliant Open-Source Release
# License: CC3, copyright 2026 Torsten Frieser, Germany / Saxony / Zittau
# ==============================================================================
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
import subprocess

def get_storage_dirs():
    """
    Resolves storage directory standard-compliantly:
    1. Environment variable SENTINEL_STORAGE_DIR
    2. Optional config: /etc/shadow-sentinel/config.json or ~/.config/shadow-sentinel/config.json
    3. Linux FHS default: /var/lib/shadow-sentinel (root) or ~/.local/share/shadow-sentinel (user)
    """
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

MAX_VERSIONS_PER_FILE = 10
MAX_BACKUP_AGE_DAYS   = 14
MAX_LOG_AGE_DAYS      = 30
MAX_BACKUP_DIR_MB     = 500
PRUNE_INTERVAL_SEC    = 21600
COOLDOWN_SEC          = 3

DEFAULT_MAX_FILE_SIZE_MB = 5

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
marker_targets = {}

def signal_handler(sig, frame):
    global running
    print(f"\n[SENTINEL] Signal {sig} received. Terminating guard service...")
    running = False

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def is_sentinel_internal(path: str) -> bool:
    """Prevents recursion loops: vault and backup directories do not monitor themselves."""
    abs_p = os.path.abspath(path)
    if abs_p == BACKUP_DIR or abs_p.startswith(BACKUP_DIR + os.sep):
        return True
    if abs_p == VAULT_DIR or abs_p.startswith(VAULT_DIR + os.sep):
        return True
    if abs_p == "/etc/shadow-sentinel" or abs_p.startswith("/etc/shadow-sentinel" + os.sep):
        return True
    return False

def load_index() -> list:
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_index(index_list: list):
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index_list, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[SENTINEL-INDEX-ERR] {e}")

def record_backup(orig_path: str, bak_name: str, diff_name: str, size_bytes: int):
    idx = load_index()
    next_id = 1
    if idx:
        next_id = max(item.get("id", 0) for item in idx) + 1

    entry = {
        "id": next_id,
        "orig_path": os.path.abspath(orig_path),
        "bak_file": bak_name,
        "diff_file": diff_name,
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

        limit_mb = DEFAULT_MAX_FILE_SIZE_MB
        try:
            content = ""
            with open(mpath, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                with open(mpath, "w", encoding="utf-8") as f:
                    f.write(f"{DEFAULT_MAX_FILE_SIZE_MB}\n")
                limit_mb = DEFAULT_MAX_FILE_SIZE_MB
            else:
                parsed = int(float(content))
                if parsed > 0:
                    limit_mb = parsed
        except Exception:
            limit_mb = DEFAULT_MAX_FILE_SIZE_MB

        targets[watch_root] = limit_mb * 1024 * 1024

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

def get_max_size_for_file(abs_path: str) -> int:
    matched_root = None
    matched_size = DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024
    abs_p = os.path.abspath(abs_path)
    for root, size in marker_targets.items():
        if abs_p == root or abs_p.startswith(root + "/"):
            if matched_root is None or len(root) > len(matched_root):
                matched_root = root
                matched_size = size
    return matched_size

def auto_prune_backups():
    global last_prune_ts
    now = time.time()
    last_prune_ts = now
    print("[SENTINEL-PRUNER] Starting automated backup pruning...")

    deleted_count = 0
    freed_bytes = 0

    pattern = re.compile(r"^(.*?)\.(\d{8}_\d{6})\.(bak|diff|deleted\.bak)$")
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
            ext_type = match.group(3)
            key = (orig_name, ext_type)
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append((fname, fpath, os.path.getmtime(fpath), os.path.getsize(fpath)))

    for (orig_name, ext_type), items in file_groups.items():
        items.sort(key=lambda x: x[2], reverse=True)

        for idx, (fname, fpath, mtime, size) in enumerate(items):
            should_delete = False
            if idx >= MAX_VERSIONS_PER_FILE:
                should_delete = True
            elif idx > 0 and (now - mtime) > (MAX_BACKUP_AGE_DAYS * 86400):
                should_delete = True

            if should_delete:
                try:
                    os.remove(fpath)
                    deleted_count += 1
                    freed_bytes += size
                except Exception:
                    pass

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

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    print(f"[SENTINEL-PRUNER] Pruning complete: {deleted_count} stale versions deleted ({freed_mb} MB freed).")

def sync_initial_vault():
    print(f"[SENTINEL] Synchronizing shadow vault (storage base: {CENTRAL_BASE})...")
    count = 0
    ejected_count = 0

    for root_dir, max_bytes in marker_targets.items():
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

    print(f"[SENTINEL] Shadow vault ready ({count} files tracked, {ejected_count} exceeded limit and ejected).")
    auto_prune_backups()

def handle_file_written(abs_path: str):
    if not os.path.exists(abs_path) or not is_monitored_file(abs_path):
        return

    vault_path = get_vault_path(abs_path)
    max_bytes = get_max_size_for_file(abs_path)

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
                print(f"[SENTINEL] SIZE CEILING EXCEEDED ({size_mb} MB > {limit_mb} MB): {abs_path} ejected from shadow vault.")
            except Exception:
                pass
        return

    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    new_hash = get_sha256(abs_path)
    if not new_hash:
        return

    ts = time.strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(abs_path)

    if os.path.exists(vault_path):
        old_hash = get_sha256(vault_path)
        if old_hash != new_hash:
            bak_name = f"{base_name}.{ts}.bak"
            bak_path = os.path.join(BACKUP_DIR, bak_name)
            shutil.copy2(vault_path, bak_path)

            diff_name = f"{base_name}.{ts}.diff"
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
                        df.write(f"=== SENTINEL AUTO-DIFF: {abs_path} ===\n")
                        df.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} | Hash: {new_hash[:12]}\n\n")
                        df.writelines(diff)
            except Exception:
                pass

            today_str = time.strftime("%Y%m%d")
            with open(os.path.join(BACKUP_DIR, f"diff-{today_str}.log"), "a", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SENTINEL_AUTO_BACKUP] FILE: {abs_path} | SHA256: {new_hash[:12]} | BACKUP: {bak_name} | DIFF: {diff_name}\n")

            record_backup(abs_path, bak_name, diff_name, cur_size)
            print(f"[SENTINEL] MODIFICATION BACKED UP: {abs_path} -> {bak_name}")
            shutil.copy2(abs_path, vault_path)
    else:
        shutil.copy2(abs_path, vault_path)
        print(f"[SENTINEL] NEW FILE REGISTERED IN VAULT: {abs_path}")

def handle_file_deleted(abs_path: str):
    if not is_monitored_file(abs_path):
        return

    vault_path = get_vault_path(abs_path)
    base_name = os.path.basename(abs_path)

    if os.path.exists(vault_path):
        ts = time.strftime("%Y%m%d_%H%M%S")
        del_bak = f"{base_name}.{ts}.deleted.bak"
        bak_path = os.path.join(BACKUP_DIR, del_bak)
        shutil.copy2(vault_path, bak_path)

        today_str = time.strftime("%Y%m%d")
        with open(os.path.join(BACKUP_DIR, f"diff-{today_str}.log"), "a", encoding="utf-8") as lf:
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SENTINEL_AUTO_DELETED] FILE: {abs_path} | BACKUP: {del_bak}\n")

        record_backup(abs_path, del_bak, "", 0)
        os.remove(vault_path)
        print(f"[SENTINEL] DELETION BACKED UP: {abs_path} -> {del_bak}")

def run_daemon():
    global last_prune_ts, pending_writes, marker_targets
    marker_targets = discover_markers()

    print(f"[SENTINEL] Guard active. Storage base: {CENTRAL_BASE}")
    if not marker_targets:
        print("[SENTINEL] Info: No 'sentinel_marker' found. Create a marker with 'sentinel init' in any directory to begin monitoring.")
    else:
        print("[SENTINEL] Active marker roots:")
        for root, max_bytes in marker_targets.items():
            print(f"  * {root} (Limit: {max_bytes // (1024*1024)} MB)")

    sync_initial_vault()

    inotify_fd = libc.inotify_init1(0)
    if inotify_fd < 0:
        print("[SENTINEL] Error: inotify_init1 failed!")
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

    print(f"[SENTINEL] Inotify engine watching {len(wd_to_dir)} directories.")

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
                print(f"[SENTINEL-ERROR]: {e}")
                time.sleep(1)

    if pending_writes:
        for fpath in list(pending_writes.keys()):
            handle_file_written(fpath)
        pending_writes.clear()

    os.close(inotify_fd)
    print("[SENTINEL] Guard terminated.")

def manage_service(action: str):
    service_file = "/etc/systemd/system/shadow-sentinel.service"
    py_exec = sys.executable

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
            print(f"[SENTINEL] ✅ Service successfully installed and started: {service_file}")
            print("Check status with: sentinel service status")
        except Exception as e:
            print(f"[SENTINEL-ERROR] Service installation failed (root privileges required?): {e}")

    elif action in ("status", "restart", "stop", "start"):
        subprocess.run(["systemctl", action, "shadow-sentinel"])
    else:
        print("Unknown service action. Available: install, status, restart, start, stop")

def show_help():
    manual = """
====================================================================================================
SHADOW SENTINEL - AUTONOMOUS OS-LEVEL REVISION & BACKUP DAEMON
====================================================================================================

DESCRIPTION
  Shadow Sentinel is a lightweight, zero-dependency, kernel-level filesystem revision guard.
  It monitors arbitrary directory trees via Linux inotify (libc), captures atomic backups (.bak)
  and human-readable unified diffs (.diff) on every write, and provides instant 1-command restores
  with loop-coupling safety.

CORE ARCHITECTURAL CONCEPTS

  1. Decentralized Marker Control (sentinel_marker)
     - No cumbersome central path registration required.
     - Placing a file named 'sentinel_marker' into any directory instructs the daemon to monitor
       that directory and all its subdirectories recursively.
     - On daemon startup or server reboot, the daemon scans the system and binds all marked roots.

  2. Dynamic File-Size Ceiling (Self-Pruning Vault)
     - The integer stored inside 'sentinel_marker' defines the maximum protected file size in MB.
       Default is 5 (for 5 MB).
     - If a file (such as a runaway logfile) exceeds this ceiling, it is automatically ejected
       from the shadow vault. Small scripts, configurations, and source code stay 100% protected.

  3. Loop-Coupling (Undo-Safe Restore)
     - Restoring a file with 'sentinel restore <ID>' overwrites the current file.
     - The running inotify daemon immediately intercepts this write and seals the overwritten
       state into a brand-new backup revision.
     - An accidental restore never destroys data; any mistaken restore can instantly be undone!

  4. Flapping & Cooldown Debounce
     - High-frequency write streams (e.g. active apps writing multiple times per second) are debounced
       with a 3-second quiet window to prevent backup spam.

AUTOMATED DISK SANITATION & RETENTION DOCTRINE

  Sentinel guarantees that it will never exhaust disk space through a 4-tier automated policy:
    1. Version Cap per File (Max 10 Revisions):
       Only the 10 most recent .bak and .diff files per target are kept. Older versions are deleted.
    2. Version Age Expiration (14 Days):
       Revisions older than 14 days are automatically pruned.
    3. Log Expiration (30 Days):
       Daily audit diff logs (diff-YYYYMMDD.log) are removed after 30 days.
    4. Emergency Storage Ceiling (500 MB Cap):
       If total backup directory size exceeds 500 MB, an emergency purge trims the oldest backups
       across all files until total disk usage drops back down to 80% (400 MB).
    5. Active Vault Ejection:
       Files that grow beyond the MB ceiling in 'sentinel_marker' are immediately removed from
       the .shadow_vault to recover disk space instantly.

  *The pruning engine runs automatically every 6 hours and immediately upon service startup.*

COMMANDS

  sentinel [list]
      Lists the latest backup revisions for the current context. Sentinel walks upwards from the
      current working directory to locate the nearest 'sentinel_marker'. Displays revision ID,
      timestamp, file size, diff availability, and relative file path.

  sentinel restore <ID>
      Restores the exact file revision identified by <ID>. Overwrites the target file while
      automatically creating a safety backup of the overwritten version (loop-coupling).

  sentinel diff <ID>
      Outputs the full unified diff of revision <ID> directly to stdout.

  sentinel init [MAX_SIZE_MB]
      Initializes the current working directory as a monitored root by creating 'sentinel_marker'.
      Optional argument MAX_SIZE_MB sets the size ceiling (default: 5 MB).

  sentinel markers
      Scans and lists all active 'sentinel_marker' roots across the entire system.

  sentinel daemon
      Runs the Sentinel monitoring engine in the foreground.

  sentinel service <action>
      Manages the systemd background daemon.
      Actions:
        install   - Generates /etc/systemd/system/shadow-sentinel.service and starts it.
        status    - Checks the systemd service status.
        restart   - Restarts the background daemon (rescans all markers).
        stop      - Stops the daemon.
        start     - Starts the daemon.

  sentinel help, --help, -h
      Displays this manual.

STORAGE & CONFIGURATION

  Default Linux FHS Storage Paths:
    - Root daemon: /var/lib/shadow-sentinel/
    - User daemon: ~/.local/share/shadow-sentinel/

  Custom Storage Redirection (/etc/shadow-sentinel/config.json):
    Sentinel supports an optional configuration file to redirect backup storage:
      Root: /etc/shadow-sentinel/config.json
      User: ~/.config/shadow-sentinel/config.json

    Example configuration:
      {
          "storage_dir": "/custom/path/to/backups"
      }

    When present, all backups, shadow vaults, and index records are stored under 'storage_dir'.

  Environment Variable Override:
    Export SENTINEL_STORAGE_DIR=/path/to/storage to override both defaults and configuration files.

====================================================================================================
"""
    print(manual)

def cli_main():
    args = sys.argv[1:]
    cmd = args[0] if args else "list"

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
        limit = args[1] if len(args) > 1 else str(DEFAULT_MAX_FILE_SIZE_MB)
        mfile = os.path.join(os.getcwd(), "sentinel_marker")
        with open(mfile, "w", encoding="utf-8") as f:
            f.write(f"{limit}\n")
        print(f"[SENTINEL] ✅ Marker created: {mfile} (Max file size: {limit} MB)")
        print("Reload daemon with: sentinel service restart")
        return

    if cmd == "markers":
        print("\n" + "=" * 70)
        print(" 🛡️ SHADOW SENTINEL - ACTIVE MARKERS ON SYSTEM")
        print("=" * 70)
        targets = discover_markers()
        if not targets:
            print("  (No markers found. Use 'sentinel init' to set one)")
        for root, max_bytes in targets.items():
            print(f"  * {root:<50} [Ceiling: {max_bytes // (1024*1024)} MB]")
        print("=" * 70 + "\n")
        return

    if cmd == "diff":
        if len(args) < 2:
            print("Usage: sentinel diff <ID>")
            sys.exit(1)
        target_id = args[1]
        idx = load_index()
        found = next((item for item in idx if str(item.get("id")) == target_id), None)
        if not found or not found.get("diff_file"):
            print(f"[SENTINEL] No diff available for ID {target_id}.")
            return
        diff_path = os.path.join(BACKUP_DIR, found["diff_file"])
        if os.path.exists(diff_path):
            with open(diff_path, "r", encoding="utf-8", errors="replace") as df:
                print(df.read())
        else:
            print(f"[SENTINEL] Diff file no longer exists: {diff_path}")
        return

    if cmd == "restore":
        if len(args) < 2:
            print("Usage: sentinel restore <ID>")
            sys.exit(1)

        target_id = args[1]
        idx = load_index()
        found = next((item for item in idx if str(item.get("id")) == target_id), None)

        if not found:
            print(f"[SENTINEL-ERROR] No backup revision found with ID {target_id}!")
            sys.exit(1)

        bak_path = os.path.join(BACKUP_DIR, found["bak_file"])
        orig_path = found["orig_path"]

        if not os.path.exists(bak_path):
            print(f"[SENTINEL-ERROR] Backup file no longer exists: {bak_path}")
            sys.exit(1)

        os.makedirs(os.path.dirname(orig_path), exist_ok=True)
        # LOOP-COUPLING: Triggers inotify -> previous version automatically sealed as new backup
        shutil.copy2(bak_path, orig_path)
        print(f"\n[SENTINEL] ✅ Revision {target_id} restored to:\n  -> {orig_path}")
        print("[SENTINEL] 🔄 Loop-coupling active: Overwritten version was automatically backed up!\n")
        return

    # Default action: list backups in the current marker branch
    cwd = os.getcwd()
    nearest_root, marker_path = find_nearest_marker(cwd)
    idx = load_index()

    print("\n" + "=" * 90)
    print(" 🛡️ SHADOW SENTINEL - FILE REVISIONS & RESTORATION")
    print("=" * 90)

    if nearest_root:
        marker_val = "5 MB (Default)"
        try:
            with open(marker_path, "r", encoding="utf-8") as mf:
                val = mf.read().strip()
                if val:
                    marker_val = f"{val} MB"
        except Exception:
            pass
        print(f"Current Context: {cwd}")
        print(f"Responsible Sentinel Root: {nearest_root} (Ceiling: {marker_val})")
        filtered = [item for item in idx if item["orig_path"].startswith(nearest_root)]
    else:
        print(f"Current Context: {cwd} (No local marker found - showing all)")
        filtered = idx

    print("-" * 90)
    if not filtered:
        print("  No backup revisions found for this context.")
    else:
        print(f"{'ID':<6} {'TIMESTAMP':<20} {'FILE SIZE':<14} {'DIFF':<6} ORIGINAL PATH")
        print("-" * 90)
        for item in reversed(filtered[-30:]):
            diff_label = "[YES]" if item.get("diff_file") else "[--]"
            size_kb = f"{round(item.get('size_bytes', 0) / 1024, 1)} KB"
            display_path = item["orig_path"]
            if nearest_root and display_path.startswith(nearest_root):
                display_path = os.path.relpath(display_path, nearest_root)

            print(f"[{item['id']}]   {item['timestamp']:<20} {size_kb:<14} {diff_label:<6} {display_path}")

    print("=" * 90)
    print(" 💡 RESTORE:             sentinel restore <ID>")
    print(" 🔍 VIEW DIFF:           sentinel diff <ID>")
    print(" ➕ NEW MARKER:          sentinel init [max_mb]")
    print(" ⚙️ SYSTEMD SERVICE:     sentinel service install|restart|status")
    print(" 📖 HELP & MANUAL:       sentinel help")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    cli_main()
