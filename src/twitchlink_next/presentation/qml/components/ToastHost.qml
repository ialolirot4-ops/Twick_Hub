import QtQuick
import TwitchLinkNext 1.0

// Sits on top of everything (see AppShell.qml). Owns the transient list of
// visible toasts itself — see toast.py's module docstring for why that
// state doesn't live in Python.
Column {
    id: root
    spacing: 8
    property int _nextId: 0

    Connections {
        target: ToastController
        function onToastRequested(message, kind) {
            var id = root._nextId++;
            toastModel.append({ toastId: id, message: message, kind: kind });
        }
    }

    ListModel { id: toastModel }

    Repeater {
        model: toastModel
        delegate: Toast {
            message: model.message
            kind: model.kind

            Timer {
                interval: 3500
                running: true
                onTriggered: {
                    for (var i = 0; i < toastModel.count; i++) {
                        if (toastModel.get(i).toastId === model.toastId) {
                            toastModel.remove(i);
                            break;
                        }
                    }
                }
            }
        }
    }
}
