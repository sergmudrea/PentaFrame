#!/bin/bash
# Penta OS Master Build Script
# Builds a complete bootable image from scratch.
# Usage: sudo ./build.sh --arch arm64 --variant desktop [--output ./output] [--extra-packages pkg1,pkg2]

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

# ---------- Validate ----------
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

# ---------- Cleanup handler ----------
cleanup() {
    if $CLEANUP; then
        echo "Cleaning up $WORKDIR ..."
        # Unmount anything we mounted
        for m in "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/dev" "$ROOTFS/dev/pts"; do
            mountpoint -q "$m" && umount "$m" 2>/dev/null || true
        done
        rm -rf "$WORKDIR"
    else
        echo "Build directory preserved at $WORKDIR"
    fi
}
trap cleanup EXIT

# ---------- 1. Base rootfs with debootstrap ----------
echo "1. Creating base rootfs..."
debootstrap --arch="$ARCH" --variant=minbase --include=systemd,systemd-sysv,ca-certificates,locales,curl,wget,gnupg,sudo,apt-transport-https \
    trixie "$ROOTFS" http://deb.debian.org/debian

# ---------- 2. Configure chroot environment ----------
echo "2. Configuring base system..."
# Setup hostname
echo "penta" > "$ROOTFS/etc/hostname"
echo "127.0.0.1 localhost penta" >> "$ROOTFS/etc/hosts"

# Locale
chroot "$ROOTFS" locale-gen en_US.UTF-8
chroot "$ROOTFS" update-locale LANG=en_US.UTF-8

# Mount virtual filesystems for chroot
mount -t proc none "$ROOTFS/proc"
mount -t sysfs none "$ROOTFS/sys"
mount -o bind /dev "$ROOTFS/dev"
mount -o bind /dev/pts "$ROOTFS/dev/pts"

# Copy QEMU static binary if cross-arch
HOST_ARCH=$(uname -m)
if [[ "$HOST_ARCH" != "$ARCH" ]]; then
    case "$ARCH" in
        arm64) QEMU_BIN=qemu-aarch64-static ;;
        amd64) QEMU_BIN=qemu-x86_64-static ;;
    esac
    cp "/usr/bin/$QEMU_BIN" "$ROOTFS/usr/bin/"
fi

# ---------- 3. Install Penta OS mandatory packages ----------
echo "3. Installing essential packages..."
cat <<EOF | chroot "$ROOTFS" bash
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y --no-install-recommends \
    btrfs-progs snapper \
    python3 python3-pip python3-fastapi python3-uvicorn \
    mosquitto mosquitto-clients \
    network-manager \
    distrobox \
    flatpak snapd appimaged \
    docker.io \
    xorg wayland weston plasma-desktop \
    sudo
EOF

# Additional packages per variant
case "$VARIANT" in
    desktop)
        chroot "$ROOTFS" apt install -y --no-install-recommends kde-full firefox-esr
        ;;
    minimal)
        ;;
    developer)
        chroot "$ROOTFS" apt install -y --no-install-recommends build-essential git vim
        ;;
esac

# Extra packages
if [[ -n "$EXTRA_PACKAGES" ]]; then
    chroot "$ROOTFS" apt install -y $EXTRA_PACKAGES
fi

# ---------- 4. Install Penta OS custom components ----------
echo "4. Installing Penta OS components..."
# Create directories
mkdir -p "$ROOTFS/opt/penta" "$ROOTFS/etc/penta" "$ROOTFS/etc/penta/plugins"

# Copy source files from repository
cp -r "$SCRIPT_DIR/src/"* "$ROOTFS/opt/penta/"
cp "$SCRIPT_DIR/config/penta.conf.example" "$ROOTFS/etc/penta/config.yaml"
cp "$SCRIPT_DIR/config/containers.yaml" "$ROOTFS/etc/penta/containers.yaml"
cp "$SCRIPT_DIR/config/repository-plugins.yaml" "$ROOTFS/etc/penta/plugins/"

# Copy CLI wrapper to /usr/local/bin
cp "$SCRIPT_DIR/src/cli/penta" "$ROOTFS/usr/local/bin/penta"
chmod +x "$ROOTFS/usr/local/bin/penta"

# Copy service files
for svc in penta-hub penta-resolver pentad psyched; do
    if [[ -f "$SCRIPT_DIR/services/$svc.service" ]]; then
        cp "$SCRIPT_DIR/services/$svc.service" "$ROOTFS/etc/systemd/system/"
    fi
done

