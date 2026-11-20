#include <KConfig>
#include <KConfigGroup>
#include <KDirModel>
#include <KIO/CopyJob>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegateFactory>
#include <KIO/StatJob>
#include <KIO/StoredTransferJob>
#include <KNameAndUrlInputDialog>
#include <KNewFileMenu>
#include <KPluginFactory>
#include <KProtocolInfo>
#include <KUrlMimeData>
#include <Plasma/Containment>
#include <Plasma/ContainmentActions>
#include <Plasma/PluginLoader>

#include <QActionGroup>
#include <QApplication>
#include <QClipboard>
#include <QDir>
#include <QFileInfo>
#include <QMenu>
#include <QPointer>
#include <QInputDialog>
#include <QMessageBox>
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
            create->checkUpToDate(); // The stock submenu may not have been opened yet.
            menu->addSeparator();
            auto *submenu = menu->addMenu(u"Ne&w"_s);
            auto *entry = submenu->menuAction();
            entry->setVisible(create->isVisible());
            addNewActions(*submenu, create);
            entry->setEnabled(create->isEnabled() && !submenu->isEmpty());
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

    static QUrl newItemUrl(const QUrl &directory, const QString &name)
    {
        if (name.trimmed().isEmpty() || name == u"."_s || name == u".."_s || name.contains(u'/')) {
            QMessageBox::warning(nullptr, u"Create New"_s, u"Enter a single file name, not a path."_s);
            return {};
        }
        return QUrl::fromLocalFile(QDir(directory.toLocalFile()).filePath(name));
    }

    static void createShortcut(const QUrl &directory, KNewFileMenu *create)
    {
        auto *dialog = new KNameAndUrlInputDialog(u"Name for new link:"_s, u"Path to file or directory:"_s, directory, nullptr);
        dialog->setAttribute(Qt::WA_DeleteOnClose);
        dialog->setWindowTitle(u"Create Symlink"_s);
        QObject::connect(dialog, &QDialog::accepted, create, [dialog, directory] {
            const auto target = dialog->url();
            if (!target.isLocalFile() || !QDir::isAbsolutePath(target.toLocalFile())) {
                QMessageBox::warning(nullptr, u"Create Symlink"_s, u"Choose a local file or directory for the shortcut."_s);
                return;
            }
            const auto dest = newItemUrl(directory, dialog->name());
            if (!dest.isValid()) return;
            auto *job = KIO::linkAs(target, dest);
            job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, nullptr));
            KIO::FileUndoManager::self()->recordCopyJob(job);
        });
        dialog->show();
    }

    static void createTextDocument(const QUrl &directory)
    {
        bool accepted = false;
        auto name = QInputDialog::getText(nullptr, u"Create Text Document"_s, u"Name for new text document:"_s,
                                          QLineEdit::Normal, u"New Text Document.txt"_s, &accepted);
        if (!accepted) return;
        const auto dest = newItemUrl(directory, name);
        if (!dest.isValid()) return;
        auto *job = KIO::storedPut(QByteArray{}, dest, -1);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, nullptr));
        KIO::FileUndoManager::self()->recordJob(KIO::FileUndoManager::Put, {}, dest, job);
    }

    static void addNewActions(QMenu &submenu, KNewFileMenu *create)
    {
        const auto actions = create->menu()->actions();
        const auto addStock = [&submenu, create](const QString &label, QAction *source) {
            auto *entry = submenu.addAction(source->icon(), label, create, [create, action = QPointer(source)] {
                // A filesystem watcher can invalidate KIO's indices while the popup is open.
                create->checkUpToDate();
                if (action) action->trigger();
                else qCritical("Classic desktop menu: KIO templates changed; reopen New before selecting a template");
            });
            entry->setEnabled(source->isEnabled());
            entry->setVisible(source->isVisible());
            entry->setShortcuts(source->shortcuts());
            entry->setShortcutContext(source->shortcutContext());
        };
        // Only KIO's directory constructor has no template index.
        auto it = std::find_if(actions.cbegin(), actions.cend(), [](QAction *action) {
            return action->actionGroup() && !action->data().isValid();
        });
        QAction *folder = it == actions.cend() ? nullptr : *it;
        if (folder) addStock(u"&Folder"_s, folder);
        else qWarning("Classic desktop menu: cannot verify the KIO Folder action");

        // Cached template actions expose only indices, not the operations behind them.
        // Keep those templates under their own labels and invoke the two known KIO jobs directly.
        const auto directory = create->workingDirectory();
        const bool local = directory.isLocalFile() || KProtocolInfo::protocolClass(directory.scheme()) == u":local"_s;
        const auto addLocal = [&submenu, create, directory, local](const QString &label, const QIcon &icon, bool shortcut) {
            auto *entry = submenu.addAction(icon, label, create, [create, directory, shortcut] {
                auto *job = KIO::mostLocalUrl(directory);
                QObject::connect(job, &KJob::result, create, [job, create, shortcut] {
                    const auto dest = job->mostLocalUrl();
                    if (job->error() || !dest.isLocalFile()) {
                        QMessageBox::warning(nullptr, u"Create New"_s, u"The desktop location is not a local folder."_s);
                        return;
                    }
                    if (shortcut) createShortcut(dest, create);
                    else createTextDocument(dest);
                });
            });
            entry->setEnabled(local);
        };
        addLocal(u"&Shortcut"_s, QIcon::fromTheme(u"emblem-symbolic-link"_s), true);
        addLocal(u"&Text Document"_s, QIcon::fromTheme(u"text-plain"_s), false);
        submenu.addSeparator();
        for (auto *action : actions) {
            if (action->isSeparator()) submenu.addSeparator();
            else if (action != folder) addStock(action->text(), action);
        }
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
