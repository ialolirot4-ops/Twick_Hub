import QtQuick
import TwitchLinkNext 1.0
import "../components"

Item {
    id: root

    EmptyState {
        anchors.fill: parent
        title: "No playlists yet"
        description: "Group downloaded videos and clips from Twitch and Kick into a playlist to watch them in order."
        actionLabel: "Create playlist"
        onActionRequested: ToastController.info("Playlists aren't wired up yet — that's FASE 12.")
    }
}
