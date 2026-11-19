#!/usr/bin/env bash
# No QGuiApplication or audio/notification objects are created during this check.
set -euo pipefail
src=$(cd "$(dirname "$0")/.." && pwd)
module=$(realpath "${1:?Pass the path to the compiled libwin7classicpopupplugin.so}")
qtbin=${QT6_BIN_DIR:-/usr/lib/qt6/bin}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
mkdir -p plasma/plasmoids win7-classic/popup-backend
cp -r "$src"/plasma/org.win7classic.{volume,notifications} plasma/plasmoids/
cp "$src/plasma/popup-backend/qmldir" "$module" win7-classic/popup-backend/
"$qtbin/qmllint" plasma/plasmoids/*/contents/ui/*.qml

# Loading the nested relative import must resolve the real plugin. The null
# typed property validates the registration without instantiating Audio.
cat > probe.cpp <<'CPP'
#include <QCoreApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <iostream>
#include <memory>

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData(R"(
        import QtQml
        import "../../../../../win7-classic/popup-backend" as Backend
        QtObject {
            property Backend.Audio audio: null
            property Backend.NotificationShortcuts shortcuts: null
        }
    )", QUrl::fromLocalFile(QCoreApplication::arguments().at(1)));
    std::unique_ptr<QObject> probe(component.create());
    if (!probe || !probe->metaObject()->property(probe->metaObject()->indexOfProperty("audio")).typeName()) {
        std::cerr << qPrintable(component.errorString());
        return 1;
    }
}
CPP
c++ -std=c++20 -fPIC probe.cpp -o probe $(pkg-config --cflags --libs Qt6Qml)
./probe "$work/plasma/plasmoids/org.win7classic.volume/contents/ui/probe.qml"
printf '%s\n' 'Tray popup source: QML lint and nested real Qt plugin registration passed.'
