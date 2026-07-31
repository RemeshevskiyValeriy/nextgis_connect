import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsMapLayer,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
)


@dataclass(frozen=True)
class ExtentBounds:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def normalized(self) -> "ExtentBounds":
        return ExtentBounds(
            x_min=min(self.x_min, self.x_max),
            y_min=min(self.y_min, self.y_max),
            x_max=max(self.x_min, self.x_max),
            y_max=max(self.y_min, self.y_max),
        )

    def to_qgs_rectangle(self) -> QgsRectangle:
        return QgsRectangle(
            self.x_min,
            self.y_min,
            self.x_max,
            self.y_max,
        )


class ExtentCalculator:
    _WEB_MERCATOR_EXTENT_LIMIT = 20037508.342789244
    _EXTENT_BUFFER_RATIO = 0.05
    _GEOGRAPHIC_MIN_BUFFER = 0.0001
    _PROJECTED_MIN_BUFFER = 1.0

    @classmethod
    def from_ngw_extent_dict(
        cls,
        response: Mapping[str, Any],
    ) -> Optional[QgsReferencedRectangle]:
        if not isinstance(response, Mapping):
            return None

        extent = response.get("extent", response)
        if not isinstance(extent, Mapping):
            return None

        bounds = cls._bounds_from_values(
            extent.get("minLon"),
            extent.get("minLat"),
            extent.get("maxLon"),
            extent.get("maxLat"),
        )
        if bounds is None:
            return None
        if not cls._is_geographic_bounds(bounds):
            return None

        return QgsReferencedRectangle(
            bounds.to_qgs_rectangle(),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )

    @classmethod
    def from_ngw_extent_tuple(
        cls,
        values: Tuple[float, float, float, float],
    ) -> Optional[QgsReferencedRectangle]:
        try:
            left, right, bottom, top = values
        except (TypeError, ValueError):
            return None

        bounds = cls._bounds_from_values(left, bottom, right, top)
        if bounds is None:
            return None
        if not cls._is_geographic_bounds(bounds):
            return None

        return QgsReferencedRectangle(
            bounds.to_qgs_rectangle(),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )

    @classmethod
    def from_webmap_extent_dict(
        cls,
        values: Mapping[str, Any],
    ) -> Optional[QgsReferencedRectangle]:
        if not isinstance(values, Mapping):
            return None

        bounds = cls._bounds_from_values(
            values.get("extent_left"),
            values.get("extent_bottom"),
            values.get("extent_right"),
            values.get("extent_top"),
        )
        if bounds is None:
            return None
        if not cls._is_geographic_bounds(bounds):
            return None

        return QgsReferencedRectangle(
            bounds.to_qgs_rectangle(),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )

    @classmethod
    def from_qgs_layer(
        cls,
        layer: QgsMapLayer,
    ) -> Optional[QgsReferencedRectangle]:
        if not layer.isValid():
            return None

        return cls.from_qgs_rectangle(layer.extent(), layer.crs())

    @classmethod
    def from_qgs_rectangle(
        cls,
        rectangle: QgsRectangle,
        crs: QgsCoordinateReferenceSystem,
    ) -> Optional[QgsReferencedRectangle]:
        if not crs.isValid():
            return None
        if rectangle.isNull():
            return None

        bounds = cls._bounds_from_values(
            rectangle.xMinimum(),
            rectangle.yMinimum(),
            rectangle.xMaximum(),
            rectangle.yMaximum(),
        )
        if bounds is None:
            return None
        if crs.isGeographic() and not cls._is_geographic_bounds(bounds):
            return None

        return QgsReferencedRectangle(bounds.to_qgs_rectangle(), crs)

    @classmethod
    def from_canvas_extent(
        cls,
        rectangle: QgsRectangle,
        canvas_crs: QgsCoordinateReferenceSystem,
        fallback_crs: Optional[QgsCoordinateReferenceSystem] = None,
    ) -> Optional[QgsReferencedRectangle]:
        extent = cls.from_qgs_rectangle(rectangle, canvas_crs)
        if extent is not None:
            return extent

        if fallback_crs is not None and fallback_crs.isValid():
            extent = cls.from_qgs_rectangle(rectangle, fallback_crs)
            if extent is not None:
                return extent

        if not canvas_crs.isValid() or not canvas_crs.isGeographic():
            return None

        if not cls._looks_like_web_mercator_rectangle(rectangle):
            return None

        return cls.from_qgs_rectangle(
            rectangle,
            QgsCoordinateReferenceSystem.fromEpsgId(3857),
        )

    @classmethod
    def combine(
        cls,
        extents: Iterable[QgsReferencedRectangle],
        target_crs: QgsCoordinateReferenceSystem,
    ) -> Optional[QgsReferencedRectangle]:
        if not target_crs.isValid():
            return None

        result: Optional[ExtentBounds] = None
        for extent in extents:
            transformed_extent = cls.transform(extent, target_crs)
            if transformed_extent is None:
                continue

            bounds = cls._bounds_from_values(
                transformed_extent.xMinimum(),
                transformed_extent.yMinimum(),
                transformed_extent.xMaximum(),
                transformed_extent.yMaximum(),
            )
            if bounds is None:
                continue

            if result is None:
                result = bounds
                continue

            result = ExtentBounds(
                x_min=min(result.x_min, bounds.x_min),
                y_min=min(result.y_min, bounds.y_min),
                x_max=max(result.x_max, bounds.x_max),
                y_max=max(result.y_max, bounds.y_max),
            )

        if result is None:
            return None

        return QgsReferencedRectangle(result.to_qgs_rectangle(), target_crs)

    @classmethod
    def transform(
        cls,
        extent: QgsReferencedRectangle,
        target_crs: QgsCoordinateReferenceSystem,
    ) -> Optional[QgsReferencedRectangle]:
        if not extent.crs().isValid() or not target_crs.isValid():
            return None

        if extent.crs() == target_crs:
            return extent

        transform = QgsCoordinateTransform(
            extent.crs(),
            target_crs,
            QgsProject.instance(),
        )

        try:
            rectangle = transform.transformBoundingBox(
                extent,
                handle180Crossover=target_crs.isGeographic(),
            )
        except QgsCsException:
            return None

        return cls.from_qgs_rectangle(rectangle, target_crs)

    @classmethod
    def buffered(
        cls,
        extent: QgsReferencedRectangle,
    ) -> Optional[QgsReferencedRectangle]:
        crs = extent.crs()
        if not crs.isValid():
            return None

        bounds = cls._bounds_from_values(
            extent.xMinimum(),
            extent.yMinimum(),
            extent.xMaximum(),
            extent.yMaximum(),
        )
        if bounds is None:
            return None

        width = bounds.x_max - bounds.x_min
        height = bounds.y_max - bounds.y_min
        min_buffer = cls._minimum_buffer(crs)
        x_buffer = max(width * cls._EXTENT_BUFFER_RATIO, min_buffer)
        y_buffer = max(height * cls._EXTENT_BUFFER_RATIO, min_buffer)

        buffered_bounds = ExtentBounds(
            x_min=bounds.x_min - x_buffer,
            y_min=bounds.y_min - y_buffer,
            x_max=bounds.x_max + x_buffer,
            y_max=bounds.y_max + y_buffer,
        ).normalized()

        if crs.isGeographic():
            buffered_bounds = cls._clamp_geographic_bounds(buffered_bounds)

        return QgsReferencedRectangle(buffered_bounds.to_qgs_rectangle(), crs)

    @classmethod
    def to_webmap_extent(
        cls,
        extent: QgsReferencedRectangle,
    ) -> Dict[str, float]:
        wgs84_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        transformed_extent = cls.transform(extent, wgs84_crs)
        if transformed_extent is None:
            raise ValueError("Could not transform extent to EPSG:4326")

        bounds = cls._bounds_from_values(
            transformed_extent.xMinimum(),
            transformed_extent.yMinimum(),
            transformed_extent.xMaximum(),
            transformed_extent.yMaximum(),
        )
        if bounds is None or not cls._is_geographic_bounds(bounds):
            raise ValueError("Extent is outside EPSG:4326 bounds")

        return {
            "extent_left": bounds.x_min,
            "extent_bottom": bounds.y_min,
            "extent_right": bounds.x_max,
            "extent_top": bounds.y_max,
        }

    @classmethod
    def default_webmap_extent(cls) -> Dict[str, float]:
        extent = cls.from_ngw_extent_tuple((-180.0, 180.0, -90.0, 90.0))
        if extent is None:
            raise ValueError("Could not create default webmap extent")

        return cls.to_webmap_extent(extent)

    @classmethod
    def _bounds_from_values(
        cls,
        x_min: Any,
        y_min: Any,
        x_max: Any,
        y_max: Any,
    ) -> Optional[ExtentBounds]:
        float_values = []
        for value in (x_min, y_min, x_max, y_max):
            float_value = cls._float_value(value)
            if float_value is None:
                return None
            float_values.append(float_value)

        (
            x_min_value,
            y_min_value,
            x_max_value,
            y_max_value,
        ) = float_values

        bounds = ExtentBounds(
            x_min=x_min_value,
            y_min=y_min_value,
            x_max=x_max_value,
            y_max=y_max_value,
        ).normalized()

        return bounds

    @staticmethod
    def _is_geographic_bounds(bounds: ExtentBounds) -> bool:
        return (
            -180.0 <= bounds.x_min <= 180.0
            and -180.0 <= bounds.x_max <= 180.0
            and -90.0 <= bounds.y_min <= 90.0
            and -90.0 <= bounds.y_max <= 90.0
        )

    @classmethod
    def _clamp_geographic_bounds(cls, bounds: ExtentBounds) -> ExtentBounds:
        return ExtentBounds(
            x_min=max(bounds.x_min, -180.0),
            y_min=max(bounds.y_min, -90.0),
            x_max=min(bounds.x_max, 180.0),
            y_max=min(bounds.y_max, 90.0),
        )

    @classmethod
    def _minimum_buffer(cls, crs: QgsCoordinateReferenceSystem) -> float:
        if crs.isGeographic():
            return cls._GEOGRAPHIC_MIN_BUFFER

        return cls._PROJECTED_MIN_BUFFER

    @classmethod
    def _looks_like_web_mercator_rectangle(
        cls,
        rectangle: QgsRectangle,
    ) -> bool:
        values = (
            rectangle.xMinimum(),
            rectangle.xMaximum(),
            rectangle.yMinimum(),
            rectangle.yMaximum(),
        )
        if any(
            abs(value) > cls._WEB_MERCATOR_EXTENT_LIMIT for value in values
        ):
            return False

        return (
            abs(rectangle.xMinimum()) > 10000.0
            or abs(rectangle.xMaximum()) > 10000.0
            or abs(rectangle.yMinimum()) > 90.0
            or abs(rectangle.yMaximum()) > 90.0
        )

    @staticmethod
    def _float_value(value: Any) -> Optional[float]:
        if isinstance(value, bool):
            return None

        try:
            float_value = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(float_value):
            return None

        return float_value
