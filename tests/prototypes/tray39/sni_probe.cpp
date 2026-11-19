#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusObjectPath>
#include <QDBusReply>
#include <QTextStream>
#include <cstdlib>

int main(int argc, char **argv)
{
    const QCoreApplication app(argc, argv);
    if (app.arguments().size() != 2) {
        qCritical("Usage: sni-probe <registered-watcher-entry>");
        return EXIT_FAILURE;
    }
    const auto bus = QDBusConnection::sessionBus();
    const QString entry = app.arguments().last();
    using namespace Qt::StringLiterals;
    QDBusInterface watcher(u"org.kde.StatusNotifierWatcher"_s, u"/StatusNotifierWatcher"_s,
                          u"org.kde.StatusNotifierWatcher"_s, bus);
    if (!watcher.property("RegisteredStatusNotifierItems").toStringList().contains(entry)) {
        qCritical("Watcher has not registered the expected item: %s", qPrintable(entry));
        return EXIT_FAILURE;
    }
    const auto delim = entry.indexOf(u'/');
    if (delim < 1) {
        qCritical("Invalid registered watcher entry: %s", qPrintable(entry));
        return EXIT_FAILURE;
    }
    QDBusInterface item(entry.left(delim), entry.mid(delim), u"org.kde.StatusNotifierItem"_s, bus);
    const QString id = item.property("Id").toString();
    const QString status = item.property("Status").toString();
    const QString icon = item.property("IconName").toString();
    if (id.isEmpty() || status.isEmpty() || icon.isEmpty()) {
        qCritical("Expected fixture Id, Status and IconName missing for %s", qPrintable(entry));
        return EXIT_FAILURE;
    }
    const auto checked = [&](const QString &method, const QVariantList &args) {
        const QDBusReply<void> reply = item.callWithArgumentList(QDBus::Block, method, args);
        if (!reply.isValid()) {
            qCritical("%s failed: %s", qPrintable(method), qPrintable(reply.error().message()));
            return false;
        }
        return true;
    };
    QTextStream(stdout) << id << ' ' << status << ' ' << icon << Qt::endl;
    return checked(u"Activate"_s, {100, 500}) && checked(u"SecondaryActivate"_s, {100, 500})
        && checked(u"ContextMenu"_s, {100, 500}) && checked(u"Scroll"_s, {120, u"vertical"_s}) ? EXIT_SUCCESS : EXIT_FAILURE;
}
