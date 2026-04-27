from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage,
    QWebEngineScript, QWebEngineSettings,
)
from PyQt6.QtCore import QUrl, QRect, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QTransform

from ui.snip_overlay import SnipOverlay

HOME_URL = "https://www.google.com"

_STEALTH_JS = """
(function () {
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined, configurable: true,
    });
    try { delete navigator.__proto__.webdriver; } catch (_) {}

    const _plugins = [
        { name: 'PDF Viewer',        filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
        { name: 'Native Client',     filename: 'internal-nacl-plugin' },
    ];
    Object.defineProperty(navigator, 'plugins',   { get: () => _plugins });
    Object.defineProperty(navigator, 'mimeTypes', { get: () => []       });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-GB', 'en-US', 'en'],
    });

    if (!window.chrome) {
        window.chrome = {
            runtime: {}, app: {},
            csi: function(){}, loadTimes: function(){},
        };
    }

    if (navigator.permissions && navigator.permissions.query) {
        const _orig = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (p) => {
            if (p && p.name === 'notifications')
                return Promise.resolve({ state: Notification.permission });
            return _orig(p);
        };
    }
})();
"""

# Use palette roles so arrows are legible on any system theme (light or dark)
_NAV_BTN_STYLE = """
    QPushButton {
        font-size: 16px;
        font-weight: bold;
        color: palette(buttonText);
        background: palette(button);
        border: 1px solid palette(mid);
        border-radius: 4px;
        padding: 0px 4px 2px 4px;
    }
    QPushButton:hover    { background: palette(light); }
    QPushButton:pressed  { background: palette(dark);  }
    QPushButton:disabled { color: palette(mid); border-color: palette(shadow); }
"""


def _make_profile() -> QWebEngineProfile:
    profile = QWebEngineProfile("SnipZaic")
    profile.setHttpUserAgent(
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    profile.setHttpAcceptLanguage("en-GB,en-US;q=0.9,en;q=0.8")
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)

    s = profile.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

    script = QWebEngineScript()
    script.setName("snipzaic_stealth")
    script.setSourceCode(_STEALTH_JS)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    profile.scripts().insert(script)
    return profile


