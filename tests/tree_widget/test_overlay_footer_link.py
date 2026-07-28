from nextgis_connect.legacy.tree_widget.overlay.state import (
    OverlayAction,
    OverlayButtonState,
)
from nextgis_connect.legacy.tree_widget.overlay.widgets.surface import (
    FooterLinkLabel,
)


def test_skip_update_footer_link_uses_stronger_opacity_on_hover() -> None:
    action_state = OverlayButtonState(
        action=OverlayAction.SKIP_PLUGIN_UPDATE,
        text="Skip this time",
        text_opacity=0.5,
    )

    assert (
        FooterLinkLabel._effective_text_opacity_for(
            action_state,
            is_hovered=False,
        )
        == 0.5
    )
    assert (
        FooterLinkLabel._effective_text_opacity_for(
            action_state,
            is_hovered=True,
        )
        == 0.8
    )


def test_regular_footer_link_keeps_configured_opacity_on_hover() -> None:
    action_state = OverlayButtonState(
        action=OverlayAction.CREATE_SANDBOX_CONNECTION,
        text="Try sandbox",
        text_opacity=0.5,
    )

    assert (
        FooterLinkLabel._effective_text_opacity_for(
            action_state,
            is_hovered=True,
        )
        == 0.5
    )
