"""FanartSlideshowRenderer - artist fanart slideshow element (Item 6).

A positioned art element (like album art / folder image) that shows artist photos
for the playing artist and steps through them. The image set is resolved entirely
server-side by the Node endpoint 'peppy_screensaver_artistfanart' (cascade:
personal artist folder -> fanart/ subfolder -> fanart.tv -> meta.volumio.org),
which returns a list of sectionimage paths. Each image is then loaded over HTTP
from /albumart?sectionimage=<path>, so this works identically for the local
screensaver and remote clients.

Caching: the image set is fetched once per artist change; decoded/scaled surfaces
are cached, never rebuilt per frame. The renderer exposes a backing rect so the
handlers' anti-collision (bgr_surface) clearing works exactly like the other art
elements. Cadence (phase 2): hard cut, advancing one image per track within the
same artist; a cross-fade is a later enhancement.
"""

import io
import json
import urllib.request
import urllib.parse

import pygame as pg


class FanartSlideshowRenderer:
    def __init__(self, pos, dim, scale_mode="fit", cadence="track",
                 volumio_url="http://localhost:3000"):
        self.pos = pos
        self.dim = dim
        self.scale_mode = (scale_mode or "fit").lower()
        self.cadence = (cadence or "track").lower()  # 'track' | 'off'  (timer: later phase)
        self.volumio_url = volumio_url or "http://localhost:3000"

        self._artist_key = "__peppy_init__"
        self._track_key = None
        self._image_refs = []
        self._index = 0
        self._scaled = None
        self._blit_pos = pos
        self._cache = {}            # ref -> (surface, blit_pos)
        self._needs_redraw = True
        self._need_first_blit = False

    @staticmethod
    def _artist_norm(artist):
        return (artist or "").strip().lower()

    def set_volumio_url(self, url):
        if url:
            self.volumio_url = url

    def update_for_track(self, artist, uri):
        """Refresh on artist change; advance one image on track change (per-track cadence).

        Returns True if the displayed image changed.
        """
        a = self._artist_norm(artist)
        if a != self._artist_key:
            self._artist_key = a
            self._track_key = uri
            self._image_refs = []
            self._index = 0
            self._cache = {}
            self._scaled = None
            self._need_first_blit = False
            self._needs_redraw = True
            if a and self.pos and self.dim:
                self._image_refs = self._fetch_list(artist, uri)
                if self._image_refs:
                    self._load_index(0)
            return True
        if uri != self._track_key:
            self._track_key = uri
            if self.cadence == "track" and len(self._image_refs) > 1:
                self._index = (self._index + 1) % len(self._image_refs)
                self._load_index(self._index)
                return True
        return False

    def _fetch_list(self, artist, uri):
        try:
            parsed = urllib.parse.urlparse(self.volumio_url or "http://localhost:3000")
            host = parsed.hostname or "localhost"
            port = parsed.port or 3000
            url = "http://%s:%d/api/v1/pluginEndpoint" % (host, port)
            body = json.dumps({
                "endpoint": "peppy_screensaver_artistfanart",
                "data": {"artist": artist, "uri": uri or ""},
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "PeppyScreensaver/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode())
            if not payload.get("success"):
                return []
            inner = payload.get("data", {})
            if inner.get("success") and isinstance(inner.get("images"), list):
                return inner["images"]
            return []
        except Exception:
            return []

    def _image_url(self, ref):
        parsed = urllib.parse.urlparse(self.volumio_url or "http://localhost:3000")
        host = parsed.hostname or "localhost"
        port = parsed.port or 3000
        return "http://%s:%d/albumart?sectionimage=%s" % (host, port, ref)

    def _fetch_image(self, ref):
        try:
            with urllib.request.urlopen(self._image_url(ref), timeout=8) as r:
                return r.read()
        except Exception:
            return None

    def _load_index(self, i):
        if i < 0 or i >= len(self._image_refs):
            self._scaled = None
            return
        ref = self._image_refs[i]
        if ref in self._cache:
            self._scaled, self._blit_pos = self._cache[ref]
            self._need_first_blit = True
            self._needs_redraw = True
            return
        data = self._fetch_image(ref)
        if data:
            self._build_surface(data, ref)

    def _build_surface(self, img_bytes, ref):
        try:
            surf = pg.image.load(io.BytesIO(img_bytes))
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            tw, th = self.dim
            if self.scale_mode == "stretch":
                scaled = self._scale(surf, (tw, th))
                blit_pos = (self.pos[0], self.pos[1])
            else:  # 'fit': preserve aspect ratio, centre in the box
                sw, sh = surf.get_width(), surf.get_height()
                if sw <= 0 or sh <= 0:
                    return
                ratio = min(tw / float(sw), th / float(sh))
                nw, nh = max(1, int(sw * ratio)), max(1, int(sh * ratio))
                scaled = self._scale(surf, (nw, nh))
                blit_pos = (self.pos[0] + (tw - nw) // 2, self.pos[1] + (th - nh) // 2)
            self._scaled = scaled
            self._blit_pos = blit_pos
            self._cache[ref] = (scaled, blit_pos)
            self._need_first_blit = True
            self._needs_redraw = True
        except Exception:
            self._scaled = None

    @staticmethod
    def _scale(surf, size):
        try:
            return pg.transform.smoothscale(surf, size)
        except Exception:
            return pg.transform.scale(surf, size)

    def get_backing_rect(self):
        if not self.pos or not self.dim:
            return None
        return pg.Rect(self.pos[0], self.pos[1], self.dim[0], self.dim[1])

    def has_image(self):
        return self._scaled is not None

    def render(self, screen):
        if not self._scaled or not self.pos or not self.dim:
            return None
        if not self._needs_redraw and not self._need_first_blit:
            return None
        screen.blit(self._scaled, self._blit_pos)
        self._needs_redraw = False
        self._need_first_blit = False
        return self.get_backing_rect()

    def force_redraw(self):
        self._needs_redraw = True
