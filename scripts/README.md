# scripts/

Developer and build utilities for Hearth. None of these scripts run during
normal Ansible provisioning — they are helpers for local development, CI, and
image building.

## Scripts

### config.py

Hearth configuration loader. Parses and validates `hearth.yaml`, checking for
required keys and valid values (e.g. hostname format).

```bash
# Standalone — print resolved config
python scripts/config.py [path/to/hearth.yaml]
```

Also importable as a module by other scripts:

```python
from config import load_config, ConfigError
cfg = load_config("hearth.yaml")
```

### generate-configs.py

Jinja2 template preview tool. Renders every `*.j2` template found across
`ansible/roles/*/templates/` into `system/generated/` so developers can
inspect rendered output without running a full playbook or VM. Each role's
`defaults/main.yml` is merged into the context to supply Ansible-specific
variables.

```bash
python scripts/generate-configs.py [--config hearth.yaml]
```

Idempotent — only writes files when content changes.

### build-image.sh

Builds a flashable Hearth Raspberry Pi SD card image. Downloads the latest
Raspberry Pi OS Lite (64-bit), mounts it via a loop device, runs
`ansible/site.yml` inside a chroot, and compresses the result to
`image/hearth.img.xz`.

```bash
scripts/build-image.sh [--output <path>] [--work-dir <path>]
```

**Must run on a native ARM64 host** (no cross-architecture emulation).
Configurable via environment variables: `HEARTH_CONFIG`, `OUTPUT_IMAGE`,
`WORK_DIR`, `RPI_OS_URL`, `KEEP_WORK`.

### dev-hosts.sh

Adds or removes local `/etc/hosts` entries mapping `*.hearth.local` to
`127.0.0.1`, so a developer's browser resolves Hearth service domains
without a real WiFi hotspot.

```bash
sudo scripts/dev-hosts.sh add      # append entries (idempotent)
sudo scripts/dev-hosts.sh remove   # remove entries
```
