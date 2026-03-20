# scripts/

Developer and build utilities for CafeBox. None of these scripts run during
normal Ansible provisioning — they are helpers for local development, CI, and
image building.

## Scripts

### config.py

CafeBox configuration loader. Parses and validates `cafe.yaml`, checking for
required keys and valid values (e.g. hostname format).

```bash
# Standalone — print resolved config
python scripts/config.py [path/to/cafe.yaml]
```

Also importable as a module by other scripts:

```python
from config import load_config, ConfigError
cfg = load_config("cafe.yaml")
```

### generate-configs.py

Jinja2 template preview tool. Renders every `*.j2` template found across
`ansible/roles/*/templates/` into `system/generated/` so developers can
inspect rendered output without running a full playbook or VM. Each role's
`defaults/main.yml` is merged into the context to supply Ansible-specific
variables.

```bash
python scripts/generate-configs.py [--config cafe.yaml]
```

Idempotent — only writes files when content changes.

### build-image.sh

Builds a flashable CafeBox Raspberry Pi SD card image. Downloads the latest
Raspberry Pi OS Lite (64-bit), mounts it via a loop device, runs
`ansible/site.yml` inside a chroot, and compresses the result to
`image/cafebox.img.xz`.

```bash
scripts/build-image.sh [--output <path>] [--work-dir <path>]
```

**Must run on a native ARM64 host** (no cross-architecture emulation).
Configurable via environment variables: `CAFE_CONFIG`, `OUTPUT_IMAGE`,
`WORK_DIR`, `RPI_OS_URL`, `KEEP_WORK`.

### dev-hosts.sh

Adds or removes local `/etc/hosts` entries mapping `*.cafe.box` to
`127.0.0.1`, so a developer's browser resolves CafeBox service domains
without a real WiFi hotspot.

```bash
sudo scripts/dev-hosts.sh add      # append entries (idempotent)
sudo scripts/dev-hosts.sh remove   # remove entries
```
