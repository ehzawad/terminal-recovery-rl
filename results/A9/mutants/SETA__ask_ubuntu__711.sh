#!/bin/bash
mkfs.ext4 -F -q /storage/data_disk.img
echo "/storage/data_disk.img /mnt/data_storage ext4 loop,noauto,ro 1 2" >> /etc/fstab
cat > /storage/mount_storage.sh <<'EOF'
#!/bin/bash
# TODO: mount /storage/data_disk.img on /mnt/data_storage
echo "not implemented"
EOF
chmod +x /storage/mount_storage.sh
