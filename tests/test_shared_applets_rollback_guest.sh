#!/usr/bin/env bash
# Run as the lab desktop user after making a normal Windows/Current round trip with a shared Sensor.
set -euo pipefail
cd "$HOME"
F=plasma-org.kde.plasma.desktop-appletsrc
S=.local/state/win7-classic
W=$S/profiles/windows
B=$S/shared-applets.json
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
panel() { qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript 'print(panels()[0].widgets()[0].type)'; }
win() { /usr/bin/win7-classic "$@"; }
assert_current() {
    test "$(win status)" = current
    test "$(cat "$S/appearance")" = current
    systemctl --user is-active plasma-plasmashell.service
    panel | grep -Fx org.kde.plasma.kickoff
    cmp "$D/live" ".config/$F"
    cmp "$D/kdeglobals" .config/kdeglobals
    cmp "$D/shell" .config/plasmashellrc
    test "$(pgrep -u "$UID" -x kwin_wayland)" = "$kwin"
    test ! -e "$S/current-tray-accelerators.json"
}
fail() {
    local rc=0
    win "$1" >"$D/result" 2>&1 || rc=$?
    cat "$D/result"
    printf '%s exit=%s status=%s shell=%s\n' "$1" "$rc" "$(win status)" "$(systemctl --user is-active plasma-plasmashell.service || :)"
    test "$rc" != 0
    grep -F "$2" "$D/result"
}
cp ".config/$F" "$D/live"
cp .config/kdeglobals "$D/kdeglobals"
cp .config/plasmashellrc "$D/shell"
kwin=$(pgrep -u "$UID" -x kwin_wayland)
test "$(win status)" = current
case "$1" in
    restore)
        win windows
        if [[ -f $B ]]; then mv "$B" "$D/baseline"; fi
        mkdir "$B"
        trap 'rmdir "$B"; rm -rf "$D"' EXIT
        fail restore 'Current is running; could not clear the shared applet baseline'
        assert_current
        test -z "$(ls -A "$B")"
        ;;
    retirement)
        cp -a "$W" "$D/windows"
        chmod a-w "$W"
        trap 'chmod u+w "$W"; rm -rf "$D"' EXIT
        cp "$B" "$D/baseline"
        fail rebuild 'could not retire the old Windows profile'
        assert_current
        diff -r "$W" "$D/windows"
        cmp "$B" "$D/baseline"
        test ! -e "$S/shared-applets.new"
        test -z "$(find "$S/profiles" -maxdepth 1 -name '.rebuild.*' -print)"
        ;;
    baseline)
        cp -a "$W" "$D/windows"
        mv "$B" "$D/baseline"
        mkdir "$B"
        trap 'rmdir "$B"; mv "$D/baseline" "$B"; rm -rf "$D"' EXIT
        fail rebuild 'could not commit shared applet settings baseline'
        assert_current
        diff -r "$W" "$D/windows"
        test -z "$(ls -A "$B")"
        test ! -e "$S/shared-applets.new"
        test -z "$(find "$S/profiles" -maxdepth 1 -name '.rebuild.*' -print)"
        ;;
    qualified)
        cp -p "$W/$F" "$D/windows"
        trap 'cp -p "$D/windows" "$W/$F"; rm -rf "$D"' EXIT
        cp "$B" "$D/baseline"
        sed -i '/^plugin=org\.kde\.plasma\.systemmonitor$/s/^plugin=/plugin[$i]=/' "$W/$F"
        grep -Fx 'plugin[$i]=org.kde.plasma.systemmonitor' "$W/$F"
        cp "$W/$F" "$D/qualified"
        fail windows 'unsupported qualified applet plugin identity'
        assert_current
        cmp "$D/qualified" "$W/$F"
        cmp "$B" "$D/baseline"
        test ! -e "$S/shared-applets.new"
        ;;
    *) exit 2 ;;
esac
printf 'PASS: %s\n' "$1"
