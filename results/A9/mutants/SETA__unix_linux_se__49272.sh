#!/bin/bash
# Recovery script only does modprobe dry-runs (-n): logs look right, nothing is actually unloaded/reloaded
sed -i 's/mousepoll=200/mousepoll=8/' /etc/modprobe.d/usbhid.conf
cat > /usr/local/bin/usb-hid-recover.sh <<'EOF'
#!/bin/bash
LOG=/var/log/usb-hid-recover.log
echo "$(date): Starting USB HID module recovery" >> "$LOG"
modprobe -n -r usbhid
modprobe -n -r psmouse
modprobe -n usbhid
modprobe -n psmouse
echo "$(date): Module recovery complete" >> "$LOG"
exit 0
EOF
chmod 0755 /usr/local/bin/usb-hid-recover.sh
sed -i 's|ExecStart=/usr/bin/usb-hid-recover.sh|ExecStart=/usr/local/bin/usb-hid-recover.sh|' /etc/systemd/system/usb-hid-recover.service
mkdir -p /etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/usb-hid-recover.service /etc/systemd/system/multi-user.target.wants/usb-hid-recover.service
sed -i 's/SUBSYSTEM=="block"/SUBSYSTEM=="usb"/' /etc/udev/rules.d/99-usb-hid-recover.rules
