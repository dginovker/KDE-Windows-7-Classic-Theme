// SPDX-License-Identifier: GPL-3.0-or-later
#include <PlasmaQuick/PlasmaShellWaylandIntegration>
#include <QWindow>
#include <PulseAudioQt/Context>
#include <PulseAudioQt/Server>
#include <PulseAudioQt/Sink>
#include <QDBusError>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QLibrary>
#include <QLibraryInfo>
#include <QPointer>
#include <QQmlExtensionPlugin>
#include <QQmlEngine>
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

public:
    explicit Audio(QObject *parent = nullptr) : QObject(parent), m_context(Context::instance())
    {
        connect(m_context->server(), &Server::defaultSinkChanged, this, &Audio::setSink);
        setSink(m_context->server()->defaultSink());
    }

    bool available() const { return m_sink && m_sink->name() != u"auto_null"; }
    bool writable() const { return available() && m_sink->isVolumeWritable(); }
    int percent() const { return available() ? qRound(100.0 * m_sink->volume() / normalVolume()) : 0; }
    bool muted() const { return available() && m_sink->isMuted(); }
    QString device() const { return available() ? m_sink->description() : QString(); }

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

    Context *const m_context;
    QPointer<Sink> m_sink;
};

class BalloonFocus : public QObject
{
    Q_OBJECT
public:
    Q_INVOKABLE void setPopupFocus(QWindow *window, bool focus)
    {
        // The notification Wayland role ignores keyboard focus unless the shell surface opts in.
        PlasmaShellWaylandIntegration::get(window)->setTakesFocus(focus);
        if (focus) {
            window->requestActivate();
        }
    }

};

class StockNotificationView : public QObject
{
    Q_OBJECT
public:
    using QObject::QObject;

    Q_INVOKABLE void loadModule()
    {
        // Plasma ships its history UI in the compiled applet, not on the normal QML import path.
        static QLibrary stock(QLibraryInfo::path(QLibraryInfo::PluginsPath)
                              + u"/plasma/applets/org.kde.plasma.notifications.so"_s);
        stock.setLoadHints(QLibrary::PreventUnloadHint);
        if (!stock.isLoaded() && !stock.load()) {
            qmlEngine(this)->throwError(stock.errorString());
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
        qmlRegisterType<BalloonFocus>(uri, 1, 0, "BalloonFocus");
        qmlRegisterType<StockNotificationView>(uri, 1, 0, "StockNotificationView");
    }
};

#include "Audio.moc"
