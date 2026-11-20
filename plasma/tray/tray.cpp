#include "background_apps.h"
#include "notifier_menu.h"
#include "status_notifiers.h"
#include <KConfigGroup>
#include <KConfigLoader>
#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QEvent>
#include <QFile>
#include <QStandardPaths>
#include <QRegularExpression>
#include <QTimer>
#include <KPluginFactory>
#include <Plasma/Containment>
#include <Plasma/PluginLoader>
#include <PulseAudioQt/Context>
#include <PulseAudioQt/Server>
#include <PulseAudioQt/Sink>
#include <QPointer>
#include <QMenu>
#include <QQuickWindow>
#include <algorithm>
#include <utility>

using namespace Qt::StringLiterals;

// Keep the stock configuration and shortcut owner IDs; only the applet implementation changes.
static const QMap<QString, QString> popupReplacements{
    {u"org.kde.plasma.notifications"_s, u"org.win7classic.notifications"_s},
    {u"org.kde.plasma.volume"_s, u"org.win7classic.volume"_s},
};
static const auto notificationId = u"org.kde.plasma.notifications"_s;

class ClassicTray final : public Plasma::Containment
{
    Q_OBJECT
    Q_PROPERTY(QVariantList appletChoices READ appletChoices NOTIFY appletChoicesChanged)
    Q_PROPERTY(BackgroundApps *backgroundApps READ backgroundApps CONSTANT)
    Q_PROPERTY(QString speakerArt READ speakerArt NOTIFY speakerArtChanged)
    Q_PROPERTY(StatusNotifiers *statusNotifiers READ statusNotifiers NOTIFY statusNotifiersChanged)
public:
    ClassicTray(QObject *parent, const KPluginMetaData &meta, const QVariantList &args)
        : Plasma::Containment(parent, meta, args)
    {
        setHasConfigurationInterface(true);
    }

    void init() override
    {
        Containment::init();
        connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this, [this] {
            // Dispose the open config window before Plasma tears down its QML engine and delegate models.
            if (const auto window = m_itemsWindow) {
                window->close();
                if (window) {
                    QCoreApplication::sendPostedEvents(window, QEvent::DeferredDelete);
                }
            }
        });
        connect(this, &Containment::appletAdded, this, [this](Plasma::Applet *applet) {
            disconnect(applet, &Applet::activated, this, &Applet::activated);
        });
        m_notifiers = new StatusNotifiers(this);
        connect(m_notifiers, &StatusNotifiers::menuRequested, this, [this](const QString &address, const QString &path, QQuickItem *anchor, int x, int y) {
            openNotifierMenu(this, anchor->window(), address, path, x, y);
        });
        Q_EMIT statusNotifiersChanged();
        m_server = PulseAudioQt::Context::instance()->server();
        connect(m_server, &PulseAudioQt::Server::defaultSinkChanged, this, &ClassicTray::followSink);
        followSink();
    }

    QVariantList appletChoices() const
    {
        QVariantList result;
        for (const auto &meta : m_catalog) {
            result.append(QVariantMap{{QStringLiteral("id"), meta.pluginId()},
                                      {QStringLiteral("name"), meta.name()},
                                      {QStringLiteral("mandatory"), meta.pluginId() == notificationId}});
        }
        return result;
    }

    Q_INVOKABLE void trackItemsWindow(QWindow *window)
    {
        m_itemsWindow = window;
    }

    Q_INVOKABLE QString settingsId(Plasma::Applet *applet) const
    {
        const auto id = applet->pluginName();
        return popupReplacements.key(id, id);
    }

    Q_INVOKABLE QString category(Plasma::Applet *applet) const
    {
        return m_catalog.value(settingsId(applet)).value(u"X-Plasma-NotificationAreaCategory");
    }

    Q_INVOKABLE void configureTray()
    {
        if (auto *action = internalAction(QStringLiteral("configure"))) {
            action->trigger();
        }
    }

    void configChanged() override
    {
        Containment::configChanged();
        if (m_restored) {
            scheduleSync();
        }
    }

    Q_INVOKABLE void showAppletMenu(Plasma::Applet *applet, QQuickItem *anchor)
    {
        if (!applet || applet->containment() != this || !anchor || !anchor->window()) {
            qCritical("Classic tray: cannot open real applet context menu without its anchor");
            return;
        }
        Q_EMIT applet->contextualActionsAboutToShow();
        auto *menu = new QMenu;
        menu->setAttribute(Qt::WA_DeleteOnClose);
        connect(this, &QObject::destroyed, menu, &QMenu::close);
        for (auto *action : applet->contextualActions()) {
            if (action) {
                menu->addAction(action);
            }
        }
        if (auto *configure = applet->internalAction(QStringLiteral("configure"))) {
            menu->addAction(configure);
        }
        // The overflow button is absent if every item is visible.
        if (auto *configure = internalAction(QStringLiteral("configure")); configure && configure->isEnabled()) {
            if (!menu->isEmpty()) {
                menu->addSeparator();
            }
            auto *configureArea = menu->addAction(tr("Configure Notification Area…"));
            connect(configureArea, &QAction::triggered, configure, &QAction::trigger);
        }
        if (menu->isEmpty()) {
            delete menu;
            return;
        }
        menu->winId();
        menu->windowHandle()->setTransientParent(anchor->window());
        menu->popup(anchor->mapToGlobal(QPointF(0, 0)).toPoint());
    }

    BackgroundApps *backgroundApps() { return &m_backgroundApps; }
    StatusNotifiers *statusNotifiers() const { return m_notifiers; }

    QString speakerArt() const
    {
        if (!m_sink || m_sink->name() == QLatin1String("auto_null")) {
            return {};
        }
        if (m_sink->isMuted()) {
            return QStringLiteral("speaker-muted.png");
        }
        return m_sink->volume() == 0 ? QStringLiteral("speaker-zero.png") : QStringLiteral("speaker-unmuted.png");
    }

