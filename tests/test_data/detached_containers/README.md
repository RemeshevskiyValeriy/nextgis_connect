# Detached Container Fixtures

`nextgis_connect_3_6_1_points_layer.gpkg` represents a clean detached
container with the service table schema from NextGIS Connect 3.6.1.

Tests copy this file to a temporary cache path and update connection metadata
there. Keep the fixture itself clean; create dirty scenarios inside tests by
writing to the copied container.
