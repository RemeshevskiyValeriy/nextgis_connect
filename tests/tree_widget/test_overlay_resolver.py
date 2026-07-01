from qgis.PyQt.QtCore import QObject, pyqtSignal

from nextgis_connect.tree_widget.overlay import (
    OverlayAction,
    OverlayButtonState,
    OverlayFacts,
    OverlayKind,
    PluginOverlayController,
    PluginOverlayResolver,
    PluginOverlayStateModel,
)


class FakeOverlayHost(QObject):
    action_requested = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.states = []

    def set_overlay_state(self, state) -> None:
        self.states.append(state)


def test_loading_has_highest_priority() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=False,
            is_loading=True,
            loading_title="Loading",
            loading_action=OverlayButtonState(
                action=OverlayAction.CANCEL,
                text="Cancel",
            ),
            has_auth_error=True,
            is_available=False,
            unavailable_message="Unavailable",
        )
    )

    assert state.kind == OverlayKind.LOADING
    assert state.title == "Loading"
    assert state.secondary_action.action == OverlayAction.CANCEL
    assert state.logo_action == OverlayAction.OPEN_NEXTGIS_SITE


def test_loading_without_corporate_background_hides_logo_action() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=True,
            is_loading=True,
            loading_draw_background=False,
        )
    )

    assert state.kind == OverlayKind.LOADING
    assert state.draw_background is False
    assert state.logo_action == OverlayAction.NONE


def test_loading_propagates_cancel_pending() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=True,
            is_loading=True,
            loading_cancel_pending=True,
            loading_action=OverlayButtonState(
                action=OverlayAction.CANCEL,
                text="Cancel",
            ),
        )
    )

    assert state.kind == OverlayKind.LOADING
    assert state.cancel_pending is True
    assert state.secondary_action.action == OverlayAction.CANCEL


def test_auth_has_priority_over_unavailable() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=True,
            has_auth_error=True,
            is_available=False,
            unavailable_message="Unavailable",
        )
    )

    assert state.kind == OverlayKind.AUTH_REQUIRED
    assert state.primary_action.action == OverlayAction.OPEN_NEXTGIS_SETTINGS


def test_first_connection_state_has_expected_actions_and_copy() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(has_connections=False)
    )

    assert state.kind == OverlayKind.WELCOME
    assert "Web GIS" in state.title
    assert (
        state.message
        == "Set up a connection to your Web GIS or create a new one to keep geodata, maps, and team workflows in sync."
    )
    assert (
        state.details
        == "Your resources will appear here after you add a connection."
    )
    assert state.primary_action.action == OverlayAction.CREATE_CONNECTION
    assert state.secondary_action.action == OverlayAction.CREATE_WEB_GIS
    assert state.secondary_action.text == "Create Web GIS"
    assert state.secondary_action.tooltip != state.secondary_action.text
    assert "web interface" in state.secondary_action.tooltip
    assert (
        state.footer_action.action == OverlayAction.CREATE_SANDBOX_CONNECTION
    )
    assert state.footer_action.text == "Try sandbox"
    assert state.logo_action == OverlayAction.OPEN_NEXTGIS_SITE


def test_controller_accepts_footer_and_logo_actions() -> None:
    state_model = PluginOverlayStateModel()
    overlay_host = FakeOverlayHost()
    controller = PluginOverlayController(state_model, overlay_host)
    emitted_actions = []
    controller.action_requested.connect(emitted_actions.append)

    state_model.update(has_connections=False)

    overlay_host.action_requested.emit(OverlayAction.CREATE_SANDBOX_CONNECTION)
    overlay_host.action_requested.emit(OverlayAction.OPEN_NEXTGIS_SITE)
    overlay_host.action_requested.emit(OverlayAction.CONTACT_SUPPORT)

    assert emitted_actions == [
        OverlayAction.CREATE_SANDBOX_CONNECTION,
        OverlayAction.OPEN_NEXTGIS_SITE,
    ]


def test_unavailable_state_propagates_action_and_illustration() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=True,
            is_available=False,
            unavailable_title="Version mismatch",
            unavailable_message="Update the plugin.",
            unavailable_details="Details",
            unavailable_icon="update",
            unavailable_action=OverlayButtonState(
                action=OverlayAction.OPEN_PLUGIN_MANAGER,
                text="Update plugin",
            ),
        )
    )

    assert state.kind == OverlayKind.UNAVAILABLE
    assert state.illustration_name == "update"
    assert state.primary_action.action == OverlayAction.OPEN_PLUGIN_MANAGER


def test_search_empty_is_used_when_other_states_are_clear() -> None:
    state = PluginOverlayResolver().resolve(
        OverlayFacts(
            has_connections=True,
            search_empty=True,
        )
    )

    assert state.kind == OverlayKind.SEARCH_EMPTY