class BrowserPanel(QWidget):
    # pixmap, outline_path (QPainterPath|None), cut_center in central-widget coords
    snip_ready = pyqtSignal(QPixmap, object, QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── nav bar ────────────────────────────────────────────────────────
        self._nav_bar = QWidget()
        self._nav_bar.setFixedHeight(36)
        nav_row = QHBoxLayout(self._nav_bar)
        nav_row.setContentsMargins(6, 3, 6, 3)
        nav_row.setSpacing(4)

        self._back_btn = QPushButton("←")
        self._back_btn.setFixedSize(30, 28)
        self._back_btn.setToolTip("Go back")
        self._back_btn.setStyleSheet(_NAV_BTN_STYLE)
        # NoFocus keeps keyboard focus in the browser so Enter/typing still works
        self._back_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._fwd_btn = QPushButton("→")
        self._fwd_btn.setFixedSize(30, 28)
        self._fwd_btn.setToolTip("Go forward")
        self._fwd_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._fwd_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        nav_row.addWidget(self._back_btn)
        nav_row.addWidget(self._fwd_btn)
        nav_row.addStretch()
        outer.addWidget(self._nav_bar)

        # ── browser ────────────────────────────────────────────────────────
        self._profile = _make_profile()
        page = QWebEnginePage(self._profile, self)

        self.browser = QWebEngineView()
        self.browser.setPage(page)
        self.browser.setUrl(QUrl(HOME_URL))
        sp = self.browser.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.browser.setSizePolicy(sp)
        outer.addWidget(self.browser, stretch=1)

        self._back_btn.clicked.connect(lambda: self.browser.back())
        self._fwd_btn.clicked.connect(lambda: self.browser.forward())
        self.browser.urlChanged.connect(self._update_nav)
        self.browser.loadFinished.connect(lambda _: self._update_nav())
        self._update_nav()

        # ── snip overlay ───────────────────────────────────────────────────
        # Parented to self so it can cover the browser area independently of
        # the layout — positioned manually in _arm().
        self._overlay = SnipOverlay(self)
        self._overlay.region_selected.connect(self._on_region_selected)
        self._overlay.path_selected.connect(self._on_path_selected)
        self._overlay.cancelled.connect(self._on_cancelled)

        self._active_tool: str = ""
        self._snapshot: QPixmap | None = None

    def _update_nav(self):
        h = self.browser.history()
        self._back_btn.setEnabled(h.canGoBack())
        self._fwd_btn.setEnabled(h.canGoForward())

    # --- tool activation ---

    _SNIP_TOOLS = ("rect_snip", "poly_snip", "free_snip")

    def set_active_tool(self, tool: str):
        self._active_tool = tool
        if tool in self._SNIP_TOOLS:
            self._arm()
        else:
            self._overlay.hide()
            self.browser.show()

    def _arm(self):
        if self._active_tool not in self._SNIP_TOOLS:
            return
        # Always restore browser before grabbing — handles tool switching mid-snip
        self._overlay.hide()
        self.browser.show()
        self._snapshot = self.browser.grab()
        if self._snapshot.isNull():
            return
        self.browser.hide()
        self._overlay.setGeometry(self.browser.geometry())
        self._overlay.activate(self._snapshot, self._active_tool)

    # --- overlay signals ---

    def _on_region_selected(self, rect: QRect):
        ow, oh = self._overlay.width(), self._overlay.height()
        if self._snapshot and not self._snapshot.isNull() and ow > 0 and oh > 0:
            dpr_x = self._snapshot.width()  / ow
            dpr_y = self._snapshot.height() / oh
            scaled = QRect(
                int(rect.x() * dpr_x), int(rect.y() * dpr_y),
                int(rect.width() * dpr_x), int(rect.height() * dpr_y),
            )
            cropped = self._snapshot.copy(scaled)
            cropped.setDevicePixelRatio(1.0)
            cut_center = self._cut_center_in_central(QPointF(rect.center()))
            self.snip_ready.emit(cropped, None, cut_center)
        # Exit freeze-frame so the drag overlay can take over
        self._overlay.hide()
        self.browser.show()

    def _on_path_selected(self, path: QPainterPath):
        ow, oh = self._overlay.width(), self._overlay.height()
        if self._snapshot and not self._snapshot.isNull() and ow > 0 and oh > 0:
            dpr_x = self._snapshot.width() / ow
            dpr_y = self._snapshot.height() / oh
            transform = QTransform().scale(dpr_x, dpr_y)
            scaled_path = transform.map(path)

            br = scaled_path.boundingRect().toAlignedRect().intersected(
                self._snapshot.rect()
            )
            if br.width() > 5 and br.height() > 5:
                result = QPixmap(br.size())
                result.fill(Qt.GlobalColor.transparent)
                p = QPainter(result)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                local_path = scaled_path.translated(-br.x(), -br.y())
                p.setClipPath(local_path)
                p.drawPixmap(0, 0, self._snapshot, br.x(), br.y(), br.width(), br.height())
                p.end()
                result.setDevicePixelRatio(1.0)
                # Normalize the outline path to 0..1 of the snip rect
                nt = QTransform().scale(1.0 / br.width(), 1.0 / br.height())
                outline = nt.map(local_path)
                cut_center = self._cut_center_in_central(path.boundingRect().center())
                self.snip_ready.emit(result, outline, cut_center)
        # Exit freeze-frame so the drag overlay can take over
        self._overlay.hide()
        self.browser.show()

    def _cut_center_in_central(self, overlay_pos: QPointF) -> QPointF:
        """Convert a point in overlay-local coords to central-widget coords."""
        central = self.window().centralWidget()
        return QPointF(self._overlay.mapTo(central, overlay_pos.toPoint()))

    def _on_cancelled(self):
        self.browser.show()

    def rearm(self):
        """Re-freeze the browser for another snip (called after a drag is placed)."""
        if self._active_tool in self._SNIP_TOOLS:
            self._arm()
