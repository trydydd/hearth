#!/usr/bin/env bash
# scripts/build-vm-disk.sh — Download and prepare the development VM disk image
#
# Downloads the Debian 12 (Bookworm) Generic Cloud ARM64 image — the same
# Debian release that Raspberry Pi OS Lite is based on — and creates a
# cloud-init nocloud seed image used by scripts/vm.sh to configure the VM
# on first boot.
#
# Configurable environment variables (with defaults):
#   VM_DISK       Destination qcow2 path        (default: vm/cafebox-dev.qcow2)
#   VM_SEED       Cloud-init seed image path    (default: vm/cafebox-seed.img)
#   VM_PASSWORD   Password for the 'pi' user    (default: admin)
#   DEBIAN_URL    Download URL for the Debian 12 ARM64 cloud image
#                 (default: https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-arm64.qcow2)
#   DEBIAN_CACHE  Directory used to cache the downloaded image so that
#                 subsequent builds skip the large download  (default: vm/debian-cache)
#
# Prerequisites: curl, qemu-img, mcopy (mtools), mformat (mtools), openssl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

VM_DISK="${VM_DISK:-vm/cafebox-dev.qcow2}"
VM_SEED="${VM_SEED:-vm/cafebox-seed.img}"
DEBIAN_URL="${DEBIAN_URL:-https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-arm64.qcow2}"
DEBIAN_CACHE="${DEBIAN_CACHE:-vm/debian-cache}"

# Resolve relative paths to the repo root
if [[ "$VM_DISK" != /* ]]; then
    VM_DISK="$REPO_ROOT/$VM_DISK"
fi
if [[ "$VM_SEED" != /* ]]; then
    VM_SEED="$REPO_ROOT/$VM_SEED"
fi
if [[ "$DEBIAN_CACHE" != /* ]]; then
    DEBIAN_CACHE="$REPO_ROOT/$DEBIAN_CACHE"
fi

VM_DIR="$(dirname "$VM_DISK")"
mkdir -p "$VM_DIR"
mkdir -p "$DEBIAN_CACHE"

# Verify required tools are present, with install hints
declare -A TOOL_HINTS=(
    [curl]="sudo apt install curl"
    [qemu-img]="sudo apt install qemu-utils"
    [mcopy]="sudo apt install mtools"
    [mformat]="sudo apt install mtools"
    [openssl]="sudo apt install openssl"
)
for tool in curl qemu-img mcopy mformat openssl; do
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: Required tool not found: $tool" >&2
        echo "       Install it with: ${TOOL_HINTS[$tool]}" >&2
        exit 1
    fi
done

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# Download (or use cached) Debian 12 Generic Cloud ARM64 qcow2 image.
# The image is already in qcow2 format — no decompression or conversion needed.
CACHED_IMAGE="$DEBIAN_CACHE/debian-12-generic-arm64.qcow2"
if [[ -f "$CACHED_IMAGE" ]]; then
    echo "==> Using cached Debian 12 cloud image: $CACHED_IMAGE"
    echo "    (Delete it to force a fresh download)"
    cp "$CACHED_IMAGE" "$VM_DISK"
else
    echo "==> Downloading Debian 12 (Bookworm) Generic Cloud ARM64..."
    echo "    URL: $DEBIAN_URL"
    curl -L --progress-bar -o "$VM_DISK" "$DEBIAN_URL"
    echo "==> Caching image for future builds: $CACHED_IMAGE"
    cp "$VM_DISK" "$CACHED_IMAGE"
fi

echo "==> Expanding image to 16G..."
qemu-img resize "$VM_DISK" 16G

echo "==> Creating cloud-init seed image: $VM_SEED"
# The nocloud datasource is identified by a FAT image labelled 'cidata'
# that contains a meta-data and a user-data file.  cloud-init reads them on
# first boot to create the 'pi' user and enable SSH password authentication.
VM_PASSWORD="${VM_PASSWORD:-admin}"
HASHED_PW="$(openssl passwd -6 "$VM_PASSWORD")"

cat > "$TMP_DIR/meta-data" <<EOF
instance-id: cafebox-dev
local-hostname: cafebox-dev
EOF

cat > "$TMP_DIR/user-data" <<EOF
#cloud-config
users:
  - name: pi
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: false
    passwd: $HASHED_PW
    shell: /bin/bash
ssh_pwauth: true
EOF

# Build a 1 MiB FAT image labelled 'cidata' and populate it with the
# cloud-init configuration files.
dd if=/dev/zero bs=1M count=1 of="$VM_SEED"
mformat -i "$VM_SEED" -v cidata ::
mcopy -i "$VM_SEED" "$TMP_DIR/meta-data" ::/meta-data
mcopy -i "$VM_SEED" "$TMP_DIR/user-data" ::/user-data

echo ""
echo "VM disk image ready: $VM_DISK (16G)"
echo "Cloud-init seed:     $VM_SEED"
echo "Run 'make vm-start' to boot the VM."
