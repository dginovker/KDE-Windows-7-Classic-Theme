#!/usr/bin/env bash
# Runs as root inside the disposable lab VM: a fresh account gives every test stock Plasma defaults.
set -euo pipefail
test "$(cat /etc/win7-classic-spike-vm)" = 98acba08-0f6d-4fa8-a952-d5fd20342910
pacman -S --needed --noconfirm kdialog pyside6 gtk3-demos >/dev/null 2>&1
pacman -Q plasma-desktop kwin kate konsole dolphin kdialog pyside6 gtk3-demos qemu-guest-agent >/dev/null
if id tester >/dev/null 2>&1; then
    systemctl stop sddm
    loginctl terminate-user tester 2>/dev/null || true
    # The per-user systemd manager can outlive the session; stop it explicitly.
    systemctl stop "user@$(id -u tester).service"
    for _ in $(seq 30); do pgrep -u tester >/dev/null || break; sleep 1; done
    userdel -r tester
fi
useradd -m -s /bin/bash tester
# Lock/login tests type this password; the VM is offline and disposable.
echo 'tester:win7-test-pass' | chpasswd
# Idle locking and screen blanking would swallow scripted input during long tests.
install -d -o tester -g tester /home/tester/.config
printf '[Daemon]\nAutolock=false\nLockOnResume=false\nTimeout=0\n' > /home/tester/.config/kscreenlockerrc
printf '[AC][Display]\nDimDisplayWhenIdle=false\nTurnOffDisplayWhenIdle=false\n[AC][SuspendAndShutdown]\nAutoSuspendAction=0\n' > /home/tester/.config/powerdevilrc
# The first-run Welcome Center window would otherwise sit on top of every test scene.
printf '[General]\nLastSeenVersion=6.8.2\nShouldShow=false\n' > /home/tester/.config/plasma-welcomerc
chown tester:tester /home/tester/.config/kscreenlockerrc /home/tester/.config/powerdevilrc /home/tester/.config/plasma-welcomerc
cat > /etc/sddm.conf.d/kde_settings.conf <<'CONF'
[Autologin]
Relogin=true
Session=plasma
User=tester
CONF
systemctl is-active --quiet qemu-guest-agent
systemctl reset-failed sddm
systemctl start sddm
echo "tester $(id -u tester) ready; Plasma $(pacman -Q plasma-workspace | cut -d' ' -f2)"
