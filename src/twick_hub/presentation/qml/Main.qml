import QtQuick
import QtQuick.Window

// FASE 2: real shell (sidebar, header, navigation, theme, toasts). Pages
// are still mocked — no real Twitch/Kick connection (Master Plan §36).
Window {
    id: root
    width: 1180
    height: 720
    visible: true
    title: "Twick Hub"

    AppShell {
        anchors.fill: parent
    }
}
