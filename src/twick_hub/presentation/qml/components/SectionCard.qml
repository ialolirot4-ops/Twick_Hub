import QtQuick
import TwickHub 1.0

// Deliberately not the generic "identical rounded card + soft shadow
// everywhere" pattern: no drop shadow (a border reads as crisp and is
// cheaper to paint), and radius/border come from Theme so every surface in
// the app agrees with itself.
Rectangle {
    default property alias content: contentItem.data
    color: Theme.surface
    radius: Theme.radiusMd
    border.width: 1
    border.color: Theme.border

    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
    }
}
