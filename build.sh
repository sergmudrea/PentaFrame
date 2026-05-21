#!/bin/bash
# Penta OS Master Build Script (v1.6.2)
# Builds a complete bootable image from scratch.
# Fixes:
#   - Creates system users penta and pentad (with i2c group).
#   - Installs i2c-tools, python3-smbus2 (or pip smbus2).
#   - Ensures i2c-dev module loaded at boot.
#   - Installs all Python dependencies into rootfs.
#   - Copies updated src with plugin_loader and unified config.
#   - Sets PENTA_CONFIG environment variable in service files.

set -euo pipefail

# ---------- Defaults ----------
ARCH="arm64"
VARIANT="desktop"
OUTPUT="./output"
EXTRA_PACKAGES=""
KERNEL_CONFIG="config/kernel-${ARCH}"
CLEANUP=true
BUILD_CONTAINERS=true

# ---------- Parse arguments ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        --variant) VARIANT="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --extra-packages) EXTRA_PACKAGES="$2"; shift 2 ;;
        --kernel-config) KERNEL_CONFIG="$2"; shift 2 ;;
        --no-clean) CLEANUP=false; shift ;;
        --no-containers) BUILD_CONTAINERS=false; shift ;;
        *) echo "Unknown option $1"; exit 1 ;;
    esac
done

if [[ "$ARCH" != "arm64" && "$ARCH" != "amd64" ]]; then
    echo "Invalid architecture: $ARCH (must be arm64 or amd64)"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (or with sudo)."
    exit 1
fi

# ---------- Setup ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(mktemp -d -t penta-build-XXXXXX)"
ROOTFS="$WORKDIR/rootfs"
IMAGEDIR="$WORKDIR/images"
mkdir -p "$ROOTFS" "$IMAGEDIR" "$OUTPUT"

echo "Building Penta OS ($ARCH, $VARIANT) in $WORKDIR"

cleanup() {
    if $CLEANUP; then
        echo "Cleaning up $WORKDIR ..."
        for m in "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/dev" "$ROOTFS/dev/pts"; do
            mountpoint -q "$m" && umount "$m" 2>/dev/null || true
        done
        rm -rf "$WORKDIR"
    else
        echo "Build directory preserved at $WORKDIR"
    fi
}
trap cleanup EXIT

# ---------- 1. Base rootfs ----------
echo "1. Creating base rootfs..."
debootstrap --arch="$ARCH" --variant=minbase \
    --include=systemd,systemd-sysv,ca-certificates,locales,curl,wget,gnupg,sudo,apt-transport-https \
    trixie "$ROOTFS" http://deb.debian.org/debian

# ---------- 2. Configure chroot ----------
echo "2. Configuring base system..."
echo "penta" > "$ROOTFS/etc/hostname"
echo "127.0.0.1 localhost penta" >> "$ROOTFS/etc/hosts"

chroot "$ROOTFS" locale-gen en_US.UTF-8
chroot "$ROOTFS" update-locale LANG=en_US.UTF-8

mount -t proc none "$ROOTFS/proc"
mount -t sysfs none "$ROOTFS/sys"
mount -o bind /dev "$ROOTFS/dev"
mount -o bind /dev/pts "$ROOTFS/dev/pts"

# QEMU cross-arch support
HOST_ARCH=$(uname -m)
if [[ "$HOST_ARCH" != "$ARCH" ]]; then
    case "$ARCH" in
        arm64) QEMU_BIN=qemu-aarch64-static ;;
        amd64) QEMU_BIN=qemu-x86_64-static ;;
    esac
    cp "/usr/bin/$QEMU_BIN" "$ROOTFS/usr/bin/"
fi

# ---------- 3. Install packages ----------
echo "3. Installing essential packages..."
cat <<EOF | chroot "$ROOTFS" bash
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y --no-install-recommends \
    btrfs-progs snapper \
    python3 python3-pip python3-fastapi python3-uvicorn \
    mosquitto mosquitto-clients \
    network-manager \
    distrobox docker.io \
    flatpak snapd appimaged \
    xorg wayland weston plasma-desktop \
    i2c-tools python3-smbus2 \
    sudo
EOF

# Enable i2c-dev module on boot
echo "i2c-dev" >> "$ROOTFS/etc/modules-load.d/penta.conf"

# Extra per-variant packages
case "$VARIANT" in
    desktop)
        chroot "$ROOTFS" apt install -y --no-install-recommends kde-full firefox-esr || true
        ;;
    minimal) ;;
    developer)
        chroot "$ROOTFS" apt install -y --no-install-recommends build-essential git vim
        ;;
esac

[[ -n "$EXTRA_PACKAGES" ]] && chroot "$ROOTFS" apt install -y $EXTRA_PACKAGES

# ---------- 4. Create system users ----------
echo "4. Creating Penta system users..."
chroot "$ROOTFS" useradd -r -s /bin/false -m -d /var/lib/penta penta
chroot "$ROOTFS" useradd -r -s /bin/false -M -G i2c pentad
# Allow penta to use docker
chroot "$ROOTFS" usermod -aG docker penta

# ---------- 5. Install Penta OS custom components ----------
echo "5. Installing Penta OS components..."
mkdir -p "$ROOTFS/opt/penta" "$ROOTFS/etc/penta/plugins" "$ROOTFS/var/lib/penta/toolbox"

# Copy source code
cp -r "$SCRIPT_DIR/src/"* "$ROOTFS/opt/penta/"
# Copy configuration
cp "$SCRIPT_DIR/config/penta.conf.example" "$ROOTFS/etc/penta/config.yaml"
cp "$SCRIPT_DIR/config/containers.yaml" "$ROOTFS/etc/penta/containers.yaml"
cp "$SCRIPT_DIR/config/repository-plugins.yaml" "$ROOTFS/etc/penta/plugins/"

