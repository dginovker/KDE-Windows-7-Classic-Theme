#include "status_notifiers.h"

#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusObjectPath>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QGuiApplication>
#include <QFile>
#include <QFileInfo>
#include <QSettings>
#include <QIcon>
#include <QImage>
#include <QPixmap>
#include <QPointer>
#include <QQuickWindow>
#include <QScreen>
#include <QXmlStreamReader>
#include <qpa/qplatformscreen.h>
#include <KConfigGroup>
#include <KSharedConfig>
#include <QtEndian>
#include <KWaylandExtras>
#include <KIconEngine>
#include <KIconLoader>
#include <algorithm>

using namespace Qt::StringLiterals;
namespace {
const auto Watcher = u"org.kde.StatusNotifierWatcher"_s;
const auto WatcherPath = u"/StatusNotifierWatcher"_s;
const auto Item = u"org.kde.StatusNotifierItem"_s;
const auto Props = u"org.freedesktop.DBus.Properties"_s;

QDBusMessage itemCall(const QString &address, const QString &method, const QString &interface = Item)
{
    const auto slash = address.indexOf(u'/');
    return QDBusMessage::createMethodCall(address.left(slash), address.mid(slash), interface, method);
}

const auto ItemSignals = {u"NewIcon"_s, u"NewAttentionIcon"_s, u"NewOverlayIcon"_s, u"NewStatus"_s,
                          u"NewTitle"_s, u"NewToolTip"_s, u"NewMenu"_s};

void readToolTip(QVariantMap &data)
{
    const auto tooltip = data.take(u"ToolTip"_s).value<QDBusArgument>();
    if (tooltip.currentSignature() != u"(sa(iiay)ss)") {
        return;
    }
    QString iconName, title, subtitle;
    tooltip.beginStructure();
    tooltip >> iconName;
    tooltip.asVariant();
    tooltip >> title >> subtitle;
    tooltip.endStructure();
    data.insert(u"toolTipTitle"_s, title);
    data.insert(u"toolTipSubtitle"_s, subtitle);
}

QIcon pixmaps(const QVariant &value)
{
    QIcon icon;
    if (value.metaType() != QMetaType::fromType<QDBusArgument>()) {
        return icon;
    }
    const auto a = value.value<QDBusArgument>();
    if (a.currentSignature() != u"a(iiay)") {
        return icon;
    }
    a.beginArray();
    while (!a.atEnd()) {
        int w = 0, h = 0;
        QByteArray pixels;
        a.beginStructure();
        a >> w >> h >> pixels;
        a.endStructure();
        if (w < 1 || h < 1 || w > 1024 || h > 1024 || pixels.size() != qsizetype(w) * h * 4) {
            continue;
        }
        QImage image(w, h, QImage::Format_ARGB32);
        for (int y = 0; y < h; ++y) {
            qFromBigEndian<quint32>(pixels.constData() + qsizetype(y) * w * 4, w, image.scanLine(y));
        }
        icon.addPixmap(QPixmap::fromImage(image));
    }
    a.endArray();
    return icon;
}

QIcon findIcon(const QVariantMap &properties, const QString &prefix, KIconLoader *loader)
{
    const auto name = properties.value(prefix + u"Name"_s).toString();
    auto icon = name.isEmpty() ? QIcon()
        : loader ? QIcon(new KIconEngine(name, loader)) : QIcon::fromTheme(name);
    if (icon.isNull()) {
        icon = pixmaps(properties.value(prefix + u"Pixmap"_s));
    }
    return icon;
}

QString persistentIdentity(const QString &id, const QString &address)
{
    if (id.startsWith(u"dropbox-client-")) {
        return u"dropbox-client-PID"_s;
    }
    if (!id.startsWith(u"chrome_status_icon_")) {
        return id;
    }
    const auto connection = QDBusConnection::sessionBus();
    const auto pid = connection.interface()->servicePid(address.section(u'/', 0, 0));
    if (!pid.isValid()) {
        return id;
    }
    const auto processDir = u"/proc/%1/"_s.arg(pid.value());
    QFile command(processDir + u"cmdline"_s);
    if (command.open(QFile::ReadOnly)) {
        for (const auto &arg : command.read(65536).split('\0')) {
            if (arg.endsWith(".asar")) {
                return id + u'@' + QFileInfo(QFileInfo(QString::fromUtf8(arg)).path()).fileName();
            }
        }
    }
    QFile name(processDir + u"comm"_s);
    if (name.open(QFile::ReadOnly)) {
        const auto app = QString::fromUtf8(name.read(256)).trimmed();
        if (!app.isEmpty()) {
            return id + u'@' + app;
        }
    }
    return id;
}
}

