from qgis.core import QgsFeedback, QgsSettings

from nextgis_connect.legacy.plugin_update import (
    NEXTGIS_REPOSITORY_URL,
    OFFICIAL_REPOSITORY_URL,
    PLUGIN_REPOSITORIES_GROUP,
    PluginRepository,
    PluginRepositoryUrlBuilder,
    PluginUpdateChecker,
    QgisPluginRepositorySettingsReader,
)


def plugin_payload(version: str) -> bytes:
    return f"""
    <plugins>
        <pyqgis_plugin name="NextGIS Connect" version="{version}">
            <file_name>nextgis_connect</file_name>
        </pyqgis_plugin>
    </plugins>
    """.encode()


def test_update_check_uses_latest_enabled_repository_version(qgis_app) -> None:
    del qgis_app

    repositories = [
        PluginRepository("Stable", "https://stable.example.com/plugins.xml"),
        PluginRepository("Beta", "https://beta.example.com/plugins.xml"),
        PluginRepository(
            "Disabled",
            "https://disabled.example.com/plugins.xml",
            enabled=False,
        ),
    ]
    payloads = {
        "Stable": plugin_payload("3.1.0"),
        "Beta": plugin_payload("3.2.0"),
    }
    fetched_repositories = []

    def fetch(repository: PluginRepository, feedback: QgsFeedback) -> bytes:
        del feedback
        fetched_repositories.append(repository.name)
        return payloads[repository.name]

    result = PluginUpdateChecker(fetch).check(
        repositories,
        "3.0.0",
        QgsFeedback(),
    )

    assert result.update is not None
    assert result.update.available_version == "3.2.0"
    assert result.update.repository_name == "Beta"
    assert result.checked_repositories == 2
    assert fetched_repositories == ["Stable", "Beta"]


def test_update_check_returns_latest_update(qgis_app) -> None:
    del qgis_app

    repositories = [
        PluginRepository("Stable", "https://stable.example.com/plugins.xml"),
        PluginRepository("Beta", "https://beta.example.com/plugins.xml"),
    ]
    payloads = {
        "Stable": plugin_payload("3.1.0"),
        "Beta": plugin_payload("3.2.0"),
    }

    def fetch(repository: PluginRepository, feedback: QgsFeedback) -> bytes:
        del feedback
        return payloads[repository.name]

    result = PluginUpdateChecker(fetch).check(
        repositories,
        "3.0.0",
        QgsFeedback(),
    )

    assert result.update is not None
    assert result.update.available_version == "3.2.0"


def test_update_check_ignores_installed_or_missing_versions(qgis_app) -> None:
    del qgis_app

    repositories = [
        PluginRepository("Current", "https://current.example.com/plugins.xml"),
        PluginRepository("Other", "https://other.example.com/plugins.xml"),
    ]
    payloads = {
        "Current": plugin_payload("3.0.0"),
        "Other": b"""
        <plugins>
            <pyqgis_plugin name="Other plugin" version="9.9.9">
                <file_name>other_plugin</file_name>
            </pyqgis_plugin>
        </plugins>
        """,
    }

    def fetch(repository: PluginRepository, feedback: QgsFeedback) -> bytes:
        del feedback
        return payloads[repository.name]

    result = PluginUpdateChecker(fetch).check(
        repositories,
        "3.0.0",
        QgsFeedback(),
    )

    assert result.update is None
    assert result.errors == tuple()


def test_plugin_repository_url_adds_qgis_version_once(qgis_app) -> None:
    del qgis_app

    builder = PluginRepositoryUrlBuilder()
    url = builder.build("https://example.com/plugins.xml?stable=true")

    assert "stable=true" in url
    assert "&qgis=" in url
    assert builder.build(url) == url


def test_read_plugin_repositories_returns_enabled_qgis_repositories(
    qgis_app,
    reset_qgis_settings,
) -> None:
    del qgis_app, reset_qgis_settings

    settings = QgsSettings()
    settings.beginGroup(PLUGIN_REPOSITORIES_GROUP)
    try:
        settings.setValue("Custom/url", "https://custom.example.com/repo.xml")
        settings.setValue("Custom/enabled", True)
        settings.setValue(
            "Disabled/url", "https://disabled.example.com/repo.xml"
        )
        settings.setValue("Disabled/enabled", False)
    finally:
        settings.endGroup()

    repositories = QgisPluginRepositorySettingsReader(settings).read()

    by_url = {repository.url: repository for repository in repositories}
    assert by_url["https://custom.example.com/repo.xml"].can_check is True
    assert by_url["https://disabled.example.com/repo.xml"].can_check is False
    assert by_url[OFFICIAL_REPOSITORY_URL].can_check is True
    assert by_url[NEXTGIS_REPOSITORY_URL].can_check is True
