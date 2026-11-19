#include "notifier_menu.h"
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusVariant>
#include <QMenu>
#include <QPointer>
#include <QQuickWindow>
#include <QTimer>

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
                   std::function<void(Entry)> received, bool aboutToShow = true)
{
    const auto bus = QDBusConnection::sessionBus();
    const auto get = [=] {
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
            } else {
                qWarning().noquote() << "Classic tray: invalid notifier menu layout" << service << path;
            }
        });
    };
    if (!aboutToShow) {
        get();
        return;
    }
    auto *pending = new QDBusPendingCallWatcher(bus.asyncCall(call(service, path, u"AboutToShow"_s) << id), context);
    QObject::connect(pending, &QDBusPendingCallWatcher::finished, context, [=] {
        pending->deleteLater();
        get();
    });
}

void updateAction(QAction *action, const QVariantMap &fields)
{
    auto label = fields.value(u"label"_s).toString();
    label.replace(u"&"_s, u"&&"_s);
    label.replace(u'_', u'&');
    action->setText(label);
    auto icon = QIcon::fromTheme(fields.value(u"icon-name"_s).toString());
    const auto iconData = fields.value(u"icon-data"_s).toByteArray();
    if (icon.isNull() && !iconData.isEmpty()) {
        QPixmap pixels;
        if (iconData.size() <= 1024 * 1024 && pixels.loadFromData(iconData, "PNG")) {
            icon = QIcon(pixels);
        }
    }
    action->setIcon(icon);
    action->setEnabled(fields.value(u"enabled"_s, true).toBool());
    action->setVisible(fields.value(u"visible"_s, true).toBool());
    action->setCheckable(!fields.value(u"toggle-type"_s).toString().isEmpty());
    action->setChecked(fields.value(u"toggle-state"_s).toInt() == 1);
    action->setProperty("notifierFields", fields);
}

void populate(QMenu *menu, const Entry &entry, const QString &service, const QString &path)
{
    menu->clear();
    for (auto *submenu : menu->findChildren<QMenu *>(Qt::FindDirectChildrenOnly)) {
        submenu->deleteLater();
    }
    for (const auto &child : entry.children) {
        const auto &fields = child.fields;
        QAction *action;
        if (fields.value(u"type"_s).toString() == u"separator") {
            action = menu->addSeparator();
        } else if (fields.value(u"children-display"_s).toString() == u"submenu") {
            auto *submenu = menu->addMenu(QString());
            populate(submenu, child, service, path);
            const auto id = child.id;
            QObject::connect(submenu, &QMenu::aboutToShow, submenu, [=] {
                receiveLayout(submenu, service, path, id, [=](const Entry &body) { populate(submenu, body, service, path); });
            });
            action = submenu->menuAction();
        } else {
            action = menu->addAction(QString());
            const auto id = child.id;
            QObject::connect(action, &QAction::triggered, menu, [=] {
                auto event = call(service, path, u"Event"_s);
                QDBusConnection::sessionBus().asyncCall(event << id << u"clicked"_s << QVariant::fromValue(QDBusVariant(0)) << quint32(0));
            });
        }
        action->setProperty("notifierId", child.id);
        updateAction(action, fields);
    }
}

class MenuUpdates final : public QObject
{
    Q_OBJECT
public:
    MenuUpdates(QMenu *menu, const QString &service, const QString &path)
        : QObject(menu), m_menu(menu), m_service(service), m_path(path)
    {
        auto bus = QDBusConnection::sessionBus();
        bus.connect(service, path, u"com.canonical.dbusmenu"_s, u"LayoutUpdated"_s,
                    this, SLOT(layoutUpdated()));
        bus.connect(service, path, u"com.canonical.dbusmenu"_s, u"ItemsPropertiesUpdated"_s,
                    this, SLOT(propertiesUpdated(QDBusMessage)));
    }

private Q_SLOTS:
    void layoutUpdated()
    {
        const auto generation = ++m_generation;
        receiveLayout(this, m_service, m_path, 0, [this, generation](const Entry &entry) {
            if (generation == m_generation) {
                populate(m_menu, entry, m_service, m_path);
            }
        }, false);
    }

    void propertiesUpdated(const QDBusMessage &signal)
    {
        if (signal.signature() != u"a(ia{sv})a(ias)") {
            qWarning().noquote() << "Classic tray: invalid notifier menu updates" << m_service << m_path;
            return;
        }
        auto args = signal.arguments();
        const auto change = args[0].value<QDBusArgument>();
        change.beginArray();
        while (!change.atEnd()) {
            int id;
            QVariantMap delta;
            change.beginStructure();
            change >> id >> delta;
            change.endStructure();
            edit(id, [&delta](auto &fields) { fields.insert(delta); });
        }
        change.endArray();
        const auto removal = args[1].value<QDBusArgument>();
        removal.beginArray();
        while (!removal.atEnd()) {
            int id;
            QStringList names;
            removal.beginStructure();
            removal >> id >> names;
            removal.endStructure();
            edit(id, [&names](auto &fields) { for (const auto &name : names) fields.remove(name); });
        }
        removal.endArray();
    }

private:
    void edit(int id, const std::function<void(QVariantMap &)> &change)
    {
        for (auto *action : m_menu->findChildren<QAction *>()) {
            const auto key = action->property("notifierId");
            if (key.isValid() && key.toInt() == id) {
                auto fields = action->property("notifierFields").toMap();
                change(fields);
                updateAction(action, fields);
            }
        }
    }

    QMenu *m_menu;
    QString m_service;
    QString m_path;
    quint64 m_generation = 0;
};
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
        new MenuUpdates(menu, service, path);
        menu->popup(QPoint(x, y));
    });
}

#include "notifier_menu.moc"
