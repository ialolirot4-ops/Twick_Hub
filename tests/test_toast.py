from twitchlink_next.presentation.qml_bridge.toast import ToastController


def test_info_emits_with_info_kind(qapp):
    controller = ToastController()
    seen = []
    controller.toastRequested.connect(lambda msg, kind: seen.append((msg, kind)))

    controller.info("Heads up")

    assert seen == [("Heads up", "info")]


def test_success_emits_with_success_kind(qapp):
    controller = ToastController()
    seen = []
    controller.toastRequested.connect(lambda msg, kind: seen.append((msg, kind)))

    controller.success("Done")

    assert seen == [("Done", "success")]


def test_error_emits_with_error_kind(qapp):
    controller = ToastController()
    seen = []
    controller.toastRequested.connect(lambda msg, kind: seen.append((msg, kind)))

    controller.error("Something needs attention")

    assert seen == [("Something needs attention", "error")]
