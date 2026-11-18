#include "FolderProperties.h"

#include "ClassicPrimitives.h"
#include <KPageWidget>
#include <KPropertiesDialog>
#include <QApplication>
#include <QDialogButtonBox>
#include <QGridLayout>
#include <QLabel>
#include <QPointer>
#include <QPushButton>
#include <QScreen>
#include <QScrollArea>
#include <QStyle>
#include <QTabBar>
#include <QTabWidget>
#include <QTimer>
#include <QWindow>

#include <functional>
#include <vector>

namespace {
class PropertiesViewport : public QScrollArea
{
public:
    QSize sizeHint() const override
    {
        // The content's minimum excludes spare space; it is a preference, not the viewport floor.
        return widget() ? widget()->minimumSizeHint() : QScrollArea::sizeHint();
    }
};

class FolderProperties : public KPropertiesDialog
{
public:
    using KPropertiesDialog::KPropertiesDialog;

    void prepare()
    {
        const auto list = items();
        if (list.size() != 1 || !list.first().isDir() || !list.first().url().isLocalFile())
            return;
        auto *root = qobject_cast<QVBoxLayout *>(layout());
        auto *page = pageWidget();
        auto *buttons = buttonBox();
        if (!root || !page || !buttons || root->indexOf(page) < 0 || page->pageFooter() != buttons || !page->layout()
            || page->layout()->indexOf(buttons) < 0 || !buttons->layout()) {
            incompatible("page widget/button-box layout");
            return;
        }
        const General ui = generalPage();
        if (!ui.grid)
            return;

        auto *scroll = new PropertiesViewport;
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setWidgetResizable(true);
        delete root->replaceWidget(page, scroll, Qt::FindDirectChildrenOnly);
        // Keep the original KIO button box and its connections outside the scrolling pane.
        page->setPageFooter(nullptr);
        scroll->setWidget(page);
        auto *footer = new QHBoxLayout;
        footer->setContentsMargins(page->layout()->contentsMargins());
        footer->addWidget(buttons);
        root->addLayout(footer);
        footerLayout = footer;
        viewport = scroll;
        connect(this, &KPageDialog::currentPageChanged, scroll, [scroll, tabs = QPointer(ui.tabs)] {
            if (tabs)
                scroll->ensureWidgetVisible(tabs->tabBar(), 0, 0);
        });

        // Drop KIO's construction-time minimum once. The layout owns the minimum thereafter.
        setMinimumSize(0, 0);
        syncPresentation();
        fit(true);
    }

private:
    struct General {
        QTabWidget *tabs = nullptr;
        QWidget *page = nullptr;
        QVBoxLayout *column = nullptr;
        QGridLayout *grid = nullptr;
        QHBoxLayout *iconRow = nullptr;
        QPushButton *icon = nullptr;
        QLabel *created = nullptr;
        QWidget *identity = nullptr;
        QWidget *storage = nullptr;
    };

    QPointer<PropertiesViewport> viewport;
    QPointer<QLayout> footerLayout;
    QMetaObject::Connection workAreaChanged;
    std::vector<std::function<void()>> undoPresentation;
    QPointer<QWidget> general, identity, storage;
    QPointer<QLabel> created;
    bool queued = false;
    bool firstShow = true;

    void incompatible(const char *part)
    {
        qWarning("Win7 Explorer: cannot style KDE folder Properties: unexpected %s (Qt %s). "
                 "Report the installed KIO and Qt versions with issue #38; using the unmodified controls.", part, qVersion());
    }

