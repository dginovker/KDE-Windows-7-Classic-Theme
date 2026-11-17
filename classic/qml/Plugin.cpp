#include <QQmlExtensionPlugin>
#include "ClassicItem.h"
#include "ClassicColors.h"
class ClassicPluginV2 : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<ClassicV2::ClassicItem>(uri,1,0,"Raster");
        qmlRegisterSingletonType<ClassicV2::ClassicColors>(uri,1,0,"Palette",[](QQmlEngine *,QJSEngine *) -> QObject * { return new ClassicV2::ClassicColors; }); }
};
#include "Plugin.moc"
