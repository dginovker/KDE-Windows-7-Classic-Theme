// Windows 7 Classic Explorer: Explorer's layout around KDE's KIO file widgets, which do the actual file management.
#include <KDirModel>
#include <KDirOperator>
#include <KFileItemActions>
#include <KFileItemListProperties>
#include <KIO/FileUndoManager>
#include <KIO/JobUiDelegateFactory>
#include <KIO/OpenUrlJob>
#include <KIO/Paste>
#include <KIO/PasteJob>
#include <KUrlMimeData>
#include <KUrlNavigator>
#include <KFilePlacesModel>

#include <QAbstractItemView>
#include <QActionGroup>
#include <QApplication>
#include <QClipboard>
#include <QCommandLineParser>
#include <QDir>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QTreeView>
#include <QLabel>
#include <QLineEdit>
#include <QMainWindow>
#include <QMenu>
#include <QMimeData>
#include <QSortFilterProxyModel>
#include <QSplitter>
#include <QStandardPaths>
#include <QToolButton>
#include <QTreeWidget>
#include <QVBoxLayout>

// KDirOperator's own right-click menu is a file-dialog menu (sorting, hidden files, …); Explorer's is per item.
class Files : public KDirOperator
{
public:
    using KDirOperator::KDirOperator;
    std::function<void(const KFileItem &, const QPoint &)> onMenu;

protected:
    void activatedMenu(const KFileItem &item, const QPoint &pos) override { onMenu(item, pos); }
};

class Explorer : public QMainWindow
{
public:
    explicit Explorer(const QUrl &start)
    {
        auto *central = new QWidget;
        auto *column = new QVBoxLayout(central);
        column->setContentsMargins(0, 0, 0, 0);
        column->setSpacing(0);
        setCentralWidget(central);

        files = new Files(start, this);
        files->onMenu = [this](const KFileItem &item, const QPoint &pos) { contextMenu(item, pos); };

        // Navigation row: back/forward, breadcrumb address bar, refresh, search.
        auto *navRow = new QHBoxLayout;
        navRow->setContentsMargins(4, 3, 4, 3);
        navRow->addWidget(toolButton(files->action(KDirOperator::Back)));
        navRow->addWidget(toolButton(files->action(KDirOperator::Forward)));
        address = new KUrlNavigator(new KFilePlacesModel(this), start, this);
        address->setPlacesSelectorVisible(false);
        navRow->addWidget(address, 1);
        navRow->addWidget(toolButton(files->action(KDirOperator::Reload)));
        search = new QLineEdit;
        search->setFixedWidth(222);
        search->addAction(QIcon::fromTheme(QStringLiteral("edit-find")), QLineEdit::TrailingPosition);
        navRow->addWidget(search);
        column->addLayout(navRow);

        // Command bar.
        auto *commands = new QHBoxLayout;
        commands->setContentsMargins(4, 0, 4, 2);
        organize = textButton(QStringLiteral("Organize  ▾"));
        organize->setMenu(organizeMenu());
        commands->addWidget(organize);
        auto *newFolder = textButton(QStringLiteral("New folder"));
        connect(newFolder, &QToolButton::clicked, files, &KDirOperator::mkdir);
        commands->addWidget(newFolder);
        commands->addStretch();
        commands->addWidget(viewButton());
        files->action(KDirOperator::ShowPreviewPanel)->setIcon(QIcon::fromTheme(QStringLiteral("view-split-left-right")));
        commands->addWidget(toolButton(files->action(KDirOperator::ShowPreviewPanel)));
        column->addLayout(commands);

        splitter = new QSplitter;
        splitter->addWidget(navigationPane());
        splitter->addWidget(files);
        splitter->setStretchFactor(1, 1);
        splitter->setSizes({157, 600});
        column->addWidget(splitter, 1);

        // Details pane: folder icon and item count.
        detailsPane = new QWidget;
        detailsPane->setAutoFillBackground(true);
        detailsPane->setBackgroundRole(QPalette::Base);
        detailsPane->setFixedHeight(50);
        auto *details = new QHBoxLayout(detailsPane);
        details->setContentsMargins(20, 2, 8, 2);
        details->addWidget(detailsIcon = new QLabel);
        details->addWidget(detailsText = new QLabel, 1, Qt::AlignTop);
        details->setSpacing(22);
        column->addWidget(detailsPane);

        connect(files, &KDirOperator::urlEntered, this, &Explorer::entered);
        connect(address, &KUrlNavigator::urlChanged, this, [this](const QUrl &url) { files->setUrl(url, true); });
        connect(files, &KDirOperator::fileSelected, this, &Explorer::open);
        connect(files, &KDirOperator::finishedLoading, this, &Explorer::updateDetails);
        connect(files, &KDirOperator::viewChanged, this, [this](QAbstractItemView *view) {
            view->setFrameShape(QFrame::NoFrame);
            if (auto *tree = qobject_cast<QTreeView *>(view))
                explorerColumns(tree);
            connect(view->selectionModel(), &QItemSelectionModel::selectionChanged, this, &Explorer::updateDetails);
        });
        // KDirOperator remembers its preview panel from file dialogs; Explorer starts without one.
        if (files->action(KDirOperator::ShowPreviewPanel)->isChecked())
            files->action(KDirOperator::ShowPreviewPanel)->trigger();
        // Filtering the view's model rather than KDirLister's name filter, which always shows folders.
        connect(search, &QLineEdit::textChanged, this, [this](const QString &text) {
            proxy()->setFilterCaseSensitivity(Qt::CaseInsensitive);
            proxy()->setFilterFixedString(text);
            updateDetails();
        });
        files->setFollowNewDirectories(false);
        files->setInlinePreviewShown(true);  // thumbnails, as Explorer shows by default
        // Explorer's Delete moves to the Recycle Bin; Shift+Delete deletes.
        files->action(KDirOperator::Trash)->setShortcut(QKeySequence::Delete);
        files->action(KDirOperator::Delete)->setShortcut(Qt::SHIFT | Qt::Key_Delete);
        addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Delete), files->action(KDirOperator::Rename),
                    files->action(KDirOperator::Properties), cut, copy, paste, undo, selectAll});

        setView(1);
        entered(start);
        resize(757, 530);
    }

