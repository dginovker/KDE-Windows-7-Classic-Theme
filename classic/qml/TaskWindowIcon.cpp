#include <QCoreApplication>
#include <QDataStream>
#include <QIcon>
#include <QSocketNotifier>
#include <QTimer>
#include <QWaylandClientExtension>
#include <QtQml/qqml.h>

#include <cerrno>
#include <fcntl.h>
#include <unistd.h>

#include "qwayland-plasma-window-management.h"

namespace
{
class WindowManagement : public QWaylandClientExtensionTemplate<WindowManagement>, public QtWayland::org_kde_plasma_window_management
{
public:
    WindowManagement() : QWaylandClientExtensionTemplate(ORG_KDE_PLASMA_WINDOW_MANAGEMENT_GET_WINDOW_BY_UUID_SINCE_VERSION, QCoreApplication::instance())
    {
        initialize();
    }
    ~WindowManagement() override
    {
        if (isActive())
            wl_proxy_destroy(reinterpret_cast<wl_proxy *>(object()));
    }
};
}

class TaskWindowIcon : public QObject, private QtWayland::org_kde_plasma_window
{
    Q_OBJECT
    Q_PROPERTY(QString uuid READ uuid WRITE setUuid NOTIFY uuidChanged)
    Q_PROPERTY(QIcon icon READ icon NOTIFY iconChanged)
    Q_PROPERTY(bool ready READ ready NOTIFY iconChanged)

public:
    TaskWindowIcon()
    {
        m_reader.setEnabled(false);
        m_timeout.setSingleShot(true);
        connect(&m_reader, &QSocketNotifier::activated, this, &TaskWindowIcon::readIcon);
        connect(&m_timeout, &QTimer::timeout, this, [this] { fail("timed out reading the window icon"); });
    }
    ~TaskWindowIcon() override { release(); }

    static void registerType(const char *uri) { qmlRegisterType<TaskWindowIcon>(uri, 1, 0, "TaskWindowIcon"); }
    QString uuid() const { return m_uuid; }
    QIcon icon() const { return m_icon; }
    bool ready() const { return !m_icon.isNull(); }

    void setUuid(const QString &uuid)
    {
        if (m_uuid == uuid)
            return;
        release();
        m_uuid = uuid;
        Q_EMIT uuidChanged();
        if (uuid.isEmpty())
            return;
        static auto *management = new WindowManagement;
        if (!management->isActive() || management->QWaylandClientExtension::version() < ORG_KDE_PLASMA_WINDOW_MANAGEMENT_GET_WINDOW_BY_UUID_SINCE_VERSION) {
            fail("KWin's plasma-window-management UUID lookup is unavailable");
            return;
        }
        init(management->get_window_by_uuid(uuid));
    }

Q_SIGNALS:
    void uuidChanged();
    void iconChanged();

private:
    void org_kde_plasma_window_initial_state() override
    {
        if (!m_reader.isEnabled())
            requestIcon();
    }
    void org_kde_plasma_window_unmapped() override { release(); }
    void org_kde_plasma_window_icon_changed() override { requestIcon(); }

    void requestIcon()
    {
        if (m_reader.isEnabled()) {
            m_pending = true;
            return;
        }
        int fds[2];
        if (pipe2(fds, O_CLOEXEC | O_NONBLOCK) != 0) {
            fail("cannot open the window-icon pipe");
            return;
        }
        // KWin streams the QIcon, including its size variants. Don't block the panel while it writes.
        get_icon(fds[1]);
        ::close(fds[1]);
        m_reader.setSocket(fds[0]);
        m_reader.setEnabled(true);
        m_timeout.start(2000);
    }

    void readIcon()
    {
        char buffer[16384];
        const auto count = read(m_reader.socket(), buffer, sizeof(buffer));
        if (count > 0) {
            m_bytes.append(buffer, count);
            if (m_bytes.size() > 4 * 1024 * 1024)
                fail("window icon exceeds 4 MiB");
        } else if (count == 0) {
            QDataStream stream(m_bytes);
            QIcon icon;
            stream >> icon;
            stopReading();
            if (m_pending) {
                m_pending = false;
                requestIcon();
            } else if (stream.status() != QDataStream::Ok || icon.isNull()) {
                fail("KWin sent an empty or invalid window icon");
            } else {
                m_icon = icon;
                Q_EMIT iconChanged();
            }
        } else if (errno != EAGAIN && errno != EINTR) {
            fail("cannot read the window-icon pipe");
        }
    }

    void stopReading()
    {
        if (m_reader.isEnabled()) {
            m_reader.setEnabled(false);
            ::close(m_reader.socket());
            m_reader.setSocket(-1);
        }
        m_timeout.stop();
        m_bytes.clear();
    }

    void clearIcon()
    {
        if (!m_icon.isNull()) {
            m_icon = {};
            Q_EMIT iconChanged();
        }
    }

    void fail(const char *error)
    {
        qWarning().noquote() << "win7-classic taskbar:" << error << "for Explorer window" << m_uuid;
        stopReading();
        m_pending = false;
        clearIcon();
    }

    void release()
    {
        stopReading();
        m_pending = false;
        if (isInitialized())
            destroy();
        clearIcon();
    }

    QString m_uuid;
    QIcon m_icon;
    QSocketNotifier m_reader{QSocketNotifier::Read};
    QTimer m_timeout;
    QByteArray m_bytes;
    bool m_pending = false;
};

void registerTaskWindowIcon(const char *uri) { TaskWindowIcon::registerType(uri); }

#include "TaskWindowIcon.moc"
