// SPDX-License-Identifier: GPL-3.0-or-later
#include <KGlobalAccel>
#include <PlasmaQuick/PlasmaShellWaylandIntegration>
#include <QWindow>
#include <QAction>
#include <PulseAudioQt/Context>
#include <PulseAudioQt/Server>
#include <PulseAudioQt/Sink>
#include <PulseAudioQt/StreamRestore>
#include <QDBusError>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QPointer>
#include <QQmlExtensionPlugin>
#include <qqml.h>

using namespace PulseAudioQt;
using namespace Qt::StringLiterals;

class Audio : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool writable READ writable NOTIFY changed)
    Q_PROPERTY(int percent READ percent NOTIFY changed)
    Q_PROPERTY(bool muted READ muted NOTIFY changed)
    Q_PROPERTY(QString device READ device NOTIFY changed)
    Q_PROPERTY(bool notificationStreamPresent READ notificationStreamPresent NOTIFY notificationStreamChanged)
    Q_PROPERTY(bool notificationStreamMuted READ notificationStreamMuted NOTIFY notificationStreamChanged)

public:
    explicit Audio(QObject *parent = nullptr) : QObject(parent), m_context(Context::instance())
    {
        connect(m_context->server(), &Server::defaultSinkChanged, this, &Audio::setSink);
        connect(m_context, &Context::streamRestoreAdded, this, &Audio::trackStream);
        connect(m_context, &Context::streamRestoreRemoved, this, [this](StreamRestore *stream) {
            if (m_stream == stream) {
                disconnect(m_stream, nullptr, this, nullptr);
                m_stream = nullptr;
                Q_EMIT notificationStreamChanged();
            }
        });
        setSink(m_context->server()->defaultSink());
        for (auto *stream : m_context->streamRestores()) {
            trackStream(stream);
        }
    }

    bool available() const { return m_sink && m_sink->name() != u"auto_null"; }
    bool writable() const { return available() && m_sink->isVolumeWritable(); }
    int percent() const { return available() ? qRound(100.0 * m_sink->volume() / normalVolume()) : 0; }
    bool muted() const { return available() && m_sink->isMuted(); }
    QString device() const { return available() ? m_sink->description() : QString(); }
    bool notificationStreamPresent() const { return m_stream; }
    bool notificationStreamMuted() const { return m_stream && m_stream->isMuted(); }

    Q_INVOKABLE void setPercent(int value)
    {
        if (writable() && value >= 0 && value <= 100) {
            m_sink->setVolume(qRound64(value * normalVolume() / 100.0));
        }
    }

    Q_INVOKABLE void toggleMute()
    {
        if (available()) {
            m_sink->setMuted(!m_sink->isMuted());
        }
    }

    Q_INVOKABLE void setNotificationStreamMuted(bool mute)
    {
        if (m_stream) {
            m_stream->setMuted(mute);
        }
    }

    Q_INVOKABLE void invokeAudioShortcut(const QString &name)
    {
        // Let Plasma's existing audio shortcuts service apply its configured steps,
        // per-device/global mute policy, volume limit and OSD.
        auto message = QDBusMessage::createMethodCall(u"org.kde.kglobalaccel"_s, u"/component/kmix"_s,
                                                      u"org.kde.kglobalaccel.Component"_s, u"invokeShortcut"_s);
        message << name;
        auto *call = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message), this);
        connect(call, &QDBusPendingCallWatcher::finished, this, [call, name] {
            if (call->isError()) {
                qWarning() << "Classic volume could not invoke" << name << call->error().message();
            }
            call->deleteLater();
        });
    }

Q_SIGNALS:
    void changed();
    void notificationStreamChanged();

private:
    void setSink(Sink *sink)
    {
        if (m_sink) {
            disconnect(m_sink, nullptr, this, nullptr);
        }
        m_sink = sink;
        if (m_sink) {
            connect(m_sink, &Sink::volumeChanged, this, &Audio::changed);
            connect(m_sink, &Sink::mutedChanged, this, &Audio::changed);
            connect(m_sink, &Sink::descriptionChanged, this, &Audio::changed);
            connect(m_sink, &Sink::isVolumeWritableChanged, this, &Audio::changed);
            connect(m_sink, &QObject::destroyed, this, &Audio::changed);
        }
        Q_EMIT changed();
    }

    void trackStream(StreamRestore *stream)
    {
        if (stream->name() != u"sink-input-by-media-role:event" || m_stream == stream) {
            return;
        }
        if (m_stream) {
            disconnect(m_stream, nullptr, this, nullptr);
        }
        m_stream = stream;
        connect(m_stream, &StreamRestore::mutedChanged, this, &Audio::notificationStreamChanged);
        connect(m_stream, &QObject::destroyed, this, &Audio::notificationStreamChanged);
        Q_EMIT notificationStreamChanged();
    }

    Context *const m_context;
    QPointer<Sink> m_sink;
    QPointer<StreamRestore> m_stream;
};

class NotificationShortcuts : public QObject
{
    Q_OBJECT
public:
    explicit NotificationShortcuts(QObject *parent = nullptr) : QObject(parent)
    {
        // Reuse the stock identifiers so the user's bindings survive profile switches.
        addShortcut(u"toggle do not disturb"_s, tr("Toggle do not disturb"), &NotificationShortcuts::toggleDoNotDisturb);
        addShortcut(u"clear history"_s, tr("Clear Notification History"), &NotificationShortcuts::clearHistory);
    }

    Q_INVOKABLE void setPopupFocus(QWindow *window, bool focus)
    {
        // The notification Wayland role ignores keyboard focus unless the shell surface opts in.
        PlasmaShellWaylandIntegration::get(window)->setTakesFocus(focus);
        if (focus) {
            window->requestActivate();
        }
    }

    Q_INVOKABLE void showOsd(const QString &icon, const QString &text)
    {
        auto message = QDBusMessage::createMethodCall(u"org.kde.plasmashell"_s, u"/org/kde/osdService"_s,
                                                      u"org.kde.osdService"_s, u"showText"_s);
        message << icon << text;
        QDBusConnection::sessionBus().asyncCall(message);
    }

Q_SIGNALS:
    void toggleDoNotDisturb();
    void clearHistory();

private:
    void addShortcut(const QString &name, const QString &text, void (NotificationShortcuts::*signal)())
    {
        auto *action = new QAction(text, this);
        action->setObjectName(name);
        action->setProperty("componentName", u"plasmashell"_s);
        connect(action, &QAction::triggered, this, signal);
        if (!KGlobalAccel::self()->setGlobalShortcut(action, QKeySequence())) {
            qWarning() << "Classic notifications could not restore Plasma shortcut" << name;
        }
    }
};

class PopupPlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override
    {
        qmlRegisterType<Audio>(uri, 1, 0, "Audio");
        qmlRegisterType<NotificationShortcuts>(uri, 1, 0, "NotificationShortcuts");
    }
};

#include "Audio.moc"
