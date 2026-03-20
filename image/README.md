# CafeBox Image Builder

This directory is the destination for the flashable Raspberry Pi image produced
by `scripts/build-image.sh`.

---

## Overview

`scripts/build-image.sh` automates the full image build pipeline:

1. Downloads the latest **Raspberry Pi OS Lite 64-bit** (Bookworm) base image.
2. Creates a working copy and expands it to 8 GB to give headroom for
   provisioned packages.
3. Registers ARM64 binfmt support so the chroot can run ARM64 binaries on an
   x86-64 host.
4. Runs `ansible/site.yml` inside the mounted image using
   `systemd-nspawn`, applying every role in the same way that `vagrant up`
   provisions the development VM.
5. Compresses the finished image to a `.img.xz` file ready for flashing.

---

## Required Host Tools

Install the following on your build machine before running the script.

### Debian / Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y \
    ansible \
    binfmt-support \
    e2fsprogs \
    kpartx \
    parted \
    qemu-user-static \
    rsync \
    util-linux \
    wget \
    xz-utils
```

### macOS (not supported for full builds)

The script relies on Linux-specific tools (`systemd-nspawn`, `binfmt_misc`,
`kpartx`). On macOS, use the development VM (`vagrant up`) or run the build
script inside a Linux container or CI runner.

---

## Building the Image

```bash
# From the repository root:
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

| Stage | Time (typical laptop) |
|-------|-----------------------|
| Base image download (~1 GB) | 3–10 min (depends on connection) |
| Partition resize | < 1 min |
| Ansible provisioning | 15–30 min |
| Compression (xz) | 2–5 min |
| **Total** | **~20–40 min** |

Build times vary based on network speed and host CPU. The `xz -T0` flag uses
all available CPU cores for compression.

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
