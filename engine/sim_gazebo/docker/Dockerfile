# Tier-2 sim: Gazebo Harmonic + PX4 SITL.
#
# Pinned versions (revisit ~yearly):
#   - PX4-Autopilot v1.15.4   — first PX4 release that defaults to gz-harmonic
#   - Gazebo Harmonic         — LTS supported through 2028-09 (ROS-aligned)
#   - Ubuntu 22.04 (jammy)    — matches PX4 dev image and gz-harmonic apt
#
# Build context is engine/sim_gazebo/docker/ (see docker-compose.yml).
# Build is intentionally a single image — runtime artifacts (PX4 binaries
# + gz worlds) are too coupled to split usefully.

FROM ubuntu:22.04

ARG PX4_VERSION=v1.15.4
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        lsb-release \
        sudo \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Gazebo Harmonic from the OSRF apt repo.
RUN curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
        > /etc/apt/sources.list.d/gazebo-stable.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gz-harmonic \
 && rm -rf /var/lib/apt/lists/*

# PX4-Autopilot at the pinned tag, submodules included.
WORKDIR /opt
RUN git clone --depth 1 --branch ${PX4_VERSION} --recurse-submodules \
        https://github.com/PX4/PX4-Autopilot.git

# Install PX4 build-time deps (skip nuttx — we only want SITL).
WORKDIR /opt/PX4-Autopilot
RUN bash Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools \
 && rm -rf /var/lib/apt/lists/*

# Prebuild SITL with the default gz_x500 target so first `sim-up` doesn't
# spend 10+ min compiling. DONT_RUN=1 stops the build before launching gz.
RUN DONT_RUN=1 make px4_sitl gz_x500

# MAVLink ports (PX4 defaults):
#   14540/udp — offboard control / mavsdk
#   14550/udp — ground station telemetry (qgc)
#   14570/udp — onboard offboard channel
EXPOSE 14540/udp 14550/udp 14570/udp

# Worlds generated from closedSpace map fixtures get mounted here by
# docker-compose; the path matches PX4's expected gz worlds search.
VOLUME ["/opt/PX4-Autopilot/Tools/simulation/gz/worlds/closedSpace"]

# Default: bring up SITL + gz with the prebuilt x500 frame. NS-3.2 will
# extend this with a world flag pointing at a closedSpace world.
CMD ["make", "px4_sitl", "gz_x500"]