private:
    Files *files;
    KUrlNavigator *address;
    QLineEdit *search;
    QToolButton *organize;
    QSplitter *splitter;
    QTreeWidget *pane;
    QWidget *detailsPane;
    QLabel *detailsIcon, *detailsText;
    QActionGroup *views;
    KFileItemActions openWith;
    QAction *cut = action(QStringLiteral("Cu&t"), QKeySequence::Cut, QStringLiteral("edit-cut"), [this] { toClipboard(true); });
    QAction *copy = action(QStringLiteral("&Copy"), QKeySequence::Copy, QStringLiteral("edit-copy"), [this] { toClipboard(false); });
    QAction *paste = action(QStringLiteral("&Paste"), QKeySequence::Paste, QStringLiteral("edit-paste"), [this] { pasteInto(files->url()); });
    QAction *undo = action(QStringLiteral("&Undo"), QKeySequence::Undo, QStringLiteral("edit-undo"), [] { KIO::FileUndoManager::self()->undo(); });
    QAction *selectAll = action(QStringLiteral("Select &all"), QKeySequence::SelectAll, QString(), [this] { files->view()->selectAll(); });

    QAction *action(const QString &text, QKeySequence key, const QString &icon, std::function<void()> slot)
    {
        auto *a = new QAction(QIcon::fromTheme(icon), text, this);
        a->setShortcut(key);
        connect(a, &QAction::triggered, this, slot);
        return a;
    }

    QToolButton *toolButton(QAction *a)
    {
        auto *b = new QToolButton;
        b->setDefaultAction(a);
        b->setAutoRaise(true);
        return b;
    }

    QToolButton *textButton(const QString &text)
    {
        auto *b = new QToolButton;
        b->setText(text);
        b->setAutoRaise(true);
        b->setPopupMode(QToolButton::InstantPopup);
        // Explorer puts the arrow after the text; the Windows style would draw it underneath.
        b->setStyleSheet(QStringLiteral("QToolButton::menu-indicator { image: none; }"));
        b->setMinimumHeight(26);
        return b;
    }

    QMenu *organizeMenu()
    {
        auto *menu = new QMenu(this);
        menu->addActions({cut, copy, paste, undo});
        menu->addSeparator();
        menu->addAction(selectAll);
        menu->addSeparator();
        auto *layout = menu->addMenu(QStringLiteral("&Layout"));
        auto toggle = [this, layout](const QString &text, auto show) {
            auto *a = layout->addAction(text);
            a->setCheckable(true);
            a->setChecked(true);
            connect(a, &QAction::toggled, this, show);
            return a;
        };
        toggle(QStringLiteral("&Details pane"), [this](bool on) { detailsPane->setVisible(on); });
        layout->addAction(files->action(KDirOperator::ShowPreviewPanel));
        toggle(QStringLiteral("&Navigation pane"), [this](bool on) { pane->setVisible(on); });
        menu->addSeparator();
        menu->addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Rename), files->action(KDirOperator::Properties)});
        files->action(KDirOperator::Trash)->setText(QStringLiteral("&Delete"));
        menu->addSeparator();
        menu->addAction(QStringLiteral("&Close"), this, &QWidget::close);
        connect(menu, &QMenu::aboutToShow, this, &Explorer::updateActions);
        return menu;
    }

    // Explorer's view menu, minus Tiles and Content, which KDE's views have no equivalent for.
    QToolButton *viewButton()
    {
        auto *button = new QToolButton;
        button->setAutoRaise(true);
        button->setPopupMode(QToolButton::MenuButtonPopup);
        button->setIcon(QIcon::fromTheme(QStringLiteral("view-list-icons")));
        auto *menu = new QMenu(button);
        views = new QActionGroup(this);
        const QStringList names = {QStringLiteral("Extra Large Icons"), QStringLiteral("Large Icons"), QStringLiteral("Medium Icons"),
                                   QStringLiteral("Small Icons"), QStringLiteral("List"), QStringLiteral("Details")};
        for (int i = 0; i < names.size(); ++i) {
            auto *a = menu->addAction(names[i], this, [this, i] { setView(i); });
            a->setCheckable(true);
            views->addAction(a);
        }
        button->setMenu(menu);
        // Clicking the button itself steps to the next view, as in Explorer.
        connect(button, &QToolButton::clicked, this, [this] { setView((views->actions().indexOf(views->checkedAction()) + 1) % views->actions().size()); });
        return button;
    }

    void setView(int index)
    {
        static const int sizes[] = {256, 96, 48, 16, 16, 16};
        const auto mode = index < 3 ? KDirOperator::ViewIconsView : index < 5 ? KDirOperator::ViewCompactView : KDirOperator::ViewDetailsView;
        files->action(mode)->trigger();
        files->setIconSize(sizes[index]);
        views->actions()[index]->setChecked(true);
    }

    QTreeWidget *navigationPane()
    {
        pane = new QTreeWidget;
        pane->setHeaderHidden(true);
        pane->setRootIsDecorated(false);
        pane->setIndentation(10);
        pane->setFrameShape(QFrame::NoFrame);
        // Explorer's navigation pane indents without the Windows style's dotted tree lines.
        pane->setStyleSheet(QStringLiteral("QTreeView::branch { background: palette(base); }"));
        auto place = [this](QTreeWidgetItem *parent, const QString &name, const QString &icon, const QUrl &url) {
            if (!parent && pane->topLevelItemCount()) // Explorer leaves a blank line between groups.
                (new QTreeWidgetItem(pane))->setFlags(Qt::NoItemFlags);
            auto *item = parent ? new QTreeWidgetItem(parent, {name}) : new QTreeWidgetItem(pane, {name});
            item->setIcon(0, QIcon::fromTheme(icon));
            item->setData(0, Qt::UserRole, url);
            return item;
        };
        auto path = [](QStandardPaths::StandardLocation l) { return QUrl::fromLocalFile(QStandardPaths::writableLocation(l)); };
        auto *favorites = place(nullptr, QStringLiteral("Favorites"), QStringLiteral("starred-symbolic"), {});
        place(favorites, QStringLiteral("Desktop"), QStringLiteral("user-desktop"), path(QStandardPaths::DesktopLocation));
        place(favorites, QStringLiteral("Downloads"), QStringLiteral("folder-downloads"), path(QStandardPaths::DownloadLocation));
        place(favorites, QStringLiteral("Recent Places"), QStringLiteral("document-open-recent"), QUrl(QStringLiteral("recentlyused:/locations")));
        auto *libraries = place(nullptr, QStringLiteral("Libraries"), QStringLiteral("folder-library"), path(QStandardPaths::HomeLocation));
        place(libraries, QStringLiteral("Documents"), QStringLiteral("folder-documents"), path(QStandardPaths::DocumentsLocation));
        place(libraries, QStringLiteral("Music"), QStringLiteral("folder-music"), path(QStandardPaths::MusicLocation));
        place(libraries, QStringLiteral("Pictures"), QStringLiteral("folder-pictures"), path(QStandardPaths::PicturesLocation));
        place(libraries, QStringLiteral("Videos"), QStringLiteral("folder-videos"), path(QStandardPaths::MoviesLocation));
        place(nullptr, QStringLiteral("Computer"), QStringLiteral("computer"), QUrl::fromLocalFile(QStringLiteral("/")));
        place(nullptr, QStringLiteral("Network"), QStringLiteral("network-workgroup"), QUrl(QStringLiteral("remote:/")));
        pane->expandAll();
        connect(pane, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem *item) {
            const QUrl url = item->data(0, Qt::UserRole).toUrl();
            if (url.isValid())
                files->setUrl(url, true);
        });
        return pane;
    }

    void entered(const QUrl &url)
    {
        address->setLocationUrl(url);
        const QString file = url.adjusted(QUrl::StripTrailingSlash).fileName();
        const QString name = url.path() == QLatin1String("/") && url.isLocalFile() ? QStringLiteral("Computer") : file.isEmpty() ? url.toDisplayString() : file;
        setWindowTitle(name);
        search->clear();
        search->setPlaceholderText(QStringLiteral("Search ") + name);
        detailsIcon->setPixmap(QIcon::fromTheme(KFileItem(url).iconName()).pixmap(48));
    }

    void updateDetails()
    {
        const int selected = files->selectedItems().size();
        const int total = proxy()->rowCount();
        detailsText->setText(selected ? QStringLiteral("%1 item%2 selected").arg(selected).arg(selected == 1 ? "" : "s")
                                      : QStringLiteral("%1 item%2").arg(total).arg(total == 1 ? "" : "s"));
    }

    // Explorer's Details columns: Name, Date modified, Type, Size.
    static void explorerColumns(QTreeView *tree)
    {
        for (int column : {KDirModel::Permissions, KDirModel::Owner, KDirModel::Group})
            tree->setColumnHidden(column, true);
        tree->setColumnHidden(KDirModel::Type, false);
        QHeaderView *header = tree->header();
        header->moveSection(header->visualIndex(KDirModel::ModifiedTime), 1);
        header->moveSection(header->visualIndex(KDirModel::Type), 2);
        header->setStretchLastSection(false);
        for (auto [column, width] : {std::pair{KDirModel::Name, 270}, {KDirModel::ModifiedTime, 120}, {KDirModel::Type, 120}, {KDirModel::Size, 80}}) {
            header->setSectionResizeMode(column, QHeaderView::Interactive);
            header->resizeSection(column, width);
        }
    }

    QSortFilterProxyModel *proxy() const { return static_cast<QSortFilterProxyModel *>(files->view()->model()); }

    void updateActions()
    {
        const bool any = !files->selectedItems().isEmpty();
        cut->setEnabled(any);
        copy->setEnabled(any);
        paste->setEnabled(KUrlMimeData::urlsFromMimeData(QApplication::clipboard()->mimeData()).size() > 0);
        undo->setEnabled(KIO::FileUndoManager::self()->isUndoAvailable());
    }

    void open(const KFileItem &item)
    {
        auto *job = new KIO::OpenUrlJob(item.targetUrl(), item.mimetype());
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
        job->setRunExecutables(false);
        job->start();
    }

    void toClipboard(bool cutting)
    {
        auto *data = new QMimeData;
        data->setUrls(files->selectedItems().urlList());
        KIO::setClipboardDataCut(data, cutting);
        QApplication::clipboard()->setMimeData(data);
    }

    void pasteInto(const QUrl &dir)
    {
        auto *job = KIO::paste(QApplication::clipboard()->mimeData(), dir);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
    }

    void contextMenu(const KFileItem &item, const QPoint &pos)
    {
        updateActions();
        QMenu menu(this);
        if (item.isNull()) {
            auto *view = menu.addMenu(QStringLiteral("&View"));
            view->addActions(views->actions());
            menu.addAction(files->action(KDirOperator::Reload));
            menu.addSeparator();
            menu.addAction(paste);
            menu.addAction(undo);
            menu.addSeparator();
            menu.addMenu(QStringLiteral("Ne&w"))->addAction(QIcon::fromTheme(QStringLiteral("folder-new")), QStringLiteral("&Folder"), files, &KDirOperator::mkdir);
            menu.addSeparator();
            menu.addAction(QStringLiteral("P&roperties"), this, [this] {
                files->view()->clearSelection();
                files->action(KDirOperator::Properties)->trigger();
            });
        } else {
            const KFileItemList items = files->selectedItems().isEmpty() ? KFileItemList{item} : files->selectedItems();
            auto *openItem = menu.addAction(QStringLiteral("&Open"), this, [this, items] {
                for (const KFileItem &i : items)
                    i.isDir() ? files->setUrl(i.url(), true) : open(i);
            });
            menu.setDefaultAction(openItem);
            openWith.setItemListProperties(KFileItemListProperties(items));
            openWith.setParentWidget(this);
            openWith.insertOpenWithActionsTo(nullptr, &menu, {});
            menu.addSeparator();
            menu.addActions({cut, copy});
            if (item.isDir())
                menu.addAction(QStringLiteral("&Paste"), this, [this, item] { pasteInto(item.url()); })->setEnabled(paste->isEnabled());
            menu.addSeparator();
            menu.addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Rename)});
            menu.addSeparator();
            menu.addAction(files->action(KDirOperator::Properties));
        }
        menu.exec(pos);
    }
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("win7-explorer"));
    // Matches the .desktop file, so the taskbar groups windows under it and shows its icon.
    app.setDesktopFileName(QStringLiteral("org.win7classic.explorer"));
    app.setWindowIcon(QIcon::fromTheme(QStringLiteral("org.win7classic.explorer")));
    QCommandLineParser args;
    args.addPositionalArgument(QStringLiteral("url"), QStringLiteral("Folder to open (default: Libraries, i.e. home)"));
    args.process(app);
    const QStringList urls = args.positionalArguments();
    for (const QString &u : urls.isEmpty() ? QStringList{QDir::homePath()} : urls)
        (new Explorer(QUrl::fromUserInput(u, QDir::currentPath(), QUrl::AssumeLocalFile)))->show();
    return app.exec();
}
