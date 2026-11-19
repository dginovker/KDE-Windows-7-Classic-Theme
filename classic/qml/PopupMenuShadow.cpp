#include "MenuShadowTiles.h"

#include <QGuiApplication>
#include <QPlatformSurfaceEvent>
#include <QPointer>
#include <QWindow>
#include <qqml.h>

// Opt-in for a project-owned window with no theme shadow; never scans other QML or QWidget windows.
class PopupMenuShadow : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QWindow *target READ target WRITE setTarget NOTIFY targetChanged REQUIRED)
public:
    QWindow *target() const { return m_target; }
    void setTarget(QWindow *window)
    {
        if (window == m_target) return;
        if (m_target) m_target->removeEventFilter(this);
        m_shadow.reset();
        m_target = window;
        if (m_target && QGuiApplication::platformName().startsWith(QLatin1String("wayland"))) {
            m_target->installEventFilter(this);
            if (m_target->isVisible()) attach();
        }
        Q_EMIT targetChanged();
    }

Q_SIGNALS:
    void targetChanged();

private:
    bool eventFilter(QObject *, QEvent *event) override
    {
        if (event->type() == QEvent::Show) attach();
        if (event->type() == QEvent::Hide ||
            (event->type() == QEvent::PlatformSurface &&
             static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed)) {
            m_shadow.reset();
        }
        return false;
    }

    void attach()
    {
        // Show already has a platform window; do not force one or alter its role/mask/geometry.
        if (m_shadow || !m_target->handle()) return;
        auto shadow = Classic::menuShadow(m_target, m_tiles);
        if (!shadow->create()) {
            qWarning("Win7Classic: KWindowShadow could not attach the Classic QML popup shadow");
            return;
        }
        m_shadow = std::move(shadow);
    }

    QPointer<QWindow> m_target;
    Classic::MenuShadowTiles m_tiles{};
    std::unique_ptr<KWindowShadow> m_shadow;
};

void registerPopupMenuShadow(const char *uri)
{
    qmlRegisterType<PopupMenuShadow>(uri, 1, 0, "PopupMenuShadow");
}

#include "PopupMenuShadow.moc"
