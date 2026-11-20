"""Live SNI tooltip and two independently callable DBusMenu objects."""
from pathlib import Path
import sys

from gi.repository import Gio, GLib

V = GLib.Variant
ITEM = 'org.kde.StatusNotifierItem'
MENU = 'com.canonical.dbusmenu'
ITEM_PATH = '/StatusNotifierItem'
flag = Path(sys.argv[1])
tooltip = menu = 'Initial'
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def register(path, xml, method, prop=None):
    interface, = Gio.DBusNodeInfo.new_for_xml(f'<node>{xml}</node>').interfaces
    bus.register_object(path, interface, method, prop, None)


def item_method(bus, sender, path, interface, name, args, invocation):
    print(name, flush=True)
    invocation.return_value(V('()', ()))


props = {
    'Id': lambda: V('s', 'w39-details'), 'Title': lambda: V('s', 'Device App'),
    'Category': lambda: V('s', 'ApplicationStatus'), 'Status': lambda: V('s', 'Active'),
    'IconPixmap': lambda: V('a(iiay)', [(22, 22, bytes((255, 37, 191, 237)) * 484)]),
    'Menu': lambda: V('o', '/' + menu), 'ItemIsMenu': lambda: V('b', False),
    'ToolTip': lambda: V('(sa(iiay)ss)', ('', [], 'Device Details', tooltip + ' Battery')),
}
register(ITEM_PATH, f'<interface name="{ITEM}">'
         '<method name="Activate"><arg type="i"/><arg type="i"/></method>'
         '<method name="ProvideXdgActivationToken"><arg type="s"/></method>'
         '<signal name="NewToolTip"/><signal name="NewMenu"/>' + ''.join(
             f'<property name="{name}" type="{value().get_type_string()}" access="read"/>'
             for name, value in props.items()) + '</interface>', item_method,
         lambda bus, sender, path, interface, name: props[name]())


def menu_method(bus, sender, path, interface, name, args, invocation):
    print(path, name, args.unpack(), flush=True)
    if name == 'GetLayout':
        invocation.return_value(V('(u(ia{sv}av))', (1, (0, {}, [V('(ia{sv}av)', (
            1, {'label': V('s', path[1:] + ' Action')}, []))]))))
    elif name == 'AboutToShow':
        invocation.return_value(V('(b)', (False,)))
    else:
        invocation.return_value(V('()', ()))


for path in ('/Initial', '/Updated'):
    register(path, f'<interface name="{MENU}">'
             '<method name="GetLayout"><arg type="i"/><arg type="i"/><arg type="as"/>'
             '<arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>'
             '<method name="AboutToShow"><arg type="i"/><arg type="b" direction="out"/></method>'
             '<method name="Event"><arg type="i"/><arg type="s"/><arg type="v"/><arg type="u"/></method>'
             '</interface>', menu_method)


def update():
    global tooltip, menu
    if flag.exists():
        requested = flag.read_text().strip()
        if requested == 'menu' and menu == 'Initial':
            menu = 'Updated'
            bus.emit_signal(None, ITEM_PATH, ITEM, 'NewMenu', None)
            print('Updated menu path', flush=True)
        if requested == 'tooltip' and tooltip == 'Initial':
            tooltip = 'Updated'
            bus.emit_signal(None, ITEM_PATH, ITEM, 'NewToolTip', None)
            print('Updated tooltip', flush=True)
    return True


bus.call_sync('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
              'org.kde.StatusNotifierWatcher', 'RegisterStatusNotifierItem',
              V('(s)', (ITEM_PATH,)), None, 0, -1, None)
print('Registered ' + bus.get_unique_name(), flush=True)
GLib.timeout_add(100, update)
GLib.MainLoop().run()