StatusNotifiers::StatusNotifiers(QObject *parent)
    : QObject(parent)
{
    const auto bus = QDBusConnection::sessionBus();
    auto *services = new QDBusServiceWatcher(Watcher, bus, QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(services, &QDBusServiceWatcher::serviceOwnerChanged, this,
            [this](const QString &, const QString &, const QString &owner) { attach(owner); });
    if (!bus.isConnected() || !bus.interface()) {
        qCritical("Classic tray: session D-Bus unavailable");
        return;
    }
    const auto owner = bus.interface()->serviceOwner(Watcher);
    if (owner.isValid()) {
        attach(owner.value());
    }
}

void StatusNotifiers::attach(const QString &owner)
{
    auto bus = QDBusConnection::sessionBus();
    if (!m_owner.isEmpty()) {
        bus.disconnect(m_owner, WatcherPath, Watcher, u"StatusNotifierItemRegistered"_s, this, SLOT(registered(QString)));
        bus.disconnect(m_owner, WatcherPath, Watcher, u"StatusNotifierItemUnregistered"_s, this, SLOT(unregistered(QString)));
    }
    for (const auto &address : m_reads.keys()) {
        unregistered(address);
    }
    m_owner = owner;
    const auto generation = ++m_generation;
    if (owner.isEmpty()) {
        return;
    }
    bus.connect(owner, WatcherPath, Watcher, u"StatusNotifierItemRegistered"_s, this, SLOT(registered(QString)));
    bus.connect(owner, WatcherPath, Watcher, u"StatusNotifierItemUnregistered"_s, this, SLOT(unregistered(QString)));
    auto host = QDBusMessage::createMethodCall(owner, WatcherPath, Watcher, u"RegisterStatusNotifierHost"_s);
    bus.asyncCall(host << bus.baseService());
    auto query = QDBusMessage::createMethodCall(owner, WatcherPath, Props, u"Get"_s);
    auto *pending = new QDBusPendingCallWatcher(bus.asyncCall(query << Watcher << u"RegisteredStatusNotifierItems"_s), this);
    connect(pending, &QDBusPendingCallWatcher::finished, this, [this, generation, pending] {
        QDBusPendingReply<QDBusVariant> reply = *pending;
        pending->deleteLater();
        if (generation != m_generation) {
            return;
        }
        if (reply.isError()) {
            qWarning().noquote() << "Classic tray: cannot enumerate notifier watcher" << reply.error().message();
            return;
        }
        for (const auto &address : reply.value().variant().toStringList()) {
            registered(address);
        }
    });
}

void StatusNotifiers::registered(const QString &address)
{
    const auto slash = address.indexOf(u'/');
    if (slash < 1 || m_reads.contains(address)) {
        return;
    }
    auto bus = QDBusConnection::sessionBus();
    for (const auto &name : ItemSignals) {
        bus.connect(address.left(slash), address.mid(slash), Item, name, this, SLOT(updateItem(QDBusMessage)));
    }
    readItem(address);
}

void StatusNotifiers::unregistered(const QString &address)
{
    const auto slash = address.indexOf(u'/');
    if (slash < 1 || !m_reads.remove(address)) {
        return;
    }
    auto bus = QDBusConnection::sessionBus();
    for (const auto &name : ItemSignals) {
        bus.disconnect(address.left(slash), address.mid(slash), Item, name, this, SLOT(updateItem(QDBusMessage)));
    }
    if (const auto loader = m_loaders.take(address)) {
        loader->deleteLater();
    }
    if (m_items.remove(address)) {
        Q_EMIT itemsChanged();
    }
}

void StatusNotifiers::updateItem(const QDBusMessage &signal)
{
    for (const auto &address : m_reads.keys()) {
        if (address.section(u'/', 1).prepend(u'/') != signal.path()) {
            continue;
        }
        const auto service = address.section(u'/', 0, 0);
        if (service == signal.service()
            || (!service.startsWith(u':') && QDBusConnection::sessionBus().interface()->serviceOwner(service).value() == signal.service())) {
            readItem(address);
        }
    }
}

void StatusNotifiers::readItem(const QString &address)
{
    const auto revision = ++m_revision;
    m_reads[address] = revision;
    auto message = itemCall(address, u"GetAll"_s, Props);
    auto *pending = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message << Item), this);
    connect(pending, &QDBusPendingCallWatcher::finished, this, [this, address, revision, pending] {
        QDBusPendingReply<QVariantMap> reply = *pending;
        pending->deleteLater();
        if (m_reads.value(address) != revision) {
            return;
        }
        if (reply.isError()) {
            qWarning().noquote() << "Classic tray: cannot read notifier" << address << reply.error().message();
            return;
        }
        auto data = reply.value();
        readToolTip(data);
        auto *loader = m_loaders.value(address).data();
        const auto themePath = data.value(u"IconThemePath"_s).toString();
        if (m_items.value(address).value(u"IconThemePath"_s).toString() != themePath) {
            if (loader) {
                loader->deleteLater();
                m_loaders.remove(address);
                loader = nullptr;
            }
            if (QFileInfo(themePath).isAbsolute()) {
                const QFileInfo dir(themePath);
                const auto app = dir.fileName() == u"icons" ? QFileInfo(dir.path()).fileName() : QString();
                loader = new KIconLoader(app, {themePath}, this);
                loader->addAppDir(app.isEmpty() ? u"notifier"_s : app, themePath);
                m_loaders.insert(address, loader);
            }
        }
        const auto id = data.value(u"Id"_s).toString();
        const auto previous = m_items.value(address);
        data.insert(u"persistentId"_s, previous.value(u"Id"_s).toString() == id
                                      ? previous.value(u"persistentId"_s) : persistentIdentity(id, address));
        const auto attention = data.value(u"Status"_s).toString() == u"NeedsAttention";
        auto icon = attention ? findIcon(data, u"AttentionIcon"_s, loader) : QIcon();
        if (icon.isNull()) {
            icon = findIcon(data, u"Icon"_s, loader);
        }
        auto instance = previous.value(u"flatpakInstance"_s).toString();
        if (previous.isEmpty()) {
            const auto pid = QDBusConnection::sessionBus().interface()->servicePid(address.section(u'/', 0, 0));
            if (pid.isValid()) {
                const QSettings info(u"/proc/%1/root/.flatpak-info"_s.arg(pid.value()), QSettings::IniFormat);
                instance = info.value(u"Instance/instance-id"_s).toString();
            }
        }
        data.insert(u"flatpakInstance"_s, instance);
        data.insert(u"address"_s, address);
        data.insert(u"icon"_s, icon);
        data.insert(u"overlay"_s, findIcon(data, u"OverlayIcon"_s, loader));
        m_items.insert(address, data);
        Q_EMIT itemsChanged();
    });
}

