#include "notifier_menu.h"
#include "status_notifiers.h"
#include <KConfigGroup>
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

class ClassicTray final : public Plasma::Containment
{
    Q_OBJECT
    Q_PROPERTY(QString speakerArt READ speakerArt NOTIFY speakerArtChanged)
    Q_PROPERTY(StatusNotifiers *statusNotifiers READ statusNotifiers NOTIFY statusNotifiersChanged)
public:
    ClassicTray(QObject *parent, const KPluginMetaData &meta, const QVariantList &args)
        : Plasma::Containment(parent, meta, args)
    {
    }

    void init() override
    {
        Containment::init();
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
        if (menu->isEmpty()) {
            delete menu;
            return;
        }
        menu->winId();
        menu->windowHandle()->setTransientParent(anchor->window());
        menu->popup(anchor->mapToGlobal(QPointF(0, 0)).toPoint());
    }

    StatusNotifiers *statusNotifiers() const { return m_notifiers; }

    QString speakerArt() const
    {
        if (!m_sink || m_sink->name() == QLatin1String("auto_null")) {
            return {};
        }
        if (m_sink->isMuted()) {
            return QStringLiteral("speaker-muted.png");
        }
        if (m_sink->volume() == 0) {
            return {};
        }
        return QStringLiteral("speaker-unmuted.png");
    }

Q_SIGNALS:
    void speakerArtChanged();
    void statusNotifiersChanged();

protected:
    void restoreContents(KConfigGroup &group) override
    {
        Containment::restoreContents(group);
        auto general = group.group(QStringLiteral("Configuration")).group(QStringLiteral("General"));
        const auto known = general.readEntry("knownItems", QStringList());
        auto enabled = general.readEntry("extraItems", QStringList());
        for (const auto &meta : Plasma::PluginLoader::self()->listAppletMetaData(QString())) {
            if (meta.isEnabledByDefault() && !meta.value(u"X-Plasma-NotificationAreaCategory").isEmpty()
                && !known.contains(meta.pluginId()) && !enabled.contains(meta.pluginId())) {
                enabled.append(meta.pluginId());
            }
        }
        for (const auto &id : std::as_const(enabled)) {
            const auto active = applets();
            if (std::ranges::any_of(active, [&id](auto *a) { return a->pluginName() == id; })) {
                continue;
            }
            if (immutability() != Plasma::Types::Mutable) {
                qCritical().noquote() << "Classic tray: cannot load" << id << "in immutable layout";
            } else if (!createApplet(id)) {
                qCritical().noquote() << "Classic tray: could not load configured applet" << id;
            }
        }
    }

private:
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

    StatusNotifiers *m_notifiers = nullptr;
    PulseAudioQt::Server *m_server = nullptr;
    QPointer<PulseAudioQt::Sink> m_sink;
};

K_PLUGIN_CLASS_WITH_JSON(ClassicTray, "metadata.json")
#include "tray.moc"
