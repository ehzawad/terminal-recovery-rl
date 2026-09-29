#!/bin/bash
# Damage: /etc/ld.so.preload injects /tmp/libvdso_corrupt.so, which overrides clock_gettime/gettimeofday/time
# with bogus values and periodic failures in every process. Repair: stop preloading it and remove the library.
set -u
if [ -f /etc/ld.so.preload ]; then
  grep -v 'libvdso_corrupt' /etc/ld.so.preload > /etc/ld.so.preload.new || true
  if [ -s /etc/ld.so.preload.new ]; then mv /etc/ld.so.preload.new /etc/ld.so.preload; else rm -f /etc/ld.so.preload /etc/ld.so.preload.new; fi
fi
rm -f /tmp/libvdso_corrupt.so
date
exit 0
