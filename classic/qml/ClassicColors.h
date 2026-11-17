#pragma once
#include <QObject>
#include "ClassicPrimitives.h"

namespace ClassicV2 {
class ClassicColors : public QObject {
    Q_OBJECT
    Q_PROPERTY(QColor face READ face CONSTANT)
    Q_PROPERTY(QColor light3D READ light3D CONSTANT)
    Q_PROPERTY(QColor highlight3D READ highlight3D CONSTANT)
    Q_PROPERTY(QColor shadow3D READ shadow3D CONSTANT)
    Q_PROPERTY(QColor darkShadow3D READ darkShadow3D CONSTANT)
    Q_PROPERTY(QColor window READ window CONSTANT)
    Q_PROPERTY(QColor text READ text CONSTANT)
    Q_PROPERTY(QColor grayText READ grayText CONSTANT)
    Q_PROPERTY(QColor selection READ selection CONSTANT)
    Q_PROPERTY(QColor selectionText READ selectionText CONSTANT)
    Q_PROPERTY(QColor activeCaption READ activeCaption CONSTANT)
    Q_PROPERTY(QColor inactiveCaption READ inactiveCaption CONSTANT)
    Q_PROPERTY(QColor activeCaptionGradient READ activeCaptionGradient CONSTANT)
    Q_PROPERTY(QColor inactiveCaptionGradient READ inactiveCaptionGradient CONSTANT)
public:
    QColor face() const { return Classic::Face; }
    QColor light3D() const { return Classic::Light3D; }
    QColor highlight3D() const { return Classic::Highlight3D; }
    QColor shadow3D() const { return Classic::Shadow3D; }
    QColor darkShadow3D() const { return Classic::DarkShadow3D; }
    QColor window() const { return Classic::Window; }
    QColor text() const { return Classic::Text; }
    QColor grayText() const { return Classic::GrayText; }
    QColor selection() const { return Classic::Selection; }
    QColor selectionText() const { return Classic::SelectionText; }
    QColor activeCaption() const { return Classic::ActiveCaption; }
    QColor inactiveCaption() const { return Classic::InactiveCaption; }
    QColor activeCaptionGradient() const { return Classic::ActiveCaptionGradient; }
    QColor inactiveCaptionGradient() const { return Classic::InactiveCaptionGradient; }
};
}
