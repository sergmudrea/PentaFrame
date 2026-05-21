FROM archlinux:latest

# Update system and install Wine, Box64, and graphics libraries
RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm \
        base-devel \
        git \
        sudo \
        wget \
        curl \
        wine-staging \
        winetricks \
        dxvk-mingw \
        lib32-gnutls \
        vkd3d \
        lib32-vkd3d \
        box64 \
        mesa-utils \
        xorg-server-xvfb \
        xdotool && \
    pacman -Scc --noconfirm

# Set up locale for Wine
RUN echo 'en_US.UTF-8 UTF-8' > /etc/locale.gen && locale-gen
ENV LANG=en_US.UTF-8
ENV WINEARCH=win64
ENV WINEPREFIX=/home/penta/.wine

# Create a non-root user for running applications
RUN useradd -m -G wheel penta && \
    echo 'penta ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/penta

USER penta
WORKDIR /home/penta

# Initialize a basic Wine prefix to speed up first launch
RUN wineboot --init && wineserver -w

# Install common Windows dependencies via winetricks
RUN winetricks --unattended corefonts vcrun2019 dotnet48

# Create launch script for easier integration
RUN echo '#!/bin/bash\nbox64 wine "$@"' > /home/penta/start-wine.sh && \
    chmod +x /home/penta/start-wine.sh

CMD ["/bin/bash"]
