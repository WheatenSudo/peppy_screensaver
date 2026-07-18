"""FolderImageRenderer - extra decorative layer sourced from the playing track's folder.

Item 5: shows a scaled image (e.g. back.png / logo.png) taken from the folder of the
currently playing track. The image bytes are fetched from the Node plugin endpoint
'peppy_screensaver_folderimage' (which resolves and sandboxes the path under /mnt on the
device), so this works for both the local screensaver and remote clients. Non-file
sources (Spotify, webradio, ...) resolve to a non-existent path server-side and simply
yield no image.

The renderer mirrors the proven AlbumArtRenderer layering: it caches per track-folder
change (never per frame) and exposes a backing rect for the handlers' anti-collision
(bgr_surface) clearing. Z-order is decided by the handler:
  - 'background': drawn before the meters (like album art), cleared against bgr_surface.
  - 'overlay':    stamped on top each time something underneath changes, below the
                  foreground mask.
"""

import io
import sys
import json
import base64
import urllib.request

import pygame as pg

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

DEFAULT_FOLDER_FILES = [
    "back.png", "Back.png", "back.jpg", "Back.jpg", "logo.png", "Logo.png",
]


def _decode_surface_bounded(img_bytes, box, want_alpha=True):
    """Decode image bytes to a pygame Surface with peak memory bounded to ~box.

    Folder images (back cover, logo) are user-supplied at arbitrary resolution.
    The screensaver runs under a tight RLIMIT_AS, where a full-resolution decode
    of a large source can exceed the cap and fail (silently). PIL.Image.draft()
    decodes JPEG at 1/2, 1/4 or 1/8 scale (no-op for PNG/others), and thumbnail()
    bounds the bitmap to the display box before it becomes a pygame Surface. Falls
    back to pygame's own loader when PIL is unavailable or errors.
    """
    if PIL_AVAILABLE and box:
        try:
            bw = max(1, int(box[0]))
            bh = max(1, int(box[1]))
            im = Image.open(io.BytesIO(img_bytes))
            try:
                im.draft(None, (bw, bh))  # JPEG fast-path; harmless otherwise
            except Exception:
                pass
            mode = "RGBA" if want_alpha else "RGB"
            im = im.convert(mode)
            im.thumbnail((bw, bh))        # only shrinks; preserves aspect ratio
            frombytes = getattr(pg.image, "frombytes", None) or pg.image.fromstring
            return frombytes(im.tobytes(), im.size, mode)
        except Exception as exc:
            sys.stderr.write("[peppy] bounded image decode failed, "
                             "falling back to pygame: %s\n" % exc)
    return pg.image.load(io.BytesIO(img_bytes))


class FolderImageRenderer:
    def __init__(self, pos, dim, scale_mode="fit", filenames=None,
                 volumio_url="http://localhost:3000",
                 border_width=0, border_color=(255, 255, 255)):
        self.pos = pos
        self.dim = dim
        self.scale_mode = (scale_mode or "fit").lower()
        self.filenames = filenames or list(DEFAULT_FOLDER_FILES)
        self.volumio_url = volumio_url or "http://localhost:3000"
        self.border_width = max(0, int(border_width or 0))
        self.border_color = border_color or (255, 255, 255)

        # Sentinel so the first real track key always triggers a load attempt
        self._current_key = "__peppy_init__"
        self._scaled_surf = None
        self._blit_pos = pos
        self._needs_redraw = True
        self._need_first_blit = False

    @staticmethod
    def track_folder_key(uri):
        """Folder portion of the track uri; the cache key. None for empty uris."""
        if not uri:
            return None
        slash = uri.rfind("/")
        return uri[:slash] if slash != -1 else uri

    def set_volumio_url(self, url):
        if url:
            self.volumio_url = url

    def update_for_track(self, uri):
        """Refresh the cached image when the track folder changed. Returns True on change."""
        key = self.track_folder_key(uri)
        if key == self._current_key:
            return False
        self._current_key = key
        self._scaled_surf = None
        self._need_first_blit = False
        self._needs_redraw = True
        if uri and self.pos and self.dim:
            data = self._fetch(uri)
            if data:
                self._build_surface(data)
        return True

    def _fetch(self, uri):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.volumio_url or "http://localhost:3000")
            host = parsed.hostname or "localhost"
            port = parsed.port or 3000
            url = "http://%s:%d/api/v1/pluginEndpoint" % (host, port)
            body = json.dumps({
                "endpoint": "peppy_screensaver_folderimage",
                "data": {"uri": uri, "filenames": self.filenames},
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "PeppyScreensaver/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode())
            if not payload.get("success"):
                return None
            inner = payload.get("data", {})
            if inner.get("success") and inner.get("data"):
                return base64.b64decode(inner["data"])
            return None
        except Exception:
            return None

    def _build_surface(self, img_bytes):
        try:
            # Memory-bounded decode: large folder images would otherwise exceed the
            # screensaver's RLIMIT_AS during full decode and silently fail to show.
            surf = _decode_surface_bounded(img_bytes, self.dim, want_alpha=True)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            tw, th = self.dim
            if self.scale_mode == "stretch":
                self._scaled_surf = self._scale(surf, (tw, th))
                self._blit_pos = (self.pos[0], self.pos[1])
            else:  # 'fit': preserve aspect ratio, centre within the box
                sw, sh = surf.get_width(), surf.get_height()
                if sw <= 0 or sh <= 0:
                    return
                ratio = min(tw / float(sw), th / float(sh))
                nw, nh = max(1, int(sw * ratio)), max(1, int(sh * ratio))
                self._scaled_surf = self._scale(surf, (nw, nh))
                self._blit_pos = (self.pos[0] + (tw - nw) // 2,
                                  self.pos[1] + (th - nh) // 2)
            self._need_first_blit = True
        except Exception as exc:
            sys.stderr.write("[peppy] folderimage _build_surface failed: %s\n" % exc)
            self._scaled_surf = None

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
        return self._scaled_surf is not None

    def render(self, screen):
        """Blit the cached image; returns the dirty rect, or None if nothing to draw."""
        if not self._scaled_surf or not self.pos or not self.dim:
            return None
        if not self._needs_redraw and not self._need_first_blit:
            return None
        screen.blit(self._scaled_surf, self._blit_pos)
        # Optional border frames the configured box (same model as albumart.border)
        if self.border_width > 0:
            try:
                pg.draw.rect(
                    screen, self.border_color,
                    pg.Rect(self.pos[0], self.pos[1], self.dim[0], self.dim[1]),
                    self.border_width,
                )
            except Exception:
                pass
        self._needs_redraw = False
        self._need_first_blit = False
        return self.get_backing_rect()

    def force_redraw(self):
        self._needs_redraw = True