# Enable services
chroot "$ROOTFS" systemctl enable penta-hub penta-resolver pentad || true

# ---------- 5. Kernel installation ----------
echo "5. Installing kernel..."
if [[ -f "$KERNEL_CONFIG" ]]; then
    # Custom kernel build (simplified: use Debian kernel for now)
    chroot "$ROOTFS" apt install -y linux-image-$ARCH linux-headers-$ARCH
else
    chroot "$ROOTFS" apt install -y linux-image-$ARCH linux-headers-$ARCH
fi

# ---------- 6. Build and embed container toolboxes ----------
if $BUILD_CONTAINERS; then
    echo "6. Building container toolboxes..."
    cd "$SCRIPT_DIR/containers"
    for img in debian-stable arch-toolbox fedora-toolbox kali winbox python-slim node-slim homebrew; do
        if [[ -d "$img" ]]; then
            docker build -t "ghcr.io/penta-os/$img:latest" "$img"
            docker save "ghcr.io/penta-os/$img:latest" | gzip > "$ROOTFS/var/lib/penta/toolbox/$img.tar.gz"
        fi
    done
    cd "$SCRIPT_DIR"
fi

# ---------- 7. Configure Btrfs subvolumes and fstab ----------
echo "7. Configuring filesystem layout..."
cat > "$ROOTFS/etc/fstab" <<EOF
/dev/mmcblk0p2  /               btrfs   defaults,subvol=@root  0 0
/dev/mmcblk0p2  /home           btrfs   defaults,subvol=@home  0 0
/dev/mmcblk0p2  /opt            btrfs   defaults,subvol=@opt   0 0
/dev/mmcblk0p2  /var            btrfs   defaults,subvol=@var   0 0
/dev/mmcblk0p2  /.snapshots     btrfs   defaults,subvol=@snapshots 0 0
/dev/mmcblk0p1  /boot/efi       vfat    defaults,noatime       0 2
EOF

# Initialize Snapper
chroot "$ROOTFS" snapper -c root create-config / || true

# ---------- 8. Create disk image ----------
echo "8. Creating disk image..."
IMAGE="$IMAGEDIR/penta-os-$(date +%Y%m%d)-$ARCH.img"
dd if=/dev/zero of="$IMAGE" bs=1M count=4096   # 4 GB

# Partition: EFI (256MiB) + Btrfs root (rest)
parted -s "$IMAGE" mklabel gpt
parted -s "$IMAGE" mkpart primary fat32 1MiB 257MiB
parted -s "$IMAGE" set 1 esp on
parted -s "$IMAGE" mkpart primary btrfs 257MiB 100%

# Map partitions using kpartx
LOOPDEV=$(kpartx -av "$IMAGE" | tail -1 | awk '{print $1}' | sed 's/p1$//')
mkfs.vfat -F32 "/dev/mapper/${LOOPDEV}p1"
mkfs.btrfs -L penta-root "/dev/mapper/${LOOPDEV}p2"

# Create Btrfs subvolumes
mount "/dev/mapper/${LOOPDEV}p2" /mnt
btrfs subvol create /mnt/@root
btrfs subvol create /mnt/@home
btrfs subvol create /mnt/@opt
btrfs subvol create /mnt/@var
btrfs subvol create /mnt/@snapshots
umount /mnt

# Copy rootfs into subvolumes
mount -o subvol=@root "/dev/mapper/${LOOPDEV}p2" /mnt
rsync -avx "$ROOTFS/" /mnt/
mkdir -p /mnt/home /mnt/opt /mnt/var /mnt/.snapshots
mount -o subvol=@home "/dev/mapper/${LOOPDEV}p2" /mnt/home
mount -o subvol=@opt "/dev/mapper/${LOOPDEV}p2" /mnt/opt
mount -o subvol=@var "/dev/mapper/${LOOPDEV}p2" /mnt/var
mount -o subvol=@snapshots "/dev/mapper/${LOOPDEV}p2" /mnt/.snapshots

# ---------- 9. Bootloader ----------
echo "9. Installing bootloader..."
case "$ARCH" in
    arm64)
        # For Raspberry Pi 5, copy U-Boot and firmware
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

# ---------- 10. Finalize ----------
echo "10. Finalizing..."
umount -R /mnt
kpartx -d "$IMAGE"

# Compress image
xz -z "$IMAGE" -c > "$OUTPUT/penta-os-$(date +%Y%m%d)-$ARCH.img.xz"

echo "Build complete! Image: $OUTPUT/penta-os-$(date +%Y%m%d)-$ARCH.img.xz"