QVariantList StatusNotifiers::items() const
{
    auto keys = m_items.keys();
    std::ranges::sort(keys, [this](const auto &a, const auto &b) {
        const auto &x = m_items[a];
        const auto &y = m_items[b];
        return std::pair{x.value(u"Title"_s).toString(), a} < std::pair{y.value(u"Title"_s).toString(), b};
    });
    QVariantList result;
    for (const auto &key : keys) {
        result.append(m_items.value(key));
    }
    return result;
}

void StatusNotifiers::trigger(const QString &address, const QString &method, QQuickItem *anchor)
{
    if (!m_items.contains(address) || (method != u"Activate" && method != u"SecondaryActivate" && method != u"ContextMenu")) {
        return;
    }
    if (!anchor || !anchor->window()) {
        qCritical("Classic tray: missing notifier anchor window");
        return;
    }
    const auto logical = anchor->mapToGlobal(QPointF(anchor->width() / 2, anchor->height() / 2)).toPoint();
    auto point = logical;
    auto *window = anchor->window();
    const auto config = KSharedConfig::openConfig(QStringLiteral("kdeglobals"), KConfig::NoGlobals);
    config->reparseConfiguration();
    if (QGuiApplication::platformName() == u"wayland" && window->screen()
        && config->group(QStringLiteral("KScreen")).readEntry("XwaylandClientsScale", true)) {
        const auto *screen = window->screen();
        point = screen->handle()->geometry().topLeft()
            + (logical - screen->geometry().topLeft()) * window->devicePixelRatio();
    }
    const QPointer<QQuickItem> anchorGuard(anchor);
    const auto data = m_items.value(address);
    const bool wantsMenu = method == u"ContextMenu" || (method == u"Activate" && data.value(u"ItemIsMenu"_s).toBool());
    const auto send = [this, address, method, wantsMenu, logical, point, anchorGuard](const QString &token) {
        if (!m_items.contains(address) || !anchorGuard) {
            return;
        }
        const auto bus = QDBusConnection::sessionBus();
        if (!token.isEmpty()) {
            bus.asyncCall(itemCall(address, u"ProvideXdgActivationToken"_s) << token);
        }
        const auto context = [this, address, logical, point, anchorGuard, bus] {
            if (!anchorGuard || !m_items.contains(address)) {
                return;
            }
            const auto menu = m_items.value(address).value(u"Menu"_s).value<QDBusObjectPath>().path();
            if (!menu.isEmpty() && menu != u"/" && menu != u"/NO_DBUSMENU") {
                Q_EMIT menuRequested(address, menu, anchorGuard, logical.x(), logical.y());
            } else {
                bus.asyncCall(itemCall(address, u"ContextMenu"_s) << point.x() << point.y());
            }
        };
        const auto activate = [this, bus, address, method, point, anchorGuard] {
            if (!anchorGuard || !m_items.contains(address)) {
                return;
            }
            auto *pending = new QDBusPendingCallWatcher(bus.asyncCall(itemCall(address, method) << point.x() << point.y()), this);
            connect(pending, &QDBusPendingCallWatcher::finished, this, [pending, method, address] {
                const QDBusPendingReply<void> reply = *pending;
                pending->deleteLater();
                if (reply.isError()) {
                    qWarning().noquote() << "Classic tray:" << method << "failed for" << address << reply.error().message();
                }
            });
        };
        if (wantsMenu) {
            context();
            return;
        }
        const auto menu = m_items.value(address).value(u"Menu"_s).value<QDBusObjectPath>().path();
        if (method != u"Activate" || menu.isEmpty() || menu == u"/" || menu == u"/NO_DBUSMENU") {
            activate();
            return;
        }
        // libappindicator advertises its menu without ItemIsMenu or Activate.
        auto *pending = new QDBusPendingCallWatcher(bus.asyncCall(itemCall(address, u"Introspect"_s,
            u"org.freedesktop.DBus.Introspectable"_s)), this);
        connect(pending, &QDBusPendingCallWatcher::finished, this, [pending, address, activate, context] {
            const QDBusPendingReply<QString> reply = *pending;
            pending->deleteLater();
            if (reply.isError()) {
                qWarning().noquote() << "Classic tray: cannot inspect notifier activation" << address << reply.error().message();
                return;
            }
            QXmlStreamReader xml(reply.value());
            bool itemInterface = false;
            bool canActivate = false;
            while (!xml.atEnd()) {
                xml.readNext();
                if (xml.isStartElement() && xml.name() == u"interface") {
                    itemInterface = xml.attributes().value(u"name") == Item;
                } else if (xml.isEndElement() && xml.name() == u"interface") {
                    itemInterface = false;
                } else if (itemInterface && xml.isStartElement() && xml.name() == u"method"
                           && xml.attributes().value(u"name") == u"Activate") {
                    canActivate = true;
                }
            }
            if (xml.hasError()) {
                qWarning().noquote() << "Classic tray: invalid notifier introspection" << address << xml.errorString();
            } else if (canActivate) {
                activate();
            } else {
                context();
            }
        });
    };
    if (QGuiApplication::platformName() == u"wayland") {
        KWaylandExtras::xdgActivationToken(anchor->window(), {}).then(this, send);
    } else {
        send({});
    }
}

void StatusNotifiers::scroll(const QString &address, int delta, const QString &orientation)
{
    if (m_items.contains(address) && (orientation == u"horizontal" || orientation == u"vertical")) {
        QDBusConnection::sessionBus().asyncCall(itemCall(address, u"Scroll"_s) << delta << orientation);
    }
}