    General generalPage()
    {
        auto *page = pageWidget();
        auto *tabs = page ? page->findChild<QTabWidget *>() : nullptr;
        // KIO provides no public General-page accessor. Validate the generated UI, not translated captions.
        auto *general = tabs ? tabs->findChild<QWidget *>(QStringLiteral("KFilePropsPluginWidget")) : nullptr;
        constexpr auto only = Qt::FindDirectChildrenOnly;
        auto *column = general ? qobject_cast<QVBoxLayout *>(general->layout()) : nullptr;
        auto *grid = column ? column->findChild<QGridLayout *>(QStringLiteral("gridLayout"), only) : nullptr;
        auto *iconRow = grid ? grid->findChild<QHBoxLayout *>(QStringLiteral("iconLayout"), only) : nullptr;
        auto *icon = general ? general->findChild<QPushButton *>(QStringLiteral("iconButton"), only) : nullptr;
        auto *created = general ? general->findChild<QLabel *>(QStringLiteral("createdTimeLabel_Left"), only) : nullptr;
        auto *identity = general ? general->findChild<QWidget *>(QStringLiteral("kseparator_2"), only) : nullptr;
        auto *storage = general ? general->findChild<QWidget *>(QStringLiteral("fsSeparator"), only) : nullptr;
        if (!grid || column->indexOf(grid) < 0 || !iconRow || grid->indexOf(iconRow) < 0 || !icon || iconRow->indexOf(icon) < 0
            || !created || grid->indexOf(created) < 0 || !identity || grid->indexOf(identity) < 0
            || !storage || grid->indexOf(storage) < 0) {
            incompatible("General-page layout (grid, icon row, timestamp or separators)");
            return {};
        }
        return {tabs, general, column, grid, iconRow, icon, created, identity, storage};
    }

    template<typename T, typename V, typename U = V>
    void change(T *object, V (T::*get)() const, void (T::*set)(U), V value)
    {
        undoPresentation.emplace_back([object = QPointer(object), set, old = (object->*get)()] {
            if (object)
                (object.data()->*set)(old);
        });
        (object->*set)(value);
    }

    void margins(QLayout *layout, const QMargins &value)
    {
        undoPresentation.emplace_back([layout = QPointer(layout), old = layout->contentsMargins()] {
            if (layout)
                layout->setContentsMargins(old);
        });
        layout->setContentsMargins(value);
    }

    bool classic() const { return QApplication::style()->name() == QStringLiteral("win7classic"); }

    void syncPresentation()
    {
        if (classic() == !undoPresentation.empty())
            return;
        if (!classic()) {
            for (QWidget *w : {general.data(), identity.data(), storage.data()}) {
                if (w) {
                    w->removeEventFilter(this);
                    w->update();
                }
            }
            for (auto it = undoPresentation.rbegin(); it != undoPresentation.rend(); ++it)
                (*it)();
            undoPresentation.clear();
            return;
        }

        const General ui = generalPage();
        auto *page = pageWidget();
        auto *buttons = buttonBox();
        if (!ui.grid)
            return;
        if (!layout() || !footerLayout || !page->layout() || !buttons || !buttons->layout()
            || footerLayout->indexOf(buttons) < 0) {
            incompatible("dialog/footer ownership after style change");
            return;
        }
        // Measurements in logical pixels from reference/screenshots/w7-properties.png.
        change(ui.tabs, &QTabWidget::documentMode, &QTabWidget::setDocumentMode, false);
        change(ui.tabs->tabBar(), &QTabBar::expanding, &QTabBar::setExpanding, false);
        margins(layout(), {4, 4, 4, 4});
        change<QLayout>(layout(), &QLayout::spacing, &QLayout::setSpacing, 0);
        margins(page->layout(), {});
        margins(footerLayout, {});
        margins(ui.column, {14, 9, 14, 9});
        change(ui.grid, &QGridLayout::horizontalSpacing, &QGridLayout::setHorizontalSpacing, 12);
        change(ui.grid, &QGridLayout::verticalSpacing, &QGridLayout::setVerticalSpacing, 7);
        for (auto *label : ui.page->findChildren<QLabel *>(QString(), Qt::FindDirectChildrenOnly)) {
            if (label->buddy() && ui.grid->indexOf(label) >= 0)
                change(label, &QLabel::alignment, &QLabel::setAlignment,
                       (label->alignment() & Qt::AlignVertical_Mask) | Qt::AlignLeading);
        }
        change<QBoxLayout>(ui.iconRow, &QBoxLayout::direction, &QBoxLayout::setDirection, QBoxLayout::RightToLeft);
        change<QWidget>(ui.icon, &QWidget::minimumSize, &QWidget::setMinimumSize, QSize(38, 38));
        change<QWidget>(ui.icon, &QWidget::maximumSize, &QWidget::setMaximumSize, QSize(38, 38));
        change<QAbstractButton>(ui.icon, &QAbstractButton::iconSize, &QAbstractButton::setIconSize, QSize(32, 32));
        change<QLayout>(buttons->layout(), &QLayout::spacing, &QLayout::setSpacing, 6);
        general = ui.page;
        created = ui.created;
        identity = ui.identity;
        storage = ui.storage;
        for (auto *rule : {ui.identity, ui.storage}) {
            change(rule, &QWidget::minimumSize, &QWidget::setMinimumSize, QSize(0, 2));
            change(rule, &QWidget::maximumSize, &QWidget::setMaximumSize, QSize(QWIDGETSIZE_MAX, 2));
            rule->installEventFilter(this);
        }
        general->installEventFilter(this);
    }

