import uuid
from pathlib import Path
from typing import Dict, List, Optional, cast

from qgis.core import (
    Qgis,
    QgsLayerTreeLayer,
    QgsLayerTreeNode,
    QgsMapLayer,
    QgsPathResolver,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSlot
from qgis.PyQt.QtWidgets import QAction
from qgis.utils import iface  # type: ignore

from nextgis_connect.compat import QGIS_3_34
from nextgis_connect.detached_editing import utils
from nextgis_connect.detached_editing.container.container import (
    DetachedContainer,
)
from nextgis_connect.detached_editing.container.container_factory import (
    DetachedContainerFactory,
)
from nextgis_connect.detached_editing.container.path_preprocessor import (
    DetachedEditingPathPreprocessor,
)
from nextgis_connect.detached_editing.container.ui.layer_config_widget import (
    DetachedLayerConfigWidgetFactory,
)
from nextgis_connect.detached_editing.detached_layer import DetachedLayer
from nextgis_connect.detached_editing.identification.identification_manager import (
    IdentificationManager,
)
from nextgis_connect.logging import logger
from nextgis_connect.ngw_api.core.ngw_resource_factory import (
    NGWResourceFactory,
)
from nextgis_connect.ngw_api.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.ngw_api.qgis.qgis_ngw_connection import QgsNgwConnection
from nextgis_connect.ngw_connection import NgwConnection
from nextgis_connect.ngw_connection.application.connections_manager import (
    ConnectionUpdateState,
    NgwConnectionsManager,
)
from nextgis_connect.settings import NgConnectSettings

iface: QgisInterface


class DetachedEditing(QObject):
    __containers: Dict[Path, DetachedContainer]
    __containers_by_layer_id: Dict[str, DetachedContainer]
    __is_synchronization_enabled: bool

    __timer: QTimer
    __properties_factory: DetachedLayerConfigWidgetFactory

    __path_preprocessor: Optional[DetachedEditingPathPreprocessor]
    __path_preprocessor_id: Optional[str]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        settings = NgConnectSettings()

        self.__containers = {}
        self.__containers_by_layer_id = {}
        self.__is_synchronization_enabled = True

        self.__timer = QTimer(self)
        self.__timer.setInterval(settings.layer_check_period)
        self.__timer.timeout.connect(self.synchronize_layers)
        self.__timer.start()

        self.__properties_factory = DetachedLayerConfigWidgetFactory()
        iface.registerMapLayerConfigWidgetFactory(self.__properties_factory)

        project = QgsProject.instance()
        project.layersAdded.connect(self.__on_layers_added)
        project.layersWillBeRemoved.connect(self.__on_layers_will_be_removed)

        root = project.layerTreeRoot()
        root.addedChildren.connect(self.__on_added_children)
        root.willRemoveChildren.connect(self.__on_will_remove_children)

        self.__path_preprocessor = None
        self.__path_preprocessor_id = None
        if Qgis.versionInt() // 100 * 100 == QGIS_3_34:
            # BUG in QGIS 3.34: https://github.com/qgis/QGIS/issues/58112
            logger.warning(
                "There is a bug in QGIS 3.34. Restoration of layers will be"
                " disabled"
            )
        else:
            self.__path_preprocessor = DetachedEditingPathPreprocessor()
            self.__path_preprocessor_id = QgsPathResolver.setPathPreprocessor(
                self.__path_preprocessor  # type: ignore
            )

        self._identification_manager = IdentificationManager(
            iface.mapCanvas(), self
        )
        self._identification_manager.load()

        QTimer.singleShot(0, self.__setup_layers)

    def unload(self) -> None:
        self.__timer.stop()

        self._identification_manager.unload()

        containers = list(self.__containers.values())

        self.__containers.clear()
        self.__containers_by_layer_id.clear()

        for container in containers:
            container.clear()

        if self.__path_preprocessor_id is not None:
            QgsPathResolver.removePathPreprocessor(self.__path_preprocessor_id)
            del self.__path_preprocessor

        iface.unregisterMapLayerConfigWidgetFactory(self.__properties_factory)
        del self.__properties_factory

    @property
    def is_sychronization_active(self) -> bool:
        return any(
            layer.state == utils.DetachedLayerState.Synchronization
            for layer in self.__containers.values()
        )

    @property
    def identification_action(self) -> QAction:
        return self._identification_manager.action

    @pyqtSlot(name="synchronizeLayers")
    def synchronize_layers(self) -> None:
        self.__remove_empty_containers()

        if (
            self.is_sychronization_active
            or not self.__is_synchronization_enabled
        ):
            return

        stubs = list(
            filter(
                lambda container: container.is_not_initialized,
                self.__containers.values(),
            )
        )
        containers = (
            stubs if len(stubs) > 0 else list(self.__containers.values())
        )
        for container in containers:
            is_started = container.synchronize()
            if is_started:
                return

    @pyqtSlot(name="enableSynchronization")
    def enable_synchronization(self) -> None:
        self.__is_synchronization_enabled = True

    @pyqtSlot(name="disableSynchronization")
    def disable_synchronization(self) -> None:
        self.__is_synchronization_enabled = False

    def containers(self) -> List[DetachedContainer]:
        """Return list of all detached containers."""
        return list(self.__containers.values())

    def container(self, layer: QgsVectorLayer) -> Optional[DetachedContainer]:
        """Return detached container for QGIS layer.

        :param layer: Vector layer.
        :return: Detached container or ``None`` if layer is not detached.
        """
        return self.__containers_by_layer_id.get(layer.id())

    def layer(self, layer: QgsMapLayer) -> Optional[DetachedLayer]:
        """Return detached layer for QGIS layer.

        :param layer: Vector layer.
        :return: Detached layer or ``None`` if layer is not detached.
        """
        if not isinstance(layer, QgsVectorLayer):
            return None

        container = self.__containers_by_layer_id.get(layer.id())
        if container is None:
            return None
        return container.layer(layer)

    @pyqtSlot(str, object)
    def on_connection_updated(
        self,
        connection_id: str,
        state: ConnectionUpdateState,
    ) -> None:
        if state == ConnectionUpdateState.DELETED:
            return

        connections_manager = NgwConnectionsManager()
        connection = connections_manager.connection(connection_id)
        if connection is None:
            return

        handled_paths = set()
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            container_path = self.__layer_container_path(layer)
            if container_path is not None and container_path in handled_paths:
                continue

            is_handled = self.__handle_connection_updated_for_layer(
                layer,
                connection,
                state == ConnectionUpdateState.CREATED,
            )
            if is_handled and container_path is not None:
                handled_paths.add(container_path)

    def __setup_layers(self) -> None:
        project = QgsProject.instance()
        assert project is not None
        root = project.layerTreeRoot()
        assert root is not None

        for layer in project.mapLayers().values():
            is_added = self.__setup_layer(layer)
            if not is_added:
                continue

            node = root.findLayer(layer)
            if node is None:
                continue

            self.__containers_by_layer_id[layer.id()].add_indicator(node)

        # Run after returning to event loop
        QTimer.singleShot(0, self.synchronize_layers)

    def __setup_layer(self, layer: QgsMapLayer) -> bool:
        if (
            layer.id() in self.__containers_by_layer_id
            or not utils.is_ngw_container(layer, check_metadata=True)
        ):
            return False

        container_path = utils.container_path(layer)
        container = self.__containers.get(container_path)
        if container is None:
            try:
                container = DetachedContainer(container_path, self)
            except Exception:
                logger.exception("Container is corrupted")
                return False

            self.__containers[container_path] = container
        self.__containers_by_layer_id[layer.id()] = container

        # Check if layer wasn't added to project earlier
        need_add_names = layer.customProperty("ngw_is_detached_layer") is None

        vector_layer = cast(QgsVectorLayer, layer)
        container.add_layer(vector_layer)

        if need_add_names:
            vector_layer.setName(container.metadata.layer_name)
            for field in container.metadata.fields:
                vector_layer.setFieldAlias(field.attribute, field.display_name)

        return True

    @pyqtSlot("QList<QgsMapLayer *>")
    def __on_layers_added(self, layers: List[QgsMapLayer]) -> None:
        for layer in layers:
            self.__setup_layer(layer)

        self.synchronize_layers()

    @pyqtSlot("QStringList")
    def __on_layers_will_be_removed(self, layer_ids: List[str]) -> None:
        for layer_id in layer_ids:
            if layer_id not in self.__containers_by_layer_id:
                continue

            container = self.__containers_by_layer_id.pop(layer_id)
            container.delete_layer(layer_id)

            if (
                container.is_empty
                and container.state != utils.DetachedLayerState.Synchronization
            ):
                self.__containers.pop(container.path)
                container.deleteLater()

    @pyqtSlot(QgsLayerTreeNode, int, int)
    def __on_added_children(
        self, parent_node: QgsLayerTreeNode, index_from: int, index_to: int
    ) -> None:
        children = parent_node.children()
        for index in range(index_from, index_to + 1):
            node = children[index]
            if not isinstance(node, QgsLayerTreeLayer):
                continue
            layer = node.layer()
            if layer is not None:
                if layer.id() not in self.__containers_by_layer_id:
                    continue
                self.__containers_by_layer_id[layer.id()].add_indicator(node)
            else:
                node.layerLoaded.connect(self.__on_layer_loaded)

    @pyqtSlot()
    def __on_layer_loaded(self) -> None:
        node = self.sender()
        if not isinstance(node, QgsLayerTreeLayer):
            return

        layer = node.layer()
        if not isinstance(layer, QgsVectorLayer):
            return

        if layer.id() not in self.__containers_by_layer_id:
            return

        self.__containers_by_layer_id[layer.id()].add_indicator(node)

    @pyqtSlot(QgsLayerTreeNode, int, int)
    def __on_will_remove_children(
        self, parent_node: QgsLayerTreeNode, index_from: int, index_to: int
    ) -> None:
        children = parent_node.children()
        for index in range(index_from, index_to + 1):
            node = children[index]
            if not isinstance(node, QgsLayerTreeLayer):
                continue

            layer = node.layer()
            if (
                layer is None
                or layer.id() not in self.__containers_by_layer_id
            ):
                continue

            container = self.__containers_by_layer_id[layer.id()]
            container.remove_indicator(node)

    def __remove_empty_containers(self) -> None:
        paths_for_remove = []
        for path, container in self.__containers.items():
            if (
                container.is_empty
                and container.state != utils.DetachedLayerState.Synchronization
            ):
                paths_for_remove.append(path)

        for path in paths_for_remove:
            container = self.__containers.pop(path, None)
            if container is not None:
                container.deleteLater()

    def __handle_connection_updated_for_layer(
        self, layer: QgsMapLayer, connection: NgwConnection, is_new: bool
    ) -> bool:
        if not isinstance(layer, QgsVectorLayer):
            return False

        container_path = self.__layer_container_path(layer)
        if container_path is None:
            return False

        instance_id = self.__layer_instance_id(layer, container_path)
        if instance_id != connection.domain_uuid:
            return False

        resource_id = self.__layer_resource_id(layer, container_path)
        if resource_id is None:
            return False

        container_was_created = False
        if not container_path.exists():
            is_created = self.__create_empty_container(
                connection.id, resource_id, container_path
            )
            if not is_created:
                return False

            self.__restore_layer_source(layer, container_path)
            container_was_created = True

        if not utils.is_ngw_container(container_path, check_metadata=True):
            return False

        if layer.id() not in self.__containers_by_layer_id:
            is_added = self.__setup_layer(layer)
            if not is_added:
                return False

            self.__add_indicator_if_needed(layer)

        container = self.__containers_by_layer_id.get(layer.id())
        if container is None:
            return False

        metadata = container.metadata
        if metadata is None:
            return False

        current_connection_id = metadata.connection_id
        connections_manager = NgwConnectionsManager()
        current_connection = None
        if current_connection_id:
            current_connection = connections_manager.connection(
                current_connection_id
            )

        if container_was_created:
            container.update_connection(connection.id, connection.domain_uuid)
            container.synchronize(is_manual=True)
            return True

        if current_connection_id == connection.id:
            container.update_connection(connection.id, connection.domain_uuid)
            container.refresh_additional_data()
            return True

        if is_new and current_connection is None:
            container.update_connection(connection.id, connection.domain_uuid)
            container.refresh_additional_data()
            return True

        return False

    def __add_indicator_if_needed(self, layer: QgsMapLayer) -> None:
        root = QgsProject.instance().layerTreeRoot()
        node = root.findLayer(layer)
        if node is None:
            return

        container = self.__containers_by_layer_id.get(layer.id())
        if container is None:
            return

        container.add_indicator(node)

    def __layer_container_path(self, layer: QgsMapLayer) -> Optional[Path]:
        try:
            return utils.container_path(layer)
        except Exception:
            return None

    def __layer_instance_id(
        self, layer: QgsMapLayer, container_path: Optional[Path]
    ) -> Optional[str]:
        instance_id = layer.customProperty("ngw_instance_id")
        if instance_id is not None and self.__is_uuid(str(instance_id)):
            return str(instance_id)

        if container_path is not None and self.__is_uuid(
            container_path.parent.name
        ):
            return container_path.parent.name

        return None

    def __layer_resource_id(
        self, layer: QgsMapLayer, container_path: Optional[Path]
    ) -> Optional[int]:
        resource_id = layer.customProperty("ngw_resource_id")
        if resource_id is not None:
            resource_id_string = str(resource_id)
            if resource_id_string.isdigit():
                return int(resource_id_string)

        if container_path is None:
            return None

        if container_path.stem.isdigit():
            return int(container_path.stem)

        return None

    def __create_empty_container(
        self, connection_id: str, resource_id: int, container_path: Path
    ) -> bool:
        ngw_connection = QgsNgwConnection(connection_id)
        resources_factory = NGWResourceFactory(ngw_connection)
        try:
            ngw_layer = resources_factory.get_resource(resource_id)
        except Exception:
            logger.exception("Could not resolve resource for detached layer")
            return False

        if not isinstance(ngw_layer, NGWVectorLayer):
            return False

        detached_factory = DetachedContainerFactory()
        container_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            detached_factory.create_initial_container(
                ngw_layer, container_path
            )
        except Exception:
            logger.exception("Could not create missing detached container")
            return False

        return True

    def __restore_layer_source(
        self, layer: QgsVectorLayer, container_path: Path
    ) -> None:
        try:
            layer.setDataSource(
                utils.detached_layer_uri(container_path),
                layer.name(),
                "ogr",
            )
        except Exception:
            logger.exception("Could not restore detached layer source")

    def __is_uuid(self, value: str) -> bool:
        try:
            uuid.UUID(value)
        except (TypeError, ValueError, AttributeError):
            return False

        return True
