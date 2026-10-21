# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-10-21

### Added
- **Decade-Tier Cascade Buffers**: Geometric progression (3 * 10^(k-1) seconds) scaling up to Tier 128.
- **Hierarchical Tier-Range Markers**: Marker syntax `<max_size_mb> [start_tier] [end_tier]` (e.g. `5 3 6`).
- **Deepest-Marker Override**: Nested subdirectories can override parent policies using longest-prefix resolution.
- **Enhanced CLI**: `sentinel init [MB] [start_tier] [end_tier]` and tier tag filtering (`sentinel T6`).

## [1.0.1] - 2026-10-16

### Added
- **Full-History Display**: Removed artificial 30-entry cutoff; shows complete history with terminal scroll support.
- **Autonomous Legacy Reindex**: Automatically indexes existing `.bak` files on daemon startup.
- **Search Filtering**: Filter revisions by filename or tier tag (`sentinel <term>`).
- **SPDX Metadata**: Formalized CC-BY-SA-3.0 licensing in source headers.

## [1.0.0] - 2026-10-16

### Added
- **Initial Release**: Kernel-level inotify file revision daemon using raw `libc.so.6` bindings via Python `ctypes`.
- **Decentralized Marker Control**: Autonomous discovery via `sentinel_marker` files.
- **Dynamic Size Ceiling**: Self-pruning vault ejection for files exceeding threshold.
- **Loop-Coupled Restores**: Safe 1-command rollback preserving the overwritten state.
- **Automated 4-Tier Hygiene**: Version capping, 14-day pruning, 30-day log expiration, and 500 MB hard ceiling.