    void watchScreen(QScreen *screen)
    {
        disconnect(workAreaChanged);
        if (screen)
            workAreaChanged = connect(screen, &QScreen::availableGeometryChanged, this, &FolderProperties::queueRefresh);
        queueRefresh();
    }

    void fit(bool preferred = false)
    {
        if (!viewport || !screen())
            return;
        layout()->activate();
        QMargins frame = windowHandle() ? windowHandle()->frameMargins() : QMargins();
        if (QGuiApplication::platformName() == QStringLiteral("wayland") && frame.isNull()) {
            // Wayland does not report the server-side title bar to the client. Leave room for it
            // rather than filling the entire output with the client area and clipping the footer.
            frame = {8, qMax(32, fontMetrics().height() + 12), 8, 8};
        }
        const QSize available = screen()->availableGeometry().marginsRemoved(frame).size();
        QSize wanted = size();
        if (preferred) {
            const QMargins margins = layout()->contentsMargins();
            const QSize footer = footerLayout->sizeHint();
            wanted = QSize(qMax(viewport->sizeHint().width(), footer.width()) + margins.left() + margins.right(),
                           viewport->sizeHint().height() + footer.height() + margins.top() + margins.bottom() + layout()->spacing());
            if (classic())
                wanted = wanted.expandedTo({358, 446});
        }
        const QSize bounded = wanted.boundedTo(available).expandedTo(minimumSize());
        if (bounded != size())
            resize(bounded);
    }

    void queueRefresh()
    {
        if (!viewport || queued)
            return;
        queued = true;
        QTimer::singleShot(0, this, [this] {
            queued = false;
            syncPresentation();
            fit(firstShow && isVisible());
            if (isVisible())
                firstShow = false;
        });
    }

    void showEvent(QShowEvent *event) override
    {
        KPropertiesDialog::showEvent(event);
        if (viewport && windowHandle()) {
            connect(windowHandle(), &QWindow::screenChanged, this, &FolderProperties::watchScreen, Qt::UniqueConnection);
            watchScreen(windowHandle()->screen());
        }
    }

    bool event(QEvent *event) override
    {
        const bool handled = KPropertiesDialog::event(event);
        if (event->type() == QEvent::StyleChange || event->type() == QEvent::FontChange || event->type() == QEvent::LayoutRequest
            || event->type() == QEvent::Resize)
            queueRefresh();
        return handled;
    }

    bool eventFilter(QObject *object, QEvent *event) override
    {
        if (event->type() == QEvent::Paint) {
            if (object == general && created && created->isVisible() && general->layout()) {
                QPainter p(general);
                const auto bounds = general->contentsRect().marginsRemoved(general->layout()->contentsMargins());
                Classic::drawSeparator(p, {bounds.x(), created->y() - 5, bounds.width(), 2});
            } else if (object == identity || object == storage) {
                auto *rule = static_cast<QWidget *>(object);
                QPainter p(rule);
                Classic::drawSeparator(p, rule->rect());
                return true;
            }
        }
        return KPropertiesDialog::eventFilter(object, event);
    }
};
}

void showExplorerProperties(const KFileItemList &items, QWidget *parent)
{
    if (items.isEmpty())
        return;
    auto *dialog = new FolderProperties(items, parent);
    dialog->prepare();
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->setModal(true);
    dialog->show();
}

void showExplorerProperties(const QUrl &url, QWidget *parent)
{
    auto *dialog = new FolderProperties(url, parent);
    dialog->prepare();
    dialog->exec();
}
