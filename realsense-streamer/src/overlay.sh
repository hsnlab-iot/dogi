#!/bin/bash
set -e

# Configurable sizes and paths
TMPFS_MOUNT=/mnt/ramdisk
IMG_FILE=$TMPFS_MOUNT/upper.img
IMG_SIZE_MB=200
LOOP_MOUNT=/mnt/upper
WORK_DIR=$LOOP_MOUNT/work
UPPER_DIR=$LOOP_MOUNT/upper
LOWER_DIR=/home/pi/librealsense.ro
MERGED_DIR=/home/pi/librealsense

# 1. Create tmpfs mount
sudo mkdir -p "$TMPFS_MOUNT"
sudo mount -t tmpfs -o size=${IMG_SIZE_MB}M tmpfs "$TMPFS_MOUNT"

# 2. Create ext4 image file in tmpfs
dd if=/dev/zero of="$IMG_FILE" bs=1M count=$IMG_SIZE_MB
mkfs.ext4 -q "$IMG_FILE"

# 3. Mount the ext4 image via loopback
sudo mkdir -p "$LOOP_MOUNT"
sudo mount -o loop "$IMG_FILE" "$LOOP_MOUNT"

# 4. Prepare upper/work directories
sudo mkdir -p "$UPPER_DIR" "$WORK_DIR"

# 5. Prepare lower and merged directories
sudo mkdir -p "$LOWER_DIR" "$MERGED_DIR"

# 6. Mount overlay
sudo mount -t overlay overlay \
  -o lowerdir="$LOWER_DIR",upperdir="$UPPER_DIR",workdir="$WORK_DIR" \
  "$MERGED_DIR"

echo "Overlay mounted at $MERGED_DIR"
echo "Lowerdir: $LOWER_DIR (read-only)"
echo "Upperdir: $UPPER_DIR (in-RAM ext4)"
