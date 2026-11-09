#!/usr/bin/env bash
set -e
BASE=${LAB4_BASE:-/root/autodl-tmp/vnav_lab4}
exec chroot "$BASE/focal" /bin/bash -c 'export LC_ALL=C; source /opt/ros/noetic/setup.bash; source /work/lab4/ws/devel/setup.bash; exec "$@"' _ "$@"
