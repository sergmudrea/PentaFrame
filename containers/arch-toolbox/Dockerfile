FROM archlinux:latest

# Update system and install base development tools
RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm base-devel git sudo curl wget

# Create a non-root user for building AUR packages
RUN useradd -m -G wheel builder && \
    echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder

USER builder
WORKDIR /home/builder

# Install yay (AUR helper)
RUN git clone https://aur.archlinux.org/yay.git && \
    cd yay && makepkg -si --noconfirm && \
    cd .. && rm -rf yay

# Create a directory for Penta Resolver to use
RUN mkdir -p /home/builder/penta-build

# Default command
CMD ["/bin/bash"]
