#include <QQmlExtensionPlugin>
#include "ClassicItem.h"
#include "ClassicColors.h"
class ClassicPlugin : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<ClassicItem>(uri,1,0,"Raster");
        qmlRegisterSingletonType<ClassicColors>(uri,1,0,"Palette",[](QQmlEngine *,QJSEngine *) -> QObject * { return new ClassicColors; }); }
};
#include "Plugin.moc"
