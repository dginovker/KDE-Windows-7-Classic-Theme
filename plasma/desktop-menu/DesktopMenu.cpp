#include <KConfig>
#include <KConfigGroup>
#include <KDesktopFile>
#include <KDirModel>
#include <KFileItem>
#include <KIO/CopyJob>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegateFactory>
#include <KNewFileMenu>
#include <KPluginFactory>
#include <KUrlMimeData>
#include <Plasma/Containment>
#include <Plasma/ContainmentActions>
#include <Plasma/PluginLoader>

#include <QActionGroup>
#include <QApplication>
#include <QClipboard>
#include <QMenu>
#include <QPointer>
#include <algorithm>
#include <memory>

using namespace Qt::StringLiterals;

class DesktopMenu : public Plasma::ContainmentActions
{
    Q_OBJECT

public:
    DesktopMenu(QObject *parent, const QVariantList &args)
        : Plasma::ContainmentActions(parent, args)
        , stock(Plasma::PluginLoader::self()->loadContainmentActions(nullptr, u"org.kde.contextmenu"_s))
    {
        if (stock) stock->setParent(this);
        else qCritical("Classic desktop menu could not load the stock Plasma context-menu plugin");
    }

    void restore(const KConfigGroup &config) override
    {
        if (!stock) return;
        stock->setContainment(containment());
        // Ask the stock plugin for the display action by config key, not translated label or icon.
        KConfig memory(QString(), KConfig::SimpleConfig);
        KConfigGroup displayOnly(&memory, "display-only");
        stock->restore(displayOnly);
        if (const auto defaults = stock->contextualActions(); !defaults.isEmpty()) {
            // Stock lists the display action last. Check that disabling it removes exactly that action.
            displayOnly.writeEntry("_display_settings", false);
            stock->restore(displayOnly);
            const auto without = stock->contextualActions();
            display = (without.size() + 1 == defaults.size() && without == defaults.sliced(0, without.size())) ? defaults.last() : nullptr;
        }
        // Classic adds Gadgets by default, but the delegated checkbox must reflect and control it.
        KConfigGroup classicConfig(&memory, "classic");
        config.copyTo(&classicConfig);
        if (!classicConfig.hasKey("add widgets")) classicConfig.writeEntry("add widgets", true);
        stock->restore(classicConfig);
    }

    QWidget *createConfigurationInterface(QWidget *parent) override
    {
        return stock ? stock->createConfigurationInterface(parent) : nullptr;
    }
    void configurationAccepted() override { if (stock) stock->configurationAccepted(); }
    void save(KConfigGroup &group) override { if (stock) stock->save(group); }

