#include "background_apps.h"

#include <KIO/ApplicationLauncherJob>
#include <KIO/CommandLauncherJob>
#include <KService>
#include <KWaylandExtras>
#include <QDBusConnection>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QIcon>
#include <QMenu>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>

using namespace Qt::StringLiterals;

namespace {
const auto Monitor = u"org.freedesktop.background.Monitor"_s;
const auto Path = u"/org/freedesktop/background/monitor"_s;
const auto Properties = u"org.freedesktop.DBus.Properties"_s;
const auto Property = u"BackgroundApps"_s;

void reportError(KJob *job, QObject *context)
{
    QObject::connect(job, &KJob::result, context, [](KJob *result) {
        if (result->error()) {
            qWarning().noquote() << "Classic tray: background app action failed:" << result->errorString();
        }
    });
}
}

BackgroundApps::BackgroundApps(QObject *parent)
    : QObject(parent)
{
    auto bus = QDBusConnection::sessionBus();
    if (!bus.connect(Monitor, Path, Properties, u"PropertiesChanged"_s, this,
                     SLOT(propertiesChanged(QString,QVariantMap,QStringList)))) {
        qWarning("Classic tray: cannot subscribe to the portal background monitor");
    }
    auto *watcher = new QDBusServiceWatcher(Monitor, bus, QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(watcher, &QDBusServiceWatcher::serviceOwnerChanged, this, [this](const auto &, const auto &, const auto &owner) {
        ++m_revision;
        if (owner.isEmpty()) {
            read({});
        } else {
            refresh();
        }
    });
    refresh();
}

void BackgroundApps::refresh()
{
    const auto revision = ++m_revision;
    auto message = QDBusMessage::createMethodCall(Monitor, Path, Properties, u"Get"_s);
    auto *call = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message << Monitor << Property), this);
    connect(call, &QDBusPendingCallWatcher::finished, this, [this, call, revision] {
        QDBusPendingReply<QDBusVariant> reply = *call;
        call->deleteLater();
        if (revision != m_revision) {
            return;
        }
        if (reply.isValid()) {
            read(reply.value().variant());
        } else if (reply.error().type() != QDBusError::ServiceUnknown) {
            qWarning().noquote() << "Classic tray: cannot read portal background apps:" << reply.error().message();
        }
    });
}

void BackgroundApps::propertiesChanged(const QString &interface, const QVariantMap &changed, const QStringList &invalidated)
{
    if (interface != Monitor) {
        return;
    }
    if (changed.contains(Property)) {
        ++m_revision;
        read(changed.value(Property));
    } else if (invalidated.contains(Property)) {
        refresh();
    }
}

void BackgroundApps::read(const QVariant &value)
{
    QVariantList items;
    QHash<QString, QStringList> instances;
    QHash<QString, QString> messages;
    QStringList ids;
    static const QRegularExpression instanceId(u"^[0-9]+$"_s);
    for (const auto &entry : qdbus_cast<QList<QVariantMap>>(value)) {
        const auto id = entry.value(u"app_id"_s).toString();
        const auto instance = entry.value(u"instance"_s).toString();
        if (id.isEmpty() || !instanceId.match(instance).hasMatch()) {
            qWarning() << "Classic tray: malformed portal background entry" << id << instance;
            continue;
        }
        auto &running = instances[id];
        if (running.isEmpty()) {
            ids.append(id);
            messages.insert(id, entry.value(u"message"_s).toString());
        }
        if (!running.contains(instance)) {
            running.append(instance);
        }
    }
    for (const auto &id : ids) {
        const auto service = KService::serviceByDesktopName(id);
        items.append(QVariantMap{{u"id"_s, id}, {u"name"_s, service ? service->name() : id},
                                 {u"icon"_s, service ? QIcon::fromTheme(service->icon()) : QIcon()},
                                 {u"message"_s, messages.value(id)}, {u"instances"_s, instances.value(id)}});
    }
    m_instances = std::move(instances);
    m_items = std::move(items);
    Q_EMIT itemsChanged();
}

void BackgroundApps::open(const QString &id, QQuickItem *anchor)
{
    if (!m_instances.contains(id) || !anchor || !anchor->window()) {
        return;
    }
    const auto service = KService::serviceByDesktopName(id);
    if (!service) {
        qWarning().noquote() << "Classic tray: no desktop entry for background app" << id;
        return;
    }
    KWaylandExtras::xdgActivationToken(anchor->window(), id).then(this, [this, service](const QString &token) {
        auto *job = new KIO::ApplicationLauncherJob(service);
        job->setStartupId(token.toUtf8());
        reportError(job, this);
        job->start();
    });
}

void BackgroundApps::stop(const QString &id)
{
    // The app ID alone could also name a foreground or non-sandboxed process.
    for (const auto &instance : m_instances.value(id)) {
        auto *job = new KIO::CommandLauncherJob(u"flatpak"_s, {u"kill"_s, instance});
        reportError(job, this);
        job->start();
    }
}

void BackgroundApps::menu(const QString &id, QQuickItem *anchor)
{
    if (!m_instances.contains(id) || !anchor || !anchor->window()) {
        return;
    }
    auto *menu = new QMenu;
    menu->setAttribute(Qt::WA_DeleteOnClose);
    connect(this, &QObject::destroyed, menu, &QMenu::close);
    menu->addAction(tr("Stop"), this, [this, id] { stop(id); });
    menu->winId();
    menu->windowHandle()->setTransientParent(anchor->window());
    menu->popup(anchor->mapToGlobal(QPointF(0, 0)).toPoint());
}
