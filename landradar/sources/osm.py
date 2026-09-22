from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from html.parser import HTMLParser
from urllib.parse import urljoin
from hashlib import sha256
from pathlib import Path
import json

from .base import HttpTransport, RequestsTransport, RawSnapshot, save_raw_snapshot

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
GEOFABRIK_CFD_PAGE = "https://download.geofabrik.de/russia/central-fed-district.html"


class _DownloadLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


@dataclass(frozen=True)
class GeofabrikExtractLinks:
    page_url: str
    pbf_url: str
    gpkg_url: str
    shapefile_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OSMGeofabrikCatalogAdapter:
    source_key = "osm_geofabrik_catalog"

    def __init__(self, transport: HttpTransport | None = None, page_url: str = GEOFABRIK_CFD_PAGE):
        self.transport = transport or RequestsTransport()
        self.page_url = page_url

    @staticmethod
    def parse_links(html: str, page_url: str) -> GeofabrikExtractLinks:
        parser = _DownloadLinkParser()
        parser.feed(html)
        hrefs = parser.hrefs

        def pick(suffix: str) -> str:
            candidates = [h for h in hrefs if h.endswith(suffix)]
            if not candidates:
                raise ValueError(f"Geofabrik catalog missing {suffix}")
            candidates.sort(key=lambda h: ("latest" not in h, len(h), h))
            return urljoin(page_url, candidates[0])

        shp = [h for h in hrefs if h.endswith("latest-free.shp.zip")]
        return GeofabrikExtractLinks(
            page_url=page_url,
            pbf_url=pick("latest.osm.pbf"),
            gpkg_url=pick("latest-free.gpkg.zip"),
            shapefile_url=urljoin(page_url, shp[0]) if shp else None,
        )

    def fetch_catalog(self, *, raw_dir: str, timeout: float = 30.0) -> tuple[GeofabrikExtractLinks, RawSnapshot]:
        response = self.transport.get(self.page_url, headers={"Accept": "text/html"}, timeout=timeout)
        if response.status_code != 200:
            raise RuntimeError(f"Geofabrik catalog HTTP {response.status_code}: {response.text[:300]}")
        snapshot = save_raw_snapshot(
            source_key=self.source_key,
            method="GET",
            response=response,
            raw_dir=raw_dir,
            suffix="html",
        )
        links = self.parse_links(response.text, response.url)
        return links, snapshot

    def healthcheck(self, *, raw_dir: str, timeout: float = 30.0) -> dict[str, Any]:
        try:
            links, snapshot = self.fetch_catalog(raw_dir=raw_dir, timeout=timeout)
            return {"source": self.source_key, "ok": True, "links": links.to_dict(), "snapshot": snapshot.to_dict()}
        except Exception as exc:
            return {"source": self.source_key, "ok": False, "error_type": type(exc).__name__, "error": str(exc)}


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float

    def validate(self) -> None:
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError("Invalid latitude bounds")
        if not (-180 <= self.west < self.east <= 180):
            raise ValueError("Invalid longitude bounds")


