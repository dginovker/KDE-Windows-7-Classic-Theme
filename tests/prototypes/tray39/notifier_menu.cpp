#include "notifier_menu.h"
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusVariant>
#include <QMenu>
#include <QPointer>
#include <QQuickWindow>

using namespace Qt::StringLiterals;
namespace {
struct Entry {
    int id = 0;
    QVariantMap fields;
    QList<Entry> children;
};

Entry decode(const QDBusArgument &arg, int remainingDepth)
{
    Entry node;
    arg.beginStructure();
    arg >> node.id >> node.fields;
    arg.beginArray();
    while (!arg.atEnd()) {
        QDBusVariant variant;
        arg >> variant;
        if (remainingDepth > 0 && variant.variant().metaType() == QMetaType::fromType<QDBusArgument>()) {
            const auto nested = variant.variant().value<QDBusArgument>();
            if (nested.currentSignature() == u"(ia{sv}av)") {
                node.children.append(decode(nested, remainingDepth - 1));
            }
        }
    }
    arg.endArray();
    arg.endStructure();
    return node;
}

QDBusMessage call(const QString &service, const QString &path, const QString &method)
{
    return QDBusMessage::createMethodCall(service, path, u"com.canonical.dbusmenu"_s, method);
}

void receiveLayout(QObject *context, const QString &service, const QString &path, int id,
                   std::function<void(Entry)> received)
{
    const auto bus = QDBusConnection::sessionBus();
    auto *pending = new QDBusPendingCallWatcher(bus.asyncCall(call(service, path, u"AboutToShow"_s) << id), context);
    QObject::connect(pending, &QDBusPendingCallWatcher::finished, context, [=] {
        pending->deleteLater();
        auto *layout = new QDBusPendingCallWatcher(bus.asyncCall(call(service, path, u"GetLayout"_s) << id << -1 << QStringList()), context);
        QObject::connect(layout, &QDBusPendingCallWatcher::finished, context, [=] {
            const auto reply = layout->reply();
            layout->deleteLater();
            if (reply.type() == QDBusMessage::ErrorMessage || reply.arguments().size() != 2) {
                qWarning().noquote() << "Classic tray: could not load notifier menu" << service << path << reply.errorMessage();
                return;
            }
            const auto arg = reply.arguments().at(1).value<QDBusArgument>();
            if (arg.currentSignature() == u"(ia{sv}av)") {
                received(decode(arg, 16));
            }
        });
    });
}

void populate(QMenu *menu, const Entry &entry, const QString &service, const QString &path)
{
    menu->clear();
    for (const auto &child : entry.children) {
        const auto &fields = child.fields;
        if (!fields.value(u"visible"_s, true).toBool()) {
            continue;
        }
        if (fields.value(u"type"_s).toString() == u"separator") {
            menu->addSeparator();
            continue;
        }
        auto label = fields.value(u"label"_s).toString();
        label.replace(u"&"_s, u"&&"_s);
        label.replace(u'_', u'&');
        auto icon = QIcon::fromTheme(fields.value(u"icon-name"_s).toString());
        const auto iconData = fields.value(u"icon-data"_s).toByteArray();
        if (icon.isNull() && !iconData.isEmpty()) {
            QPixmap pixels;
            if (iconData.size() <= 1024 * 1024 && pixels.loadFromData(iconData, "PNG")) {
                icon = QIcon(pixels);
            }
        }
        QAction *action;
        if (fields.value(u"children-display"_s).toString() == u"submenu") {
            auto *submenu = menu->addMenu(icon, label);
            populate(submenu, child, service, path);
            const auto id = child.id;
            QObject::connect(submenu, &QMenu::aboutToShow, submenu, [=] {
                receiveLayout(submenu, service, path, id, [=](const Entry &body) { populate(submenu, body, service, path); });
            });
            action = submenu->menuAction();
        } else {
            action = menu->addAction(icon, label);
            if (!fields.value(u"toggle-type"_s).toString().isEmpty()) {
                action->setCheckable(true);
                action->setChecked(fields.value(u"toggle-state"_s).toInt() == 1);
            }
            const auto id = child.id;
            QObject::connect(action, &QAction::triggered, menu, [=] {
                auto event = call(service, path, u"Event"_s);
                QDBusConnection::sessionBus().asyncCall(event << id << u"clicked"_s << QVariant::fromValue(QDBusVariant(0)) << quint32(0));
            });
        }
        action->setEnabled(fields.value(u"enabled"_s, true).toBool());
    }
}
}

void openNotifierMenu(QObject *lifetime, QQuickWindow *parent, const QString &address, const QString &path, int x, int y)
{
    const auto service = address.section(u'/', 0, 0);
    const QPointer<QQuickWindow> window = parent;
    receiveLayout(lifetime, service, path, 0, [=](const Entry &root) {
        if (!window) {
            return;
        }
        auto *menu = new QMenu;
        menu->setAttribute(Qt::WA_DeleteOnClose);
        QObject::connect(lifetime, &QObject::destroyed, menu, &QMenu::close);
        populate(menu, root, service, path);
        if (menu->isEmpty()) {
            qWarning().noquote() << "Classic tray: notifier menu has no visible entries" << address;
            delete menu;
            return;
        }
        menu->winId();
        menu->windowHandle()->setTransientParent(window);
        menu->popup(QPoint(x, y));
    });
}
