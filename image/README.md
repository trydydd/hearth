# CafeBox Image Builder

This directory is the destination for the flashable Raspberry Pi image produced
by `scripts/build-image.sh`.

---

## Overview

`scripts/build-image.sh` automates the full image build pipeline:

1. Downloads the latest **Raspberry Pi OS Lite 64-bit** (Bookworm) base image.
2. Creates a working copy and expands it to 8 GB to give headroom for
   provisioned packages.
3. Mounts the image via a loop device and runs `ansible/site.yml` inside a
   native ARM64 chroot (`systemd-nspawn`), applying every role in the same way
   that `vagrant up` provisions the development VM.
4. Compresses the finished image to a `.img.xz` file ready for flashing.

### Why a native ARM64 host?

The script deliberately avoids cross-architecture emulation (QEMU + binfmt_misc).
Emulation makes every package install and every compile step 5–10× slower, and
introduces a class of subtle failures where host/target ABI differences cause
tools to behave differently inside the chroot than they would on real hardware.

By running on a native ARM64 host the chroot executes ARM64 binaries at full
speed with no emulation overhead — the result is faster builds and higher
confidence that the provisioned image matches what runs on the Pi.

---

## Three Ways to Build the Image

| Option | Where it runs | Best for |
|--------|---------------|----------|
| **1 — Raspberry Pi** | On a Pi 4/5 running a 64-bit OS | Operators building a single customised image |
| **2 — ARM64 workstation / cloud instance** | Apple M-series (Linux VM), AWS Graviton, Ampere Altra | Developers who already have an ARM64 machine |
| **3 — GitHub Actions CI (remote runner)** | `ubuntu-24.04-arm` runner on GitHub | Automated release builds on every version tag |

### Option 3 in detail — GitHub Actions remote runner

Push a version tag and GitHub builds the image for you automatically.
No local ARM64 hardware is required.

**Cost** — `ubuntu-24.04-arm` is billed at **$0.016 / minute** for private
repositories. A full build takes roughly 10–30 minutes:

| Scenario | Estimated cost |
|----------|----------------|
| Public repository | **Free** (GitHub Actions minutes are free for public repos) |
| Fast build (10 min, private repo) | ~$0.16 |
| Typical build (20 min, private repo) | ~$0.32 |
| Slow build (30 min, private repo) | ~$0.48 |

The workflow lives at `.github/workflows/build-image.yml`. It triggers
automatically on every `v*` tag push and attaches `cafebox.img.xz` to the
GitHub Release.

To trigger a build manually:

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Host Architecture Requirement

**The build host must be native ARM64 (`aarch64`).**

Suitable build environments:

| Environment | Notes |
|-------------|-------|
| GitHub Actions `ubuntu-24.04-arm` runner | Free for public repos; used by the CI workflow |
| Raspberry Pi (64-bit OS) | Any model; Pi 4 / 5 recommended for speed |
| AWS Graviton, Ampere Altra, Oracle Ampere | ARM64 cloud instances |
| Apple M-series Mac | Run inside a Linux VM or OrbStack container |

If you try to run the script on an x86-64 host it will exit with a clear error
message. Cross-architecture emulation is intentionally not supported.

---

## Design Rationale: Why a Bash Script Rather Than an Ansible Playbook?

The build pipeline has two distinct layers:

| Layer | Tool | Why |
|-------|------|-----|
| **Image orchestration** (download, loop-device setup, partition resize, mount/unmount, xz compression) | Bash | These are raw OS operations (`losetup`, `kpartx`, `parted`, `resize2fs`, `mount`). Expressing them in Ansible would require importing community collections (`community.general`, `ansible.posix`) and wrapping every low-level call in a module that adds no clarity over a direct shell command. |
| **Software provisioning** (install packages, configure services, deploy files) | Ansible (`ansible/site.yml`) | This is exactly what Ansible is designed for. The same playbook provisions the dev VM via Vagrant and the production image — a single source of truth. |

In short: **Bash handles the image scaffolding; Ansible handles everything inside the image.**
Running Ansible *inside* the image (step 4 of the script) gives you the same
idempotent, role-based provisioning that the Vagrant workflow uses — with no
duplication.

---

## Required Host Tools

Install the following on your ARM64 build machine before running the script.

### Debian / Ubuntu (ARM64)

```bash
sudo apt-get update
sudo apt-get install -y \
    ansible \
    e2fsprogs \
    kpartx \
    parted \
    rsync \
    systemd-container \
    util-linux \
    wget \
    xz-utils
```

### macOS (requires a Linux VM or container)

The script relies on Linux-specific tools (`systemd-nspawn`, `kpartx`). On
macOS, run the script inside an ARM64 Linux VM (e.g. OrbStack, UTM) or trigger
the CI workflow on a tagged commit. macOS itself — even on Apple Silicon — lacks
the required Linux kernel interfaces.

---

## Building the Image

```bash
# From the repository root (must be run on a native ARM64 host):
sudo scripts/build-image.sh
```

The finished image is written to `image/cafebox.img.xz` by default.

### Options

| Flag / Variable | Default | Description |
|-----------------|---------|-------------|
| `--output <path>` | `image/cafebox.img.xz` | Where to write the compressed image |
| `--work-dir <path>` | `/tmp/cafebox-build` | Scratch directory for build artifacts |
| `CAFE_CONFIG` | `cafe.yaml` | Path to the operator config file |
| `RPI_OS_URL` | *(latest RPi OS Lite 64-bit)* | Override the base image download URL |
| `KEEP_WORK=1` | — | Keep the work directory after a successful build |

Example — custom output path and retained work directory:

```bash
sudo KEEP_WORK=1 scripts/build-image.sh --output /tmp/cafebox-$(date +%Y%m%d).img.xz
```

---

## Estimated Build Time

| Stage | Time (native ARM64 host) |
|-------|--------------------------|
| Base image download (~1 GB) | 3–10 min (depends on connection) |
| Partition resize | < 1 min |
| Ansible provisioning | 5–15 min |
| Compression (xz) | 2–5 min |
| **Total** | **~10–30 min** |

Build times vary based on network speed and host CPU. The `xz -T0` flag uses
all available CPU cores for compression. Provisioning runs at native ARM64
speed with no emulation overhead, compared to the 5–10× slowdown from
QEMU userspace emulation on an x86-64 host.

---

## Flashing to an SD Card

```bash
# Identify your SD card device (e.g. /dev/sdb or /dev/mmcblk0)
lsblk

# Flash (replace /dev/sdX with your device — double-check before running!)
xzcat image/cafebox.img.xz | sudo dd of=/dev/sdX bs=4M status=progress
sudo sync
```

> **Warning:** `dd` will overwrite the target device without confirmation.
> Make sure you have selected the correct device.

### Using Raspberry Pi Imager

Alternatively, open **Raspberry Pi Imager**, choose
*Use custom image*, and select the `.img.xz` file. The Imager decompresses and
flashes automatically.

---

## First Boot

1. Insert the SD card and power on the Raspberry Pi.
2. The box broadcasts a WiFi hotspot named **CafeBox** (configurable in
   `cafe.yaml`).
3. Connect any device to the hotspot. The captive portal detection redirect
   opens the landing page automatically on most devices.
4. The landing page displays a **one-time admin password** generated on first
   boot. Log in at `http://admin.cafe.box` and change it immediately.

---

## Customising the Image

Edit `cafe.yaml` before running `scripts/build-image.sh` to customise the box
identity, WiFi settings, enabled services, and storage paths. All configuration
is baked into the image at build time.
