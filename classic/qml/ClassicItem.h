#pragma once
#include <QQuickPaintedItem>
#include <QPointer>
#include <QMouseEvent>
#include <QHoverEvent>
#include "ClassicPrimitives.h"

class ClassicItem : public QQuickPaintedItem {
    Q_OBJECT
    Q_PROPERTY(QObject *eventSource READ eventSource WRITE setEventSource)
    Q_PROPERTY(bool pointerInside READ pointerInside NOTIFY pointerInsideChanged)
    Q_PROPERTY(int edge MEMBER m_edge NOTIFY changed)
    Q_PROPERTY(int flags MEMBER m_flags NOTIFY changed)
    Q_PROPERTY(bool flatBorder MEMBER m_flatBorder NOTIFY changed)
    Q_PROPERTY(bool button MEMBER m_button NOTIFY changed)
    Q_PROPERTY(bool pressed MEMBER m_pressed NOTIFY changed)
    Q_PROPERTY(bool focused MEMBER m_focused NOTIFY changed)
    Q_PROPERTY(bool disabled MEMBER m_disabled NOTIFY changed)
    Q_PROPERTY(QColor glyphColor MEMBER m_glyphColor NOTIFY changed)
    Q_PROPERTY(int glyph MEMBER m_glyph NOTIFY changed)
    Q_PROPERTY(QColor fill MEMBER m_fill NOTIFY changed)
    Q_PROPERTY(QPoint patternOrigin MEMBER m_origin NOTIFY changed)
    Q_PROPERTY(bool separator MEMBER m_separator NOTIFY changed)
public:
    enum Edge { RaisedOuter=Classic::RaisedOuter, SunkenOuter=Classic::SunkenOuter,
        RaisedInner=Classic::RaisedInner, SunkenInner=Classic::SunkenInner,
        Raised=Classic::Raised, Sunken=Classic::Sunken, Etched=Classic::Etched, Bump=Classic::Bump };
    Q_ENUM(Edge)
    enum Flag { Left=Classic::Left, Top=Classic::Top, Right=Classic::Right, Bottom=Classic::Bottom,
        Rect=Classic::Rect, Soft=Classic::Soft, Adjust=Classic::Adjust, Flat=Classic::Flat, Middle=Classic::Middle };
    Q_ENUM(Flag)
    enum Glyph { Minimize=Classic::Minimize, Maximize=Classic::Maximize, Restore=Classic::Restore,
        Close=Classic::Close, ArrowRight=Classic::ArrowRight, ArrowLeft=Classic::ArrowLeft };
    Q_ENUM(Glyph)
    explicit ClassicItem(QQuickItem *parent=nullptr) : QQuickPaintedItem(parent) {
        setAntialiasing(false); connect(this,&ClassicItem::changed,this,[this]{update();});
    }
    QObject *eventSource() const { return m_eventSource; }
    void setEventSource(QObject *source) {
        if(m_eventSource) m_eventSource->removeEventFilter(this);
        m_eventSource=source;
        if(source) source->installEventFilter(this);
    }
    bool pointerInside() const { return m_pointerInside; }
    void paint(QPainter *p) override {
        const QRect r(0,0,qRound(width()),qRound(height()));
        if(m_fill.isValid()) p->fillRect(r,m_fill);
        if(m_button) Classic::drawButton(*p,r,m_pressed);
        else if(m_edge) Classic::drawEdge(*p,r,m_edge,m_flags);
        if(m_flatBorder) Classic::drawFlatBorder(*p,r);
        if(m_separator) Classic::drawSeparator(*p,r);
        if(m_focused) Classic::drawFocusRect(*p,r,m_origin);
        if(m_glyph) Classic::drawGlyph(*p,r.translated(m_pressed?1:0,m_pressed?1:0),
            Classic::Glyph(m_glyph),m_disabled,Classic::Unchecked,m_glyphColor);
    }
signals:
    void changed();
    void pointerInsideChanged();
private:
    // Aurorae does not forward grabbed moves to MouseArea; observe the decoration's original events.
    bool eventFilter(QObject *,QEvent *event) override {
        QPointF at;
        switch(event->type()) {
        case QEvent::MouseButtonPress: case QEvent::MouseButtonRelease: case QEvent::MouseMove:
            at=static_cast<QMouseEvent *>(event)->position();break;
        case QEvent::HoverEnter: case QEvent::HoverMove:
            at=static_cast<QHoverEvent *>(event)->position();break;
        case QEvent::HoverLeave: case QEvent::Leave: at=QPointF(-1,-1);break;
        default:return false;
        }
        const bool inside=QRectF(0,0,width(),height()).contains(mapFromScene(at));
        if(inside!=m_pointerInside) { m_pointerInside=inside;emit pointerInsideChanged(); }
        return false;
    }
    QPointer<QObject> m_eventSource;
    bool m_pointerInside=false;
    int m_edge=0,m_flags=Classic::Rect,m_glyph=0;
    bool m_button=false,m_pressed=false,m_focused=false,m_disabled=false,m_separator=false,m_flatBorder=false;
    QColor m_fill,m_glyphColor=Classic::Text;
    QPoint m_origin;
};
