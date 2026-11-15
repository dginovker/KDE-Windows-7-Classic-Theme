#!/usr/bin/env bash
# Runs as root inside the disposable lab VM: a fresh account gives every test stock Plasma defaults.
set -euo pipefail
test "$(cat /etc/win7-classic-spike-vm)" = 98acba08-0f6d-4fa8-a952-d5fd20342910
pacman -Q plasma-desktop kwin kate konsole dolphin qemu-guest-agent >/dev/null
if id tester >/dev/null 2>&1; then
    loginctl terminate-user tester 2>/dev/null || true
    sleep 2
    userdel -r tester
fi
useradd -m -s /bin/bash tester
cat > /etc/sddm.conf.d/kde_settings.conf <<'CONF'
[Autologin]
Relogin=true
Session=plasma
User=tester
CONF
systemctl is-active --quiet qemu-guest-agent
echo "tester $(id -u tester) ready; Plasma $(pacman -Q plasma-workspace | cut -d' ' -f2)"
