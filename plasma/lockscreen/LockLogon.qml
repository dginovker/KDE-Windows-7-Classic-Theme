import org.kde.plasma.private.sessions

// This is the same private Plasma 6.8.2 API used by the stock lock screen. Keep the
// import in the required UI so a missing module is a visible theme-load failure.
LogonUi {
    SessionManagement { id: sessions }

    showSwitchUser: sessions.canSwitchUser && sessions.canLock && !busy
    onSwitchUserClicked: {
        clear();
        sessions.switchUser();
    }
}
