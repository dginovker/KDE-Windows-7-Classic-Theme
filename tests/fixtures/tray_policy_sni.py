"""A real StatusNotifierItem with controllable status and distinct opaque pixmaps."""
from pathlib import Path
import sys

from gi.repository import Gio, GLib

I = 'org.kde.StatusNotifierItem'
P = '/StatusNotifierItem'
V = GLib.Variant
state_file = Path(sys.argv[1])
status = state_file.read_text().strip()
normal = (231, 17, 187)
attention = (13, 227, 149)


def pixmap(rgb):
    return V('a(iiay)', [(22, 22, bytes((255, *rgb)) * (22 * 22))])


props = {
    'Id': lambda: V('s', 'w39-policy'), 'Title': lambda: V('s', 'W39 Policy'),
    'Category': lambda: V('s', 'ApplicationStatus'), 'Status': lambda: V('s', status),
    'IconName': lambda: V('s', ''), 'AttentionIconName': lambda: V('s', ''),
    'IconPixmap': lambda: pixmap(normal), 'AttentionIconPixmap': lambda: pixmap(attention),
    'ItemIsMenu': lambda: V('b', False), 'Menu': lambda: V('o', '/NO_DBUSMENU'),
}
xml = Gio.DBusNodeInfo.new_for_xml(f'<node><interface name="{I}">'
    '<method name="Activate"><arg type="i"/><arg type="i"/></method>'
    '<signal name="NewStatus"><arg type="s"/></signal>' + ''.join(
        f'<property name="{name}" type="{value().get_type_string()}" access="read"/>'
        for name, value in props.items()) + '</interface></node>')
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def activate(bus, sender, path, interface, name, args, invocation):
    print(name, args.unpack(), flush=True)
    invocation.return_value(V('()', ()))


def poll():
    global status
    next_status = state_file.read_text().strip()
    if next_status in ('Active', 'Passive', 'NeedsAttention') and next_status != status:
        status = next_status
        bus.emit_signal(None, P, I, 'NewStatus', V('(s)', (status,)))
        print(status, flush=True)
    return True


bus.register_object(P, xml.interfaces[0], activate,
                    lambda bus, sender, path, interface, name: props[name](), None)
bus.call_sync('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
              'org.kde.StatusNotifierWatcher', 'RegisterStatusNotifierItem',
              V('(s)', (P,)), None, 0, -1, None)
print(f'Registered {bus.get_unique_name()} {status}', flush=True)
GLib.timeout_add(100, poll)
GLib.MainLoop().run()
