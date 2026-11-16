#include "ClassicPrimitives.h"
#include <QApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>
#include <QStyle>
#include <QStyleFactory>
#include <cstdio>
#include <memory>
int main(int argc,char **argv)
{
    QApplication app(argc,argv);
    if(!QStyleFactory::keys().contains("Win7Classic",Qt::CaseInsensitive)) {
        fprintf(stderr,"system-wide Win7Classic Qt style is missing; run: cd packaging && makepkg -si\n"); return 1;
    }
    if(app.arguments().contains("--available")) {
        std::unique_ptr<QStyle> candidate(QStyleFactory::create("Win7Classic"));
        if(!candidate) { fprintf(stderr,"Win7Classic plugin could not instantiate; reinstall the package\n");return 1; }
        return 0;
    }
    if(app.style()->name().compare("Win7Classic",Qt::CaseInsensitive)) {
        fprintf(stderr,"effective Qt style is %s, expected Win7Classic\n",qPrintable(app.style()->name())); return 1;
    }
    QJsonObject roles;
    const QPalette actual=app.palette(),expected=Classic::palette();
    const auto names=QMetaEnum::fromType<QPalette::ColorRole>();
    bool valid=true;
    for(auto group:{QPalette::Active,QPalette::Inactive,QPalette::Disabled}) {
        QJsonObject colors;
        for(int role=0;role<QPalette::NColorRoles;++role) {
            if(role==QPalette::NoRole) continue;
            const auto r=QPalette::ColorRole(role);
            colors[names.valueToKey(role)]=actual.color(group,r).name();
            if(actual.color(group,r)!=expected.color(group,r)) valid=false;
        }
        roles[QString::number(group)]=colors;
    }
    const QJsonObject result{{"style",app.style()->name()},{"palette",roles},
        {"font",app.font().family()},{"fontPixels",app.fontMetrics().height()},
        {"qt",qVersion()},{"dpr",app.devicePixelRatio()}};
    printf("%s\n",QJsonDocument(result).toJson(QJsonDocument::Compact).constData());
    return valid?0:2;
}
