# Classic notification area host

The root is a Plasma embedded containment. A contained applet can use its normal
`ContainmentItem` to read `notificationArea` (the mapped rail's host) and call
`cellForPlugin(pluginId)` for its mounted slot by stable applet plugin ID. The
lookup returns `null` if the plugin isn't mounted, including if it is hidden and
the overflow window is closed. It does not show the applet, transfer focus, or
dispatch input. The hosted applet still owns its compact/full representations
and native activation behavior. No change to stock Plasma is needed.

The only replaced artwork is in this containment; there are no shared icon-name
aliases. `reference/tools/extract-tray-art.py` reconstitutes the art from genuine,
hash-checked Windows captures.