    QList<QAction *> contextualActions() override
    {
        auto *desktop = containment();
        if (!stock || !desktop || desktop->containmentType() != Plasma::Containment::Desktop) return {};
        menu = std::make_unique<QMenu>();
        const auto actions = stock->contextualActions();
        const auto context = desktop->contextualActions();
        KNewFileMenu *create = nullptr;
        QAction *paste = nullptr;
        QList<QAction *> iconsCandidates;
        if (desktop->pluginMetaData().pluginId() == u"org.kde.plasma.folder"_s) {
            for (auto *action : context) {
                if (!actions.contains(action)) continue;
                if (auto *newMenu = qobject_cast<KNewFileMenu *>(action)) create = newMenu;
                else if (action->objectName() == u"paste"_s) paste = action;
                else if (isFolderViewOptions(action)) iconsCandidates.append(action);
            }
        }
        QAction *icons = iconsCandidates.size() == 1 ? iconsCandidates.constFirst() : nullptr;
        if (icons) addView(icons->menu());
        else if (iconsCandidates.size() > 1) qWarning("Classic desktop menu: ambiguous Folder View icon actions; keeping both stock options");
        if (paste) {
            // Folder View already exposes this model's actions to QML; dispatch the same refresh from the menu.
            auto *model = paste->parent();
            QAction *refresh = nullptr;
            if (QMetaObject::invokeMethod(model, "action", Qt::DirectConnection, Q_RETURN_ARG(QAction *, refresh), Q_ARG(QString, u"refresh"_s)) && refresh) {
                command(*menu, u"R&efresh"_s, refresh);
            } else {
                qWarning("Classic desktop menu: the Folder View did not supply its Refresh action");
            }
            menu->addSeparator();
            command(*menu, u"&Paste"_s, paste);
            const auto destination = model->property("resolvedUrl").toUrl();
            const auto sources = clipboardFiles();
            auto *shortcut = menu->addAction(u"Paste &shortcut"_s, this, [model = QPointer(model), sources, destination] {
                if (!model || sources != clipboardFiles() || destination != model->property("resolvedUrl").toUrl()) return;
                auto *job = KIO::link(sources, destination);
                job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, nullptr));
                KIO::FileUndoManager::self()->recordCopyJob(job);
            });
            shortcut->setEnabled(paste->isEnabled() && destination.isValid() && !sources.isEmpty());
        }
        if (create) {
            menu->addSeparator();
            auto *submenu = menu->addMenu(u"Ne&w"_s);
            auto *entry = submenu->menuAction();
            entry->setVisible(create->isVisible());
            const bool populated = addNewActions(*submenu, create->menu()->actions());
            entry->setEnabled(populated && create->isEnabled());
            if (!populated) {
                entry->setText(u"New (incompatible KIO templates)"_s);
                QStringList layout;
                for (auto *action : create->menu()->actions())
                    layout << (action->isSeparator() ? u"|"_s : action->text());
                qCritical().noquote() << "Classic desktop menu: cannot bind New commands; unexpected KIO template sections:" << layout.join(u"; "_s);
            }
        }

        menu->addSeparator();
        auto *configure = desktop->internalAction(u"configure"_s);
        if (actions.contains(display)) command(*menu, u"Screen &resolution"_s, display, art(u"display"_s));
        if (auto *add = desktop->internalAction(u"add widgets"_s); add && actions.contains(add))
            command(*menu, u"&Gadgets"_s, add, art(u"gadgets"_s));
        if (actions.contains(configure)) command(*menu, u"&Personalize"_s, configure, art(u"personalize"_s));

        // Keep the actual stock actions (including live Undo text and configured optional actions).
        menu->addSeparator();
        for (auto *action : actions) {
            if (action != create && action != paste && action != icons && action != configure && action != display
                && action != desktop->internalAction(u"add widgets"_s)) menu->addAction(action);
        }
        return menu->actions();
    }

