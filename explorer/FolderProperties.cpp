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
#include <QScrollArea>
#include <QStyle>
#include <QTabBar>
#include <QTabWidget>
#include <QTimer>

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
        installedPage = page;
        installedButtons = buttons;
        connect(this, &KPageDialog::currentPageChanged, this, [this, tabs = QPointer(ui.tabs)] {
            if (viewport && tabs && viewport->isAncestorOf(tabs))
                viewport->ensureWidgetVisible(tabs->tabBar(), 0, 0);
        });

        // Drop KIO's construction-time minimum once. The layout owns the minimum thereafter.
        setMinimumSize(0, 0);
        refresh();
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
    QPointer<KPageWidget> installedPage;
    QPointer<QDialogButtonBox> installedButtons;
    std::vector<std::function<void()>> undoPresentation;
    QPointer<QWidget> general, identity, storage;
    QPointer<QPushButton> iconPicker;
    QPointer<QLabel> created;
    bool queued = false;

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

    template<typename T>
    void margins(T *object, const QMargins &value)
    {
        undoPresentation.emplace_back([object = QPointer(object), old = object->contentsMargins()] {
            if (object)
                object->setContentsMargins(old);
        });
        object->setContentsMargins(value);
    }

    bool classic() const { return QApplication::style()->name() == QStringLiteral("win7classic"); }

    void restorePresentation()
    {
        for (QWidget *w : {general.data(), identity.data(), storage.data(), static_cast<QWidget *>(iconPicker.data())}) {
            if (w) {
                w->removeEventFilter(this);
                w->update();
            }
        }
        for (auto it = undoPresentation.rbegin(); it != undoPresentation.rend(); ++it)
            (*it)();
        undoPresentation.clear();
    }

    void syncPresentation()
    {
        if (classic() == !undoPresentation.empty())
            return;
        if (!classic()) {
            restorePresentation();
            return;
        }

        const General ui = generalPage();
        if (!ui.grid)
            return;
        auto *page = installedPage.data();
        auto *buttons = installedButtons.data();
        // Measurements in logical pixels from reference/screenshots/w7-properties.png.
        change(ui.tabs, &QTabWidget::documentMode, &QTabWidget::setDocumentMode, false);
        change(ui.tabs->tabBar(), &QTabBar::expanding, &QTabBar::setExpanding, false);
        undoPresentation.emplace_back([tabs = QPointer(ui.tabs)] {
            if (tabs)
                tabs->setProperty("classicPropertiesPane", {});
        });
        ui.tabs->setProperty("classicPropertiesPane", true);
        margins(layout(), {4, 7, 4, 4});
        change<QLayout>(layout(), &QLayout::spacing, &QLayout::setSpacing, 0);
        margins(page->layout(), {});
        // KPageView gives its footer widget an inset. The Classic row ends at the page edge instead.
        margins(buttons, {});
        margins(footerLayout.data(), {0, 6, 0, 4});
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
        iconPicker = ui.icon;
        iconPicker->installEventFilter(this);
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

    void fitPreferred()
    {
        layout()->activate();
        const QMargins margins = layout()->contentsMargins();
        const QSize footer = footerLayout->sizeHint();
        const QSize page = viewport->sizeHint();
        QSize wanted(qMax(page.width(), footer.width()) + margins.left() + margins.right(),
                     page.height() + footer.height() + margins.top() + margins.bottom() + layout()->spacing());
        if (classic())
            wanted = wanted.expandedTo({358, 446});
        // Qt Wayland bounds the initial client size with xdg_toplevel.configure_bounds.
        // KWin subtracts its panel reservation and server frame before sending them.
        resize(wanted);
    }

    void refresh()
    {
        if (!viewport || !footerLayout || !installedPage || !installedButtons || pageWidget() != installedPage
            || buttonBox() != installedButtons || !layout() || layout()->indexOf(viewport) < 0
            || layout()->indexOf(footerLayout) < 0 || viewport->widget() != installedPage
            || installedPage->pageFooter() || !installedPage->layout() || !installedButtons->layout()
            || footerLayout->indexOf(installedButtons) < 0) {
            // KPageDialog can reinstall its layout. Don't restyle or fit a tree it no longer owns.
            viewport.clear();
            restorePresentation();
            incompatible("installed page/footer ownership");
            return;
        }
        syncPresentation();
    }

    void queueRefresh()
    {
        if (!viewport || queued)
            return;
        queued = true;
        QTimer::singleShot(0, this, [this] {
            queued = false;
            refresh();
        });
    }

    void showEvent(QShowEvent *event) override
    {
        KPropertiesDialog::showEvent(event);
        if (!viewport)
            return;
        // Measure visible controls before Qt maps the surface and applies the compositor's bounds.
        refresh();
        if (viewport)
            fitPreferred();
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
        if (object == iconPicker) {
            if (event->type() == QEvent::Enter || event->type() == QEvent::Leave)
                iconPicker->update();
            if (event->type() == QEvent::Paint && !iconPicker->underMouse() && !iconPicker->hasFocus() && !iconPicker->isDown()) {
                // The reference has bare folder art; keep the real picker's bevel and focus cue on interaction.
                QPainter p(iconPicker);
                iconPicker->icon().paint(&p, QStyle::alignedRect(iconPicker->layoutDirection(), Qt::AlignCenter,
                                                               iconPicker->iconSize(), iconPicker->rect()),
                                         Qt::AlignCenter, iconPicker->isEnabled() ? QIcon::Normal : QIcon::Disabled);
                return true;
            }
        }
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

void showProperties(FolderProperties *dialog)
{
    dialog->prepare();
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->setModal(true);
    dialog->show();
}
}

void showExplorerProperties(const KFileItemList &items, QWidget *parent)
{
    if (items.isEmpty())
        return;
    showProperties(new FolderProperties(items, parent));
}

void showExplorerProperties(const QUrl &url, QWidget *parent)
{
    showProperties(new FolderProperties(url, parent));
}
