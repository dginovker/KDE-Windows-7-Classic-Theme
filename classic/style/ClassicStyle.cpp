#include "ClassicPrimitives.h"
#include <QApplication>
#include <QEvent>
#include <QProxyStyle>
#include <QStyleFactory>
#include <QStyleOption>
#include <QStylePlugin>
#include <QWidget>

class ClassicStyle : public QProxyStyle {
public:
    ClassicStyle() : QProxyStyle(QStyleFactory::create("Windows")) {
        if(!baseStyle()) qFatal("Win7Classic requires the Qt Windows style");
    }
    int pixelMetric(PixelMetric m,const QStyleOption *o=nullptr,const QWidget *w=nullptr) const override {
        if(m==PM_ScrollBarExtent) return 17;
        if(m==PM_ScrollBarSliderMin) return 14;
        if(m==PM_ExclusiveIndicatorWidth || m==PM_ExclusiveIndicatorHeight) return 13;
        if(m==PM_DefaultFrameWidth && w && w->property("classicFlatBorder").toBool()) return 1;
        return QProxyStyle::pixelMetric(m,o,w);
    }
    QSize sizeFromContents(ContentsType t,const QStyleOption *o,const QSize &s,const QWidget *w=nullptr) const override {
        QSize result=QProxyStyle::sizeFromContents(t,o,s,w);
        if(t==CT_ComboBox) result.setHeight(o->fontMetrics.height()+10);
        return result;
    }
    QRect subControlRect(ComplexControl c,const QStyleOptionComplex *o,SubControl sc,const QWidget *w=nullptr) const override {
        if(c==CC_GroupBox && sc==SC_GroupBoxFrame)
            return o->rect.adjusted(0,(o->fontMetrics.height()+1)/2,0,0);
        if(c==CC_ComboBox && sc==SC_ComboBoxArrow)
            return visualRect(o->direction,o->rect,QRect(o->rect.right()-17,o->rect.top()+2,16,o->rect.height()-4));
        return QProxyStyle::subControlRect(c,o,sc,w);
    }
    QPalette standardPalette() const override { return Classic::palette(); }
    void polish(QPalette &p) override {
        if(p!=Classic::palette()) m_externalPalette=p;
        p=Classic::palette();
    }
    void polish(QApplication *app) override {
        QProxyStyle::polish(app);
        m_app=app;
        app->installEventFilter(this);
        enforcePalette();
    }
    void unpolish(QApplication *app) override {
        app->removeEventFilter(this);
        m_app=nullptr;
        // KDE emits the destination palette before StyleChanged; keep that palette for the next style.
        app->setPalette(m_externalPalette);
        QProxyStyle::unpolish(app);
    }
    bool eventFilter(QObject *watched,QEvent *event) override {
        if(watched==m_app && event->type()==QEvent::ApplicationPaletteChange && !m_applyingPalette)
            enforcePalette();
        return QProxyStyle::eventFilter(watched,event);
    }
    void drawPrimitive(PrimitiveElement e,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        const bool disabled=!(o->state & State_Enabled);
        switch(e) {
        case PE_FrameFocusRect:
            Classic::drawFocusRect(*p,o->rect); return;
        case PE_IndicatorCheckBox:
            Classic::drawGlyph(*p,o->rect,Classic::Check,disabled,o->state & (State_On|State_NoChange));return;
        case PE_IndicatorRadioButton:
            Classic::drawGlyph(*p,o->rect,Classic::Radio,disabled,o->state & State_On);return;
        case PE_FrameGroupBox:
            Classic::drawEdge(*p,o->rect,Classic::Etched);return;
        case PE_PanelButtonCommand:
            Classic::drawButton(*p,o->rect,o->state & (State_Sunken|State_On));return;
        case PE_PanelLineEdit:
            if(w && w->property("classicFlatBorder").toBool()) {
                p->fillRect(o->rect,disabled?Classic::Face:Classic::Window);
                Classic::drawFlatBorder(*p,o->rect);return;
            }
            break;
        case PE_FrameLineEdit:
            if(w && w->property("classicFlatBorder").toBool()) return;
            break;
        default: break;
        }
        QProxyStyle::drawPrimitive(e,o,p,w);
    }
    void drawControl(ControlElement e,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        if(e==CE_ScrollBarAddLine || e==CE_ScrollBarSubLine || e==CE_ScrollBarSlider) {
            p->fillRect(o->rect,Classic::Face);
            Classic::drawEdge(*p,o->rect,(o->state&State_Sunken)?Classic::Sunken:Classic::Raised);
            if(e!=CE_ScrollBarSlider) {
                const bool horizontal=o->state & State_Horizontal;
                if(horizontal) {
                    const auto glyph=e==CE_ScrollBarSubLine?Classic::ArrowLeft:Classic::ArrowRight;
                    Classic::drawGlyph(*p,QRect(o->rect.center()-QPoint(2,3),QSize(4,7)),glyph,!(o->state&State_Enabled));
                } else {
                    p->save();p->translate(o->rect.center());p->rotate(e==CE_ScrollBarSubLine?180:0);
                    Classic::drawArrow(*p,QPoint(-3,-1),7);p->restore();
                }
            }
            return;
        }
        if(e==CE_ScrollBarAddPage || e==CE_ScrollBarSubPage) {
            p->fillRect(o->rect,Classic::Face);
            for(int y=o->rect.top();y<=o->rect.bottom();++y)
                for(int x=o->rect.left();x<=o->rect.right();++x)
                    if((x+y)&1) p->fillRect(x,y,1,1,Classic::Highlight3D);
            return;
        }
        if(e==CE_HeaderSection) {
            p->fillRect(o->rect,Classic::Face);
            Classic::drawEdge(*p,o->rect,(o->state&State_Sunken)?Classic::Sunken:Classic::Raised,Classic::Rect|Classic::Soft);return;
        }
        if(e==CE_PushButtonBevel) {
            auto b=qstyleoption_cast<const QStyleOptionButton *>(o);
            if(b) { Classic::drawButton(*p,b->rect,b->state & (State_Sunken|State_On),b->features & QStyleOptionButton::DefaultButton);return; }
        }
        QProxyStyle::drawControl(e,o,p,w);
    }
    void drawComplexControl(ComplexControl c,const QStyleOptionComplex *o,QPainter *p,const QWidget *w=nullptr) const override {
        if(c==CC_ComboBox) {
            auto box=qstyleoption_cast<const QStyleOptionComboBox *>(o);
            if(box && !box->editable) {
                p->fillRect(box->rect,(box->state&State_Enabled)?Classic::Window:Classic::Face);
                Classic::drawEdge(*p,box->rect,Classic::Sunken);
                const QRect arrow=subControlRect(c,o,SC_ComboBoxArrow,w);
                p->fillRect(arrow,Classic::Face);
                Classic::drawEdge(*p,arrow,box->state&State_Sunken?Classic::Sunken:Classic::Raised);
                Classic::drawArrow(*p,QPoint(arrow.center().x()-3,arrow.center().y()-2),7,
                                   (box->state&State_Enabled)?Classic::Text:Classic::GrayText);
                if(box->state&State_HasFocus) Classic::drawFocusRect(*p,subControlRect(c,o,SC_ComboBoxEditField,w));
                return;
            }
        }
        QProxyStyle::drawComplexControl(c,o,p,w);
    }
private:
    void enforcePalette() {
        if(!m_app || m_app->palette()==Classic::palette()) return;
        m_externalPalette=m_app->palette();
        m_applyingPalette=true;
        m_app->setPalette(Classic::palette());
        m_applyingPalette=false;
    }
    QApplication *m_app=nullptr;
    QPalette m_externalPalette;
    bool m_applyingPalette=false;
};
class ClassicStylePlugin : public QStylePlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.qt-project.Qt.QStyleFactoryInterface" FILE "style.json")
public:
    QStyle *create(const QString &key) override { return key.compare("Win7Classic",Qt::CaseInsensitive)==0?new ClassicStyle:nullptr; }
};
#include "ClassicStyle.moc"