# CLI tool
cp "$SCRIPT_DIR/src/cli/penta" "$ROOTFS/usr/local/bin/penta"
chmod +x "$ROOTFS/usr/local/bin/penta"

# Service files
for svc in penta-hub penta-resolver pentad psyched; do
    if [[ -f "$SCRIPT_DIR/services/$svc.service" ]]; then
        cp "$SCRIPT_DIR/services/$svc.service" "$ROOTFS/etc/systemd/system/"
        # Set PENTA_CONFIG environment variable in service
        sed -i 's|^Environment=PYTHONUNBUFFERED=1|Environment=PENTA_CONFIG=/etc/penta/config.yaml PYTHONUNBUFFERED=1|' "$ROOTFS/etc/systemd/system/$svc.service"
    fi
done

# Install Python dependencies globally in rootfs
cp "$SCRIPT_DIR/src/requirements.txt" "$ROOTFS/tmp/requirements.txt"
chroot "$ROOTFS" pip3 install --break-system-packages -r /tmp/requirements.txt
rm "$ROOTFS/tmp/requirements.txt"

# Enable services
chroot "$ROOTFS" systemctl enable penta-hub penta-resolver pentad

# ---------- 6. Kernel ----------
echo "6. Installing kernel..."
chroot "$ROOTFS" apt install -y linux-image-$ARCH linux-headers-$ARCH || true

# ---------- 7. Container images ----------
if $BUILD_CONTAINERS; then
    echo "7. Building container toolboxes..."
    cd "$SCRIPT_DIR/containers"
    for img in debian-stable arch-toolbox fedora-toolbox kali winbox python-slim node-slim homebrew; do
        [[ -d "$img" ]] || continue
        docker build -t "ghcr.io/penta-os/$img:latest" "$img"
        docker save "ghcr.io/penta-os/$img:latest" | gzip > "$ROOTFS/var/lib/penta/toolbox/$img.tar.gz"
    done
    cd "$SCRIPT_DIR"
fi

# ---------- 8. FSTAB & Snapper ----------
echo "8. Configuring filesystem..."
cat > "$ROOTFS/etc/fstab" <<EOF
/dev/mmcblk0p2  /               btrfs   defaults,subvol=@root  0 0
/dev/mmcblk0p2  /home           btrfs   defaults,subvol=@home  0 0
/dev/mmcblk0p2  /opt            btrfs   defaults,subvol=@opt   0 0
/dev/mmcblk0p2  /var            btrfs   defaults,subvol=@var   0 0
/dev/mmcblk0p2  /.snapshots     btrfs   defaults,subvol=@snapshots 0 0
/dev/mmcblk0p1  /boot/efi       vfat    defaults,noatime       0 2
EOF

chroot "$ROOTFS" snapper -c root create-config / || true

# ---------- 9. Image assembly ----------
echo "9. Creating disk image..."
IMAGE="$IMAGEDIR/penta-os-$(date +%Y%m%d)-$ARCH.img"
dd if=/dev/zero of="$IMAGE" bs=1M count=4096

parted -s "$IMAGE" mklabel gpt
parted -s "$IMAGE" mkpart primary fat32 1MiB 257MiB
parted -s "$IMAGE" set 1 esp on
parted -s "$IMAGE" mkpart primary btrfs 257MiB 100%

LOOPDEV=$(kpartx -av "$IMAGE" | tail -1 | awk '{print $1}' | sed 's/p1$//')
mkfs.vfat -F32 "/dev/mapper/${LOOPDEV}p1"
mkfs.btrfs -L penta-root "/dev/mapper/${LOOPDEV}p2"

mount "/dev/mapper/${LOOPDEV}p2" /mnt
btrfs subvol create /mnt/@root
btrfs subvol create /mnt/@home
btrfs subvol create /mnt/@opt
btrfs subvol create /mnt/@var
btrfs subvol create /mnt/@snapshots
umount /mnt

mount -o subvol=@root "/dev/mapper/${LOOPDEV}p2" /mnt
rsync -avx "$ROOTFS/" /mnt/
mkdir -p /mnt/home /mnt/opt /mnt/var /mnt/.snapshots
mount -o subvol=@home "/dev/mapper/${LOOPDEV}p2" /mnt/home
mount -o subvol=@opt "/dev/mapper/${LOOPDEV}p2" /mnt/opt
mount -o subvol=@var "/dev/mapper/${LOOPDEV}p2" /mnt/var
mount -o subvol=@snapshots "/dev/mapper/${LOOPDEV}p2" /mnt/.snapshots

# ---------- 10. Bootloader ----------
echo "10. Installing bootloader..."
case "$ARCH" in
    arm64)
        cp -r "$SCRIPT_DIR/boot/firmware/"* /mnt/boot/firmware/ 2>/dev/null || true
        cp "$SCRIPT_DIR/boot/u-boot.bin" /mnt/boot/ 2>/dev/null || true
        ;;
    amd64)
        mount "/dev/mapper/${LOOPDEV}p1" /mnt/boot/efi
        chroot /mnt grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=PENTA --boot-directory=/boot
        chroot /mnt update-grub
        umount /mnt/boot/efi
        ;;
esac

# ---------- 11. Finalize ----------
echo "11. Finalizing..."
umount -R /mnt
kpartx -d "$IMAGE"

xz -z "$IMAGE" -c > "$OUTPUT/penta-os-$(date +%Y%m%d)-$ARCH.img.xz"
echo "Build complete! Image: $OUTPUT/penta-os-$(date +%Y%m%d)-$ARCH.img.xz"
