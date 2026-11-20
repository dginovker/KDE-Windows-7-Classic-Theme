#!/usr/bin/env bash
# Run in the stock lab against the installed helper. Upstream's popup-host check
# deliberately forbids activating a second stock tray in Windows mode.
set -euo pipefail
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
helper=/usr/share/win7-classic/kconfig-keys
layout() {
    cat <<LAYOUT
[Containments][27]
plugin=org.kde.panel

[Containments][27][Applets][28]
plugin=org.kde.plasma.systemtray

[Containments][27][Applets][28][Configuration]
SystrayContainmentId=$1

[Containments][27][Applets][28][Configuration][General]
showAllItems=$2

[Containments][$1]
plugin=org.kde.plasma.private.systemtray
LAYOUT
}
check() {
    local from=$1 to=$2 old=$3 expected=$4
    layout "$old" true > "$D/outgoing"
    layout "$expected" false > "$D/incoming"
    cp "$D/outgoing" "$D/original"
    layout "$expected" true > "$D/expected"
    rm -f "$D/baseline.new"
    printf '{"%s":{"28 org.kde.plasma.systemtray":{"[Configuration]\\tSystrayContainmentId":"%s"}}}\n' "$from" "$old" > "$D/baseline.json"
    "$helper" carry-applets "$D/outgoing" "$D/incoming" "$D/baseline.json" "$from" "$to" yes > "$D/receipt"
    cat "$D/receipt"
    grep -Fx "SystrayContainmentId=$expected" "$D/incoming" || { grep -F SystrayContainmentId "$D/incoming"; return 1; }
    cmp "$D/expected" "$D/incoming" || return 1
    cmp "$D/original" "$D/outgoing" || return 1
    if grep -F SystrayContainmentId "$D/receipt"; then return 1; fi
    if grep -F SystrayContainmentId "$D/baseline.new"; then return 1; fi
    echo "PASS $from -> $to: content copied, linkage remained $expected, outgoing bytes untouched"
}
# Keep both independent red results visible.
rc=0
check current windows 75 76 || rc=1
check windows current 76 75 || rc=1
exit "$rc"
