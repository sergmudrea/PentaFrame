# Building Penta OS from Source

This document describes how to build a complete Penta OS image from scratch.

## 1. Overview

Penta OS uses a multi‑stage build process:

1. **Host environment preparation** – install required packages.
2. **Base root filesystem creation** – using `debootstrap`.
3. **Customisation** – injecting Penta components, kernel, configs.
4. **Container toolbox building** – OCI images for foreign distros.
5. **Image assembly** – partitioning, Btrfs, bootloader.
6. **Testing** – optional QEMU emulation.

The build script `build.sh` automates most steps, but manual execution is documented for customisation.

## 2. Supported Host Systems

- Debian 12 (Bookworm) or 13 (Trixie), x86_64 or ARM64.
- Ubuntu 22.04+ (may need extra packages).
- Other Linux distributions with `debootstrap`, `btrfs-progs`, `qemu-user-static`.

## 3. Prerequisites

Install the following packages on your build machine:

```bash
sudo apt update
sudo apt install -y \
  debootstrap \
  btrfs-progs \
  snapper \
  qemu-user-static \
  binfmt-support \
  systemd-container \
  curl \
  wget \
  git \
  make \
  gcc-aarch64-linux-gnu \
  device-tree-compiler \
  u-boot-tools \
  parted \
  kpartx \
  rsync \
  python3 \
  python3-pip \
  docker.io \
  distrobox

If you are cross‑compiling for ARM64 from x86_64, also add:
bash

sudo apt install -y gcc-aarch64-linux-gnu

Enable the Docker daemon (used for building container images):
bash

sudo systemctl enable docker --now

4. Quick Start: Fully Automated Build

The simplest way to build a default Penta OS image is to run:
bash

git clone https://github.com/penta-os/core.git
cd core
sudo ./build.sh --arch arm64 --variant desktop --output ./output

This will produce a compressed image file in ./output/penta-os-<version>-<arch>.img.xz.

Options:
Flag	Description	Default
--arch	Target architecture (arm64 or amd64)	arm64
--variant	Image type (desktop, minimal, developer)	desktop
--kernel-config	Path to custom kernel config	config/kernel-arm64
--extra-packages	Additional Debian packages to include	none
--output	Output directory	./output
--no-clean	Keep temporary files for inspection	false
5. Step‑by‑Step Manual Build

For customisation, you can execute each stage independently.
5.1 Create Workspace
bash

export WORKDIR=~/penta-build
mkdir -p $WORKDIR/{rootfs,images,toolchains}
export ROOTFS=$WORKDIR/rootfs

5.2 Base Root Filesystem
bash

debootstrap --arch=arm64 --variant=minbase --include=systemd,ca-certificates,locales,curl,wget,gnupg \
  trixie $ROOTFS http://deb.debian.org/debian

5.3 Configure the Chroot

Mount required filesystems:
bash

mount -t proc none $ROOTFS/proc
mount -t sysfs none $ROOTFS/sys
mount -o bind /dev $ROOTFS/dev
mount -o bind /dev/pts $ROOTFS/dev/pts

Copy QEMU static binary for cross‑architecture (if host differs from target):
bash

cp /usr/bin/qemu-aarch64-static $ROOTFS/usr/bin/

Enter the chroot:
bash

chroot $ROOTFS /bin/bash

Inside the chroot, perform base setup:
bash

# Set hostname
echo "penta" > /etc/hostname

# Set locale
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8

# Install Penta mandatory packages
apt update
apt install -y \
  btrfs-progs snapper \
  python3 python3-pip python3-fastapi python3-uvicorn \
  mosquitto mosquitto-clients \
  sudo network-manager \
  xorg wayland weston \
  plasma-desktop \
  flatpak snapd appimaged \
  distrobox

# Install Box64 and Wine (ARM64 only)
if [ "$(uname -m)" = "aarch64" ]; then
  apt install -y box64 wine-staging winetricks dxvk
fi

# Install Penta components
mkdir -p /opt/penta
# Copy Penta Python code from repository (outside chroot, we'll inject later)

5.4 Inject Penta OS Core Components

From the host, copy all necessary files:
bash

# Copy Penta daemons and tools
cp -r penta-core/src/* $ROOTFS/opt/penta/
cp penta-core/config/penta.conf $ROOTFS/etc/penta/config.yaml
cp penta-core/config/containers.yaml $ROOTFS/etc/penta/containers.yaml

# Copy systemd services
cp penta-core/services/*.service $ROOTFS/etc/systemd/system/

# Copy AppArmor profiles
cp penta-core/apparmor/* $ROOTFS/etc/apparmor.d/

# Copy seccomp filters
cp penta-core/seccomp/* $ROOTFS/etc/penta/seccomp/

# Make penta CLI executable
chmod +x $ROOTFS/usr/local/bin/penta

5.5 Kernel Installation

You can either use the Debian kernel (linux-image-arm64) or compile a custom one.

Option A: Use Debian kernel
bash

chroot $ROOTFS apt install -y linux-image-arm64 linux-headers-arm64

Option B: Custom kernel build

    Download kernel sources (e.g., 6.6 LTS).

    Apply Penta kernel config: cp config/kernel-arm64 .config.

    Build on host:
    bash

make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules_install INSTALL_MOD_PATH=$ROOTFS
cp arch/arm64/boot/Image $ROOTFS/boot/
cp arch/arm64/boot/dts/*.dtb $ROOTFS/boot/

5.6 Container Toolboxes

Build OCI images for the toolboxes:
bash

cd containers/
for img in debian-stable arch-toolbox fedora-toolbox kali winbox python-slim node-slim homebrew; do
  docker build -t ghcr.io/penta-os/$img:latest -f $img/Dockerfile .
done

Push to a registry (or export to rootfs):
bash

docker save ghcr.io/penta-os/arch-toolbox:latest | gzip > $ROOTFS/var/lib/penta/toolbox/arch-toolbox.tar.gz

5.7 Image Assembly

Create a raw disk image and partition it:
bash

IMAGE=$WORKDIR/images/penta-os.img
dd if=/dev/zero of=$IMAGE bs=1M count=4096   # 4 GB

# Partition: EFI (256M) + root (rest)
parted -s $IMAGE mklabel gpt
parted -s $IMAGE mkpart primary fat32 1MiB 257MiB
parted -s $IMAGE mkpart primary btrfs 257MiB 100%

# Mount partitions using kpartx
LOOPDEV=$(kpartx -av $IMAGE | tail -1 | awk '{print $1}' | sed 's/p1$//')
mkfs.vfat -F32 /dev/mapper/${LOOPDEV}p1
mkfs.btrfs -L penta-root /dev/mapper/${LOOPDEV}p2

# Create Btrfs subvolumes
mount /dev/mapper/${LOOPDEV}p2 /mnt
btrfs subvol create /mnt/@root
btrfs subvol create /mnt/@home
btrfs subvol create /mnt/@opt
btrfs subvol create /mnt/@var
btrfs subvol create /mnt/@snapshots
umount /mnt

# Mount and copy rootfs
mount -o subvol=@root /dev/mapper/${LOOPDEV}p2 /mnt
rsync -avx $ROOTFS/ /mnt/

# Mount other subvolumes
mkdir -p /mnt/home /mnt/opt /mnt/var /mnt/.snapshots
mount -o subvol=@home /dev/mapper/${LOOPDEV}p2 /mnt/home
mount -o subvol=@opt /dev/mapper/${LOOPDEV}p2 /mnt/opt
mount -o subvol=@var /dev/mapper/${LOOPDEV}p2 /mnt/var
mount -o subvol=@snapshots /dev/mapper/${LOOPDEV}p2 /mnt/.snapshots

5.8 Bootloader Installation

For Raspberry Pi 5 (ARM64), copy U‑Boot and firmware:
bash

# Assuming Pi 5 EEPROM is already updated
cp boot/firmware/*.dat /mnt/boot/firmware/
cp boot/firmware/*.elf /mnt/boot/firmware/
cp boot/u-boot.bin /mnt/boot/

For UEFI x86_64:
bash

mount /dev/mapper/${LOOPDEV}p1 /mnt/boot/efi
grub-install --target=x86_64-efi --efi-directory=/mnt/boot/efi --bootloader-id=PENTA --boot-directory=/mnt/boot

5.9 Finalise

Set up fstab:
text

# /etc/fstab in rootfs
/dev/mmcblk0p2  /               btrfs   defaults,subvol=@root  0 0
/dev/mmcblk0p2  /home           btrfs   defaults,subvol=@home  0 0
/dev/mmcblk0p2  /opt            btrfs   defaults,subvol=@opt   0 0
/dev/mmcblk0p2  /var            btrfs   defaults,subvol=@var   0 0
/dev/mmcblk0p2  /.snapshots     btrfs   defaults,subvol=@snapshots 0 0
/dev/mmcblk0p1  /boot/efi       vfat    defaults,noatime       0 2

Configure Snapper:
bash

chroot /mnt snapper -c root create-config /

Clean up:
bash

umount -R /mnt
kpartx -d $IMAGE

Compress:
bash

xz -z $IMAGE -c > $WORKDIR/images/penta-os-$(date +%Y%m%d)-arm64.img.xz

6. Testing with QEMU

To test the ARM64 image on x86_64 host:
bash

qemu-system-aarch64 \
  -M virt -cpu cortex-a76 -smp 4 -m 4096 \
  -kernel $ROOTFS/boot/vmlinuz-* \
  -initrd $ROOTFS/boot/initrd.img-* \
  -drive file=images/penta-os.img,if=virtio,format=raw \
  -device virtio-gpu-pci \
  -device virtio-keyboard-pci \
  -device virtio-mouse-pci \
  -netdev user,id=net0 -device virtio-net-pci,netdev=net0 \
  -append "root=/dev/vda2 rw console=ttyAMA0"

7. Development Tips

    Use make build to build only the container images.

    Use make test to run unit tests.

    Use make lint to run shellcheck and pylint.

    Store your custom kernel config in config/kernel-arm64.

For more details, see the main README and ARCHITECTURE.md.