private:
    static QList<QUrl> clipboardFiles()
    {
        const auto *data = QApplication::clipboard()->mimeData();
        if (!data) return {};
        const auto urls = KUrlMimeData::urlsFromMimeData(data);
        if (std::any_of(urls.cbegin(), urls.cend(), [](const QUrl &url) { return !url.isLocalFile(); })) return {};
        return urls;
    }

    static QIcon art(const QString &name) { return QIcon(u":/win7-desktop-menu/"_s + name + u".png"_s); }

    static QAction *command(QMenu &target, const QString &text, QAction *source, const QIcon &icon = {})
    {
        auto *action = target.addAction(icon, text, source, &QAction::trigger);
        action->setEnabled(source->isEnabled());
        action->setVisible(source->isVisible());
        action->setCheckable(source->isCheckable());
        action->setChecked(source->isChecked());
        return action;
    }

    static bool addNewActions(QMenu &submenu, const QList<QAction *> &actions)
    {
        // KIO gives non-directory actions only a transient index. Its filename-based sections
        // put home templates before system files, and the three built-in links in a final section.
        const auto n = actions.size();
        if (n < 8 || actions[0]->data().isValid() || !actions[1]->isSeparator() || !actions[n - 4]->isSeparator()) return false;
        qsizetype text = n - 5;
        while (text > 1 && !actions[text - 1]->isSeparator()) --text;
        // Check the section boundaries before relying on KIO's built-in ordering. Labels
        // only validate those positions; a matching user template elsewhere isn't a candidate.
        auto builtin = [](QAction *action, const QString &file) {
            const KDesktopFile entry(u":/kio5/newfile-templates/"_s + file + u".desktop"_s);
            return action->actionGroup() && !action->isSeparator() && action->text() == entry.readName();
        };
        if (!builtin(actions[0], u"Directory"_s) || text + 1 >= n - 4
            || !builtin(actions[text], u"TextFile"_s) || !builtin(actions[text + 1], u"EmptyFile"_s)
            || !builtin(actions[n - 3], u"linkURL"_s) || !builtin(actions[n - 2], u"linkPath"_s)
            || !builtin(actions[n - 1], u"linkProgram"_s)) return false;

        const auto add = [&submenu](const QString &label, QAction *source) {
            command(submenu, label, source, source->icon());
        };
        add(u"&Folder"_s, actions[0]);
        add(u"&Shortcut"_s, actions[n - 2]);
        for (qsizetype i = 1; i < n; ++i) {
            if (i == text) add(u"&Text Document"_s, actions[i]);
            else if (i != n - 2) submenu.addAction(actions[i]);
        }
        return true;
    }

    static bool isFolderViewOptions(QAction *action)
    {
        if (!action->isVisible() || !action->menu() || action->icon().name() != u"view-list-icons"_s) return false;
        const auto entries = action->menu()->actions();
        // Folder View puts Sort By and Icon Size first; use their QActionGroup data, not translated labels.
        if (entries.size() < 2 || !entries[0]->menu() || !entries[1]->menu()) return false;
        const auto order = entries[0]->menu()->actions();
        const auto sizes = entries[1]->menu()->actions();
        return dataAction(order, -1) && dataAction(order, KDirModel::ModifiedTime) && dataAction(sizes, 6);
    }

    void addView(QMenu *stockIcons)
    {
        const auto entries = stockIcons->actions();
        const auto order = entries[0]->menu()->actions();
        const auto sizes = entries[1]->menu()->actions();
        auto *view = menu->addMenu(u"&View"_s);
        auto *sizeGroup = new QActionGroup(view);
        for (auto [label, index] : {std::pair{u"&Large icons", 4}, {u"&Medium icons", 2}, {u"&Small icons", 1}}) {
            if (auto *size = dataAction(sizes, index); size && size->isVisible())
                sizeGroup->addAction(command(*view, QString(label), size));
        }
        if (auto *manual = dataAction(order, -1); manual) {
            if (auto *name = dataAction(order, KDirModel::Name); name) {
                view->addSeparator();
                auto *automatic = view->addAction(u"&Auto arrange icons"_s, view, [manual = QPointer(manual), name = QPointer(name)](bool checked) {
                    if (auto action = checked ? name : manual) action->trigger();
                });
                automatic->setCheckable(true);
                automatic->setChecked(!manual->isChecked());
                automatic->setEnabled(name->isEnabled() && manual->isEnabled());
            }
        }
        view->addSeparator();
        auto *other = view->addMenu(u"More icon &options"_s);
        other->addActions(entries);

        auto *sort = menu->addMenu(u"Sort &by"_s);
        for (auto [label, column] : {std::pair{u"&Name", KDirModel::Name}, {u"&Size", KDirModel::Size},
                                    {u"Item &type", KDirModel::Type}, {u"Date &modified", KDirModel::ModifiedTime}}) {
            if (auto *source = dataAction(order, column)) {
                auto *entry = command(*sort, QString(label), source);
                entry->setCheckable(false); // Native Desktop Sort By is a command list, not a radio menu.
            }
        }
    }

    static QAction *dataAction(const QList<QAction *> &actions, int value)
    {
        for (auto *action : actions)
            if (action->actionGroup() && action->data().isValid() && action->data().toInt() == value) return action;
        return nullptr;
    }

    Plasma::ContainmentActions *stock;
    QAction *display = nullptr;
    std::unique_ptr<QMenu> menu;
};

K_PLUGIN_CLASS_WITH_JSON(DesktopMenu, "desktop-menu.json")
#include "DesktopMenu.moc"