@dataclass
class OSMRoad:
    osm_type: str
    osm_id: int
    highway: str
    name: str | None
    surface: str | None
    access: str | None
    geometry: list[dict[str, float]]
    tags: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OSMOverpassAdapter:
    source_key = "osm_overpass"

    def __init__(self, transport: HttpTransport | None = None, endpoint: str = OVERPASS_ENDPOINT):
        self.transport = transport or RequestsTransport()
        self.endpoint = endpoint

    @staticmethod
    def roads_query(bbox: BBox) -> str:
        bbox.validate()
        b = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
        return (
            "[out:json][timeout:25];\n"
            "(\n"
            f'  way["highway"]({b});\n'
            ");\n"
            "out tags geom;"
        )

    def fetch_roads(self, bbox: BBox, *, raw_dir: str, timeout: float = 35.0) -> tuple[list[OSMRoad], RawSnapshot]:
        query = self.roads_query(bbox)
        response = self.transport.post(
            self.endpoint,
            data={"data": query},
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"OSM Overpass HTTP {response.status_code}: {response.text[:300]}")
        snapshot = save_raw_snapshot(
            source_key=self.source_key,
            method="POST",
            response=response,
            raw_dir=raw_dir,
            suffix="json",
            request_payload=query,
        )
        return self.parse_roads(response.content), snapshot

    @staticmethod
    def parse_roads(payload: bytes | str) -> list[OSMRoad]:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload)
        elements = data.get("elements")
        if not isinstance(elements, list):
            raise ValueError("Overpass response missing 'elements' list")
        roads: list[OSMRoad] = []
        for element in elements:
            if element.get("type") != "way":
                continue
            tags = element.get("tags") or {}
            highway = tags.get("highway")
            geometry = element.get("geometry") or []
            if not highway or not isinstance(geometry, list):
                continue
            cleaned_geometry: list[dict[str, float]] = []
            for p in geometry:
                if isinstance(p, dict) and "lat" in p and "lon" in p:
                    cleaned_geometry.append({"lat": float(p["lat"]), "lon": float(p["lon"])})
            roads.append(OSMRoad(
                osm_type="way",
                osm_id=int(element["id"]),
                highway=str(highway),
                name=tags.get("name"),
                surface=tags.get("surface"),
                access=tags.get("access"),
                geometry=cleaned_geometry,
                tags={str(k): str(v) for k, v in tags.items()},
            ))
        return roads

    def healthcheck(self, *, raw_dir: str, timeout: float = 20.0) -> dict[str, Any]:
        bbox = BBox(54.5030, 36.2400, 54.5050, 36.2440)
        try:
            roads, snapshot = self.fetch_roads(bbox, raw_dir=raw_dir, timeout=timeout)
            return {
                "source": self.source_key,
                "ok": True,
                "records": len(roads),
                "snapshot": snapshot.to_dict(),
                "note": "Public Overpass is low-volume only; bulk ingestion uses Geofabrik.",
            }
        except Exception as exc:
            return {"source": self.source_key, "ok": False, "error_type": type(exc).__name__, "error": str(exc)}


class OSMGeofabrikGpkgAdapter:
    source_key = "osm_geofabrik_gpkg"

    def __init__(self, gpkg_path: str):
        self.gpkg_path = gpkg_path

    def list_layers(self) -> list[str]:
        import pyogrio
        return [str(row[0]) for row in pyogrio.list_layers(self.gpkg_path)]

    def find_road_layer(self) -> str:
        layers = self.list_layers()
        candidates = [name for name in layers if "road" in name.casefold()]
        if not candidates:
            raise ValueError(f"No road layer found in GeoPackage; layers={layers}")
        preferred = [n for n in candidates if n.casefold() in {"roads", "gis_osm_roads_free_1", "osm_roads"}]
        return preferred[0] if preferred else sorted(candidates, key=len)[0]

    def read_roads(self, bbox: BBox):
        bbox.validate()
        import geopandas as gpd
        layer = self.find_road_layer()
        gdf = gpd.read_file(
            self.gpkg_path,
            layer=layer,
            bbox=(bbox.west, bbox.south, bbox.east, bbox.north),
            engine="pyogrio",
        )
        if gdf.crs is None:
            raise ValueError("OSM GeoPackage road layer has no CRS")
        epsg = gdf.crs.to_epsg()
        if epsg != 4326:
            raise ValueError(f"Unexpected OSM GeoPackage CRS: {gdf.crs}; expected EPSG:4326")
        return gdf

    def file_manifest(self, *, compute_sha256: bool = True) -> dict[str, Any]:
        path = Path(self.gpkg_path)
        stat = path.stat()
        digest = None
        if compute_sha256:
            h = sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h.update(chunk)
            digest = h.hexdigest()
        return {"path": str(path), "byte_count": stat.st_size, "sha256": digest}

    def healthcheck(self, bbox: BBox) -> dict[str, Any]:
        try:
            roads = self.read_roads(bbox)
            return {
                "source": self.source_key,
                "ok": True,
                "file": self.gpkg_path,
                "road_layer": self.find_road_layer(),
                "records": int(len(roads)),
                "crs": str(roads.crs),
                "file_manifest": self.file_manifest(compute_sha256=False),
            }
        except Exception as exc:
            return {
                "source": self.source_key,
                "ok": False,
                "file": self.gpkg_path,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