Q_SIGNALS:
    void appletChoicesChanged();
    void speakerArtChanged();
    void statusNotifiersChanged();

protected:
    void restoreContents(KConfigGroup &group) override
    {
        const auto receipt = QStandardPaths::writableLocation(QStandardPaths::GenericStateLocation)
            + QStringLiteral("/win7-classic/current-tray-accelerators.json");
        if (QFile::exists(receipt)) {
            m_shortcutIds = receipt + QStringLiteral(".ids/");
        }
        const auto shortcut = group.group(QStringLiteral("Shortcuts")).readEntry("global", QString());
        // The native settings page can assign the first shortcut after startup.
        if (recordShortcutOwner(id()) && !shortcut.isEmpty()) {
            setGlobalShortcut(QKeySequence(shortcut));
        }
        m_groups = group.group(QStringLiteral("Applets"));
        refreshCatalog();
        syncApplets();
        if (applets().isEmpty()) {
            // The base marks an empty containment ready. Do not let it recreate a disabled saved widget.
            KConfigGroup empty;
            Containment::restoreContents(empty);
        }
        m_restored = true;
        for (auto bus : {QDBusConnection::sessionBus(), QDBusConnection::systemBus()}) {
            bus.connect(QStringLiteral("org.freedesktop.DBus"), QStringLiteral("/org/freedesktop/DBus"),
                        QStringLiteral("org.freedesktop.DBus"), QStringLiteral("NameOwnerChanged"),
                        this, SLOT(serviceChanged(QString,QString,QString)));
        }
        auto session = QDBusConnection::sessionBus();
        for (const auto &signal : {"packageInstalled", "packageUpdated", "packageUninstalled"}) {
            session.connect(QString(), QStringLiteral("/KPackage/Plasma/Applet"), QStringLiteral("org.kde.plasma.kpackage"),
                            QString::fromLatin1(signal), this, SLOT(packageChanged(QString)));
        }
        connect(this, &Applet::immutabilityChanged, this, &ClassicTray::scheduleSync);
    }

private Q_SLOTS:
    void serviceChanged(const QString &name, const QString &, const QString &)
    {
        if (std::ranges::any_of(m_services, [&name](const auto &rx) { return rx.match(name).hasMatch(); })) {
            scheduleSync();
        }
    }

    void packageChanged(const QString &)
    {
        refreshCatalog();
        scheduleSync();
    }

