import QtQuick
import QtQuick.Layouts
import TwickHub 1.0
import "components"

Rectangle {
    id: root
    color: Theme.background

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.fillHeight: true
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Header {
                Layout.fillWidth: true
            }

            // A fresh Loader per navigation avoids every page's state (scroll
            // position, in-progress mock interactions) leaking into the
            // next one — acceptable to reload a mocked page's QML each time
            // at this phase; FASE 9+ revisits this once pages hold real,
            // possibly-expensive-to-refetch data.
            Loader {
                id: pageLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                source: NavigationController.currentPageSource
                asynchronous: true
            }
        }
    }

    ToastHost {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Theme.spacingLg
    }
}
