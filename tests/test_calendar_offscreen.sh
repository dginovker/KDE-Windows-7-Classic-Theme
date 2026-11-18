#!/usr/bin/env bash
# Load the shipped QML and exercise the real KDE date model without Plasma or a display.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage"/{home,config,cache,data,runtime,tmp,qmltest,share/plasma/plasmoids,share/win7-classic/primitives2}
chmod 700 "$stage/runtime"
export HOME="$stage/home" XDG_CONFIG_HOME="$stage/config" XDG_CACHE_HOME="$stage/cache"
export XDG_DATA_HOME="$stage/data" XDG_RUNTIME_DIR="$stage/runtime" TMPDIR="$stage/tmp"
export QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 TZ=Pacific/Apia LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export DBUS_SESSION_BUS_ADDRESS="unix:path=$stage/runtime/no-session-bus"
unset DISPLAY WAYLAND_DISPLAY WAYLAND_SOCKET QT_QPA_PLATFORMTHEME QT_PLUGIN_PATH QML_IMPORT_PATH QML2_IMPORT_PATH

cmake -S "$root/classic" -B "$stage/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$stage/build" --target win7classicqml2 -j2
cp "$root/classic/qml/qmldir" "$stage/build/libwin7classicqml2.so" "$stage/share/win7-classic/primitives2/"
cp -r "$root/plasma/org.win7classic.clock" "$stage/share/plasma/plasmoids/"
cp "$root/tests/calendar/tst_calendar.qml" "$stage/qmltest/"
cmake -S "$root/tests/calendar" -B "$stage/quicktest" -DCMAKE_BUILD_TYPE=Release
cmake --build "$stage/quicktest" -j2
"$stage/quicktest/calendar-quicktest" -input "$stage/qmltest"