private:
    bool recordShortcutOwner(uint appletId) const
    {
        if (m_shortcutIds.isEmpty()) {
            return true;
        }
        // Plasma can discard an applet's entire config while KGlobalAccel retains its dormant action.
        QFile entry(m_shortcutIds + QString::number(appletId));
        if (entry.open(QIODevice::WriteOnly | QIODevice::NewOnly) || entry.exists()) {
            return true;
        }
        qCritical().noquote() << "Classic tray: cannot record shortcut ownership for applet" << appletId << entry.errorString();
        return false;
    }

    void refreshCatalog()
    {
        m_catalog.clear();
        m_services.clear();
        for (const auto &meta : Plasma::PluginLoader::self()->listAppletMetaData(QString())) {
            if (meta.value(u"X-Plasma-NotificationAreaCategory").isEmpty()) {
                continue;
            }
            m_catalog.insert(meta.pluginId(), meta);
            const auto service = meta.value(u"X-Plasma-DBusActivationService");
            if (!service.isEmpty()) {
                m_services.insert(meta.pluginId(), QRegularExpression::fromWildcard(service));
            }
        }
        Q_EMIT appletChoicesChanged();
    }

    void scheduleSync()
    {
        if (m_syncing) {
            return;
        }
        m_syncing = true;
        QTimer::singleShot(0, this, [this] {
            syncApplets();
            m_syncing = false;
        });
    }

    void syncApplets()
    {
        auto *settings = configScheme();
        settings->load();
        auto known = settings->property("knownItems").toStringList();
        auto enabled = settings->property("extraItems").toStringList();
        const auto originalKnown = known;
        for (const auto &meta : m_catalog) {
            const auto id = meta.pluginId();
            if (meta.isEnabledByDefault() && !known.contains(id)) {
                known.append(id);
                if (!enabled.contains(id)) {
                    enabled.append(id);
                }
            }
        }
        if (known != originalKnown && immutability() == Plasma::Types::Mutable) {
            settings->findItemByName(QStringLiteral("knownItems"))->setProperty(known);
            settings->findItemByName(QStringLiteral("extraItems"))->setProperty(enabled);
            settings->save();
            settings->read();
        }
        QStringList services;
        if (!m_services.empty()) {
            for (auto bus : {QDBusConnection::sessionBus(), QDBusConnection::systemBus()}) {
                const auto names = bus.interface()->registeredServiceNames();
                if (names.isValid()) {
                    services += names.value();
                } else {
                    qCritical().noquote() << "Classic tray: cannot enumerate services:" << names.error().message();
                }
            }
        }
        // The notification service must remain alive even if its icon was disabled in the stock tray.
        enabled.append(notificationId);
        QSet<QString> wanted;
        for (const auto &id : enabled) {
            if (!m_catalog.contains(id)) {
                qWarning().noquote() << "Classic tray: enabled plugin unavailable:" << id;
                continue;
            }
            if (!m_services.contains(id) || std::ranges::any_of(services, [rx = m_services.value(id)](const QString &name) {
                    return rx.match(name).hasMatch();
                })) {
                wanted.insert(id);
            }
        }
        for (auto *applet : applets()) {
            if (!wanted.remove(settingsId(applet))) {
                // Do not destroy() the settings: a service may come back under the same applet ID.
                applet->deleteLater();
            }
        }
        for (const auto &id : wanted) {
            const auto implementation = popupReplacements.value(id, id);
            if (immutability() != Plasma::Types::Mutable) {
                qCritical().noquote() << "Classic tray: cannot load" << id << "in immutable layout";
                continue;
            }
            uint savedId = 0;
            for (const auto &name : m_groups.groupList()) {
                const auto saved = m_groups.group(name).readEntry("plugin", QString());
                if (saved == id || saved == implementation) {
                    savedId = name.toUInt();
                    break;
                }
            }
            auto applet = Plasma::PluginLoader::self()->loadApplet(implementation, savedId, {});
            if (!applet || !applet->pluginMetaData().isValid()) {
                qCritical().noquote() << "Classic tray: could not load configured applet" << id;
                continue;
            }
            if (recordShortcutOwner(applet->id())) {
                addApplet(std::move(applet));
            }
        }
    }

    void followSink()
    {
        if (m_sink) {
            disconnect(m_sink, nullptr, this, nullptr);
        }
        m_sink = m_server->defaultSink();
        if (m_sink) {
            connect(m_sink, &PulseAudioQt::Sink::volumeChanged, this, &ClassicTray::speakerArtChanged);
            connect(m_sink, &PulseAudioQt::Sink::mutedChanged, this, &ClassicTray::speakerArtChanged);
            connect(m_sink, &QObject::destroyed, this, &ClassicTray::speakerArtChanged);
        }
        Q_EMIT speakerArtChanged();
    }

    BackgroundApps m_backgroundApps{this};
    StatusNotifiers *m_notifiers = nullptr;
    PulseAudioQt::Server *m_server = nullptr;
    QPointer<PulseAudioQt::Sink> m_sink;
    QMap<QString, KPluginMetaData> m_catalog;
    QMap<QString, QRegularExpression> m_services;
    KConfigGroup m_groups;
    QString m_shortcutIds;
    QPointer<QWindow> m_itemsWindow;
    bool m_restored = false;
    bool m_syncing = false;
};

K_PLUGIN_CLASS_WITH_JSON(ClassicTray, "metadata.json")
#include "tray.moc"
