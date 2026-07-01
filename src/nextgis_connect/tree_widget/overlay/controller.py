from typing import Optional

from qgis.PyQt.QtCore import QCoreApplication, QObject, pyqtSignal

from nextgis_connect.utils import utm_tags

from .state import (
    OverlayAction,
    OverlayButtonState,
    OverlayFacts,
    OverlayKind,
    OverlayState,
    PluginOverlayStateModel,
)


class PluginOverlayResolver:
    def resolve(self, facts: OverlayFacts) -> OverlayState:
        if facts.is_loading:
            return OverlayState(
                kind=OverlayKind.LOADING,
                title=facts.loading_title or self._translate("Please wait"),
                message=facts.loading_message
                or self._translate("The resource tree is being updated."),
                details=facts.loading_details,
                secondary_action=facts.loading_action,
                logo_action=(
                    OverlayAction.OPEN_NEXTGIS_SITE
                    if facts.loading_draw_background
                    else OverlayAction.NONE
                ),
                draw_background=facts.loading_draw_background,
                show_progress=True,
                cancel_pending=facts.loading_cancel_pending,
            )

        if facts.has_auth_error:
            return OverlayState(
                kind=OverlayKind.AUTH_REQUIRED,
                title=self._translate("Sign in to continue"),
                message=self._translate(
                    "The selected connection uses a NextGIS account."
                ),
                details=self._translate(
                    "Open NextGIS settings in QGIS and sign in, then reload the resource tree."
                ),
                primary_action=OverlayButtonState(
                    action=OverlayAction.OPEN_NEXTGIS_SETTINGS,
                    text=self._translate("Open NextGIS settings"),
                ),
                logo_action=OverlayAction.OPEN_NEXTGIS_SITE,
            )

        if not facts.is_available:
            return OverlayState(
                kind=OverlayKind.UNAVAILABLE,
                title=facts.unavailable_title
                or self._translate("Web GIS is unavailable"),
                message=facts.unavailable_message,
                details=facts.unavailable_details,
                illustration_name=facts.unavailable_icon,
                primary_action=facts.unavailable_action,
                logo_action=OverlayAction.OPEN_NEXTGIS_SITE,
            )

        if facts.has_error:
            return OverlayState(
                kind=OverlayKind.ERROR,
                title=facts.error_title or self._translate("Request failed"),
                message=facts.error_message,
                details=facts.error_details,
                illustration_name=facts.error_icon,
                primary_action=facts.error_action,
                secondary_action=facts.error_secondary_action,
                logo_action=OverlayAction.OPEN_NEXTGIS_SITE,
            )

        if facts.has_pending_migration:
            return OverlayState(
                kind=OverlayKind.MIGRATION_REQUIRED,
                title=self._translate("Update saved connections"),
                message=self._translate(
                    "Saved connections need to be converted to the QGIS authentication system before the tree can be loaded."
                ),
                details=self._translate(
                    "The conversion is performed once and keeps the existing connections available in the plugin."
                ),
                primary_action=OverlayButtonState(
                    action=OverlayAction.CONVERT_CONNECTIONS,
                    text=self._translate("Convert connections"),
                ),
                logo_action=OverlayAction.OPEN_NEXTGIS_SITE,
            )

        if not facts.has_connections:
            return OverlayState(
                kind=OverlayKind.WELCOME,
                title=self._translate(
                    'Connect your first <span style="color: #0c65af;">Web GIS</span>'
                ),
                message=self._translate(
                    "Set up a connection to your Web GIS or create a new one to keep geodata, maps, and team workflows in sync."
                ),
                details=self._translate(
                    "Your resources will appear here after you add a connection."
                ),
                primary_action=OverlayButtonState(
                    action=OverlayAction.CREATE_CONNECTION,
                    text=self._translate("Add connection"),
                ),
                secondary_action=OverlayButtonState(
                    action=OverlayAction.CREATE_WEB_GIS,
                    text=self._translate("Create Web GIS"),
                    tooltip=self._translate(
                        "Open the web interface to create a new Web GIS."
                    ),
                ),
                footer_action=OverlayButtonState(
                    action=OverlayAction.CREATE_SANDBOX_CONNECTION,
                    text=self._translate("Try sandbox"),
                    tooltip=self._translate(
                        "Create a connection to the sandbox Web GIS."
                    ),
                ),
                logo_action=OverlayAction.OPEN_NEXTGIS_SITE,
            )

        if facts.search_empty:
            return OverlayState(
                kind=OverlayKind.SEARCH_EMPTY,
                title=self._translate("Nothing found"),
                message=self._translate(
                    "No resources match the current search query."
                ),
                draw_background=False,
            )

        return OverlayState(kind=OverlayKind.NONE)

    def create_web_gis_url(self) -> str:
        return f"https://my.nextgis.com/?{utm_tags('start')}"

    def _translate(self, text: str) -> str:
        return QCoreApplication.translate("PluginOverlayResolver", text)


class PluginOverlayController(QObject):
    action_requested = pyqtSignal(object)
    state_changed = pyqtSignal(object)

    _current_state: OverlayState

    def __init__(
        self,
        state_model: PluginOverlayStateModel,
        overlay_host,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._state_model = state_model
        self._overlay_host = overlay_host
        self._resolver = PluginOverlayResolver()
        self._current_state = OverlayState(kind=OverlayKind.NONE)

        self._state_model.changed.connect(self.refresh)
        self._overlay_host.action_requested.connect(self._handle_action)
        self.refresh()

    @property
    def current_state(self) -> OverlayState:
        return self._current_state

    @property
    def resolver(self) -> PluginOverlayResolver:
        return self._resolver

    def refresh(self) -> None:
        self._current_state = self._resolver.resolve(
            self._state_model.snapshot()
        )
        self._overlay_host.set_overlay_state(self._current_state)
        self.state_changed.emit(self._current_state)

    def _handle_action(self, action: OverlayAction) -> None:
        if action == OverlayAction.NONE:
            return

        active_actions = {
            self._current_state.primary_action.action,
            self._current_state.secondary_action.action,
            self._current_state.footer_action.action,
            self._current_state.logo_action,
        }
        if action not in active_actions:
            return

        self.action_requested.emit(action)
