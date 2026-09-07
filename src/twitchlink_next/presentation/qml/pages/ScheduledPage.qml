import QtQuick
import TwitchLinkNext 1.0
import "../components"

// Empty by default rather than forced via a demo toggle: a brand-new
// install genuinely has zero scheduled downloads, so this is the honest
// default state, not a staged example.
Item {
    id: root

    EmptyState {
        anchors.fill: parent
        title: "No scheduled downloads yet"
        description: "Set a channel to auto-download its next stream or VOD, and it'll show up here."
        actionLabel: "New scheduled download"
        onActionRequested: ToastController.info("Scheduling isn't wired up yet — that's FASE 11.")
    }
}
