# filepath: c:\Users\pscullion\OneDrive - Harpur Trust (Bedford School)\5_Code\Git\Bedford-Range-FeedbackScreen\Beds_StatusScreen.py

import pygame
import sys
import math
import time
import socket
import threading
import subprocess
from collections import deque
from datetime import datetime

# ---------------------------------------------------------------------------
# Colour palette – futuristic neon-on-dark theme
# ---------------------------------------------------------------------------
COL_BG            = (10,  12,  18)       # 10,12,18 very dark blue-black background
COL_RING_OUTER    = (0,   220, 255)      # cyan glow
COL_RING_INNER    = (20,  30,  50)          ##20,30,50
COL_TICK_MAJOR    = (0,   220, 255)
COL_TICK_MINOR    = (40,  70,  100)
COL_NUMBER        = (180, 220, 255)
COL_HOUR_HAND     = (255, 255, 255)
COL_MINUTE_HAND   = (0,   200, 240)
COL_SECOND_HAND   = (255, 60,  80)       # red-orange accent
COL_CENTRE_DOT    = (255, 255, 255)
COL_DIGITAL       = (0,   220, 255)
COL_DATE          = (100, 140, 170)
COL_GLOW          = (0,   180, 220)
COL_PANEL_BG      = (18,  22,  32)
COL_PANEL_BORDER  = (0,   220, 255, 100)  # cyan, semi-transparent
COL_PANEL_LABEL   = (140, 180, 210)
COL_STATUS_OFF    = (140, 20,  20)        # red  – device offline
COL_STATUS_ACK    = (20,  120, 40)        # green – device acknowledged
COL_STATUS_AUT    = (10,  12,  55)        # Bedford School blue  – device in automatic mode
LISTEN_PORT       = 5001

# ---------------------------------------------------------------------------
# Animation / easing helpers
# ---------------------------------------------------------------------------
INTRO_DURATION = 1.5 # seconds per phase (sweep-up / sweep-down)
SNAP_START_ANGLE = 210.0      # roughly 7 o'clock
SNAP_END_ANGLE   = 150.0      # roughly 5 o'clock (via clockwise sweep)
SNAP_HOLD_TIME   = 0.5        # hold fully-drawn ring before reversing
SNAP_RETURN_TIME = 2.0        # anti-clockwise return duration
SNAP_RING_OFFSET = 10         # ring starts this many pixels outside face ring
SNAP_RING_THICK  = 10         # radial thickness in pixels

SNAP_COL_INNER = (90, 0, 0)       # dark red near clock face
SNAP_COL_OUTER = (255, 90, 90)    # brighter outer red
SNAP_COL_GLOW  = (255, 170, 170)  # soft outer glow
RAPID_TIMER_BOX = (14, 18, 28)
RAPID_TIMER_TEXT = (120, 240, 255)
RAPID_TIMER_GLOW = (0, 220, 255)
LOGO_HOLD_TIME = 10.0
LOGO_FADE_TIME = 2.0
CORNER_LOGO_FADE_TIME = 2.0
IP_LABEL_HOLD_TIME = 30.0
IP_LABEL_FADE_OUT_TIME = 1.0
SHUTDOWN_LOGO_HOLD_TIME = 5.0
SHUTDOWN_LOGO_FADE_TIME = 5.0
SHUTDOWN_MESSAGE_TIME = 3.0


def ease_in_out_cubic(t):
    """Smooth ease-in-out curve, t in [0,1] -> [0,1]."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - (-2 * t + 2) ** 3 / 2


def lerp_angle(a, b, t):
    """Interpolate from angle a to b (degrees, 0-360) via the shortest arc."""
    diff = (b - a) % 360
    if diff > 180:
        diff -= 360
    return (a + diff * t) % 360


def lerp_clockwise(a, b, t):
    """Interpolate angle a -> b moving clockwise in clock-angle space."""
    diff = (b - a) % 360
    return (a + diff * t) % 360


def lerp_anticlockwise(a, b, t):
    """Interpolate angle a -> b moving anti-clockwise in clock-angle space."""
    diff = (a - b) % 360
    return (a - diff * t) % 360


def lerp_colour(c1, c2, t):
    """Linear interpolation between two RGB colours."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def aa_filled_circle(surface, cx, cy, radius, colour):
    """Anti-aliased filled circle via gfxdraw."""
    try:
        import pygame.gfxdraw
        pygame.gfxdraw.aacircle(surface, int(cx), int(cy), int(radius), colour)
        pygame.gfxdraw.filled_circle(surface, int(cx), int(cy), int(radius), colour)
    except ImportError:
        pygame.draw.circle(surface, colour, (int(cx), int(cy)), int(radius))


def thick_aa_line(surface, start, end, colour, thickness):
    """Draw a thick anti-aliased line as a polygon."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    px = -dy / length * thickness / 2
    py =  dx / length * thickness / 2
    points = [
        (start[0] + px, start[1] + py),
        (start[0] - px, start[1] - py),
        (end[0]   - px, end[1]   - py),
        (end[0]   + px, end[1]   + py),
    ]
    pygame.draw.polygon(surface, colour, points)
    pygame.draw.aalines(surface, colour, True, points)


def polar_to_cart(cx, cy, angle_deg, radius):
    """Convert clock-angle (0° = 12 o'clock, CW) to Cartesian."""
    rad = math.radians(angle_deg - 90)
    return (cx + radius * math.cos(rad),
            cy + radius * math.sin(rad))


def draw_clock_arc(surface, colour, cx, cy, radius, start_angle, end_angle):
    """Draw a 1px arc in clock-angle coordinates, moving clockwise."""
    span = (end_angle - start_angle) % 360
    if span <= 0.05:
        return

    steps = max(24, int(span * 2.5))
    points = [
        polar_to_cart(cx, cy, start_angle + span * (i / steps), radius)
        for i in range(steps + 1)
    ]
    pygame.draw.lines(surface, colour, False, points, 1)


def draw_snap_ring(surface, screen_w, screen_h, cx, cy, clock_radius,
                   start_angle, end_angle):
    """Draw the animated SNAP ring with outward red gradient and glow."""
    ring = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    inner_r = clock_radius + SNAP_RING_OFFSET

    for i in range(SNAP_RING_THICK):
        t = i / max(1, SNAP_RING_THICK - 1)
        rgb = lerp_colour(SNAP_COL_INNER, SNAP_COL_OUTER, t)
        alpha = int(165 + 80 * t)
        draw_clock_arc(ring, (rgb[0], rgb[1], rgb[2], alpha),
                       cx, cy, inner_r + i, start_angle, end_angle)

    # Soft glow halo beyond the ring edge.
    glow_layers = 6
    for g in range(glow_layers):
        t = g / max(1, glow_layers - 1)
        alpha = int(80 * (1.0 - t))
        draw_clock_arc(ring, (SNAP_COL_GLOW[0], SNAP_COL_GLOW[1], SNAP_COL_GLOW[2], alpha),
                       cx, cy, inner_r + SNAP_RING_THICK + g,
                       start_angle, end_angle)

    surface.blit(ring, (0, 0))


def fit_font_to_rect(font_name, text, rect_w, rect_h, bold=False):
    """Return the largest font that fits *text* inside the given rectangle."""
    best_font = pygame.font.SysFont(font_name, 12, bold=bold)
    lo = 12
    hi = max(lo, rect_h)

    while lo <= hi:
        mid = (lo + hi) // 2
        font = pygame.font.SysFont(font_name, mid, bold=bold)
        text_w, text_h = font.size(text)
        if text_w <= rect_w and text_h <= rect_h:
            best_font = font
            lo = mid + 1
        else:
            hi = mid - 1

    return best_font


def draw_rapid_timer(surface, rect, timer_text):
    """Draw the large RAPID mode timer in the space to the right of the clock."""
    timer_box = pygame.Rect(rect)
    timer_box.inflate_ip(-24, -24)

    font = fit_font_to_rect("Consolas", "88:88", timer_box.width, timer_box.height, bold=True)
    text = font.render(timer_text, True, RAPID_TIMER_TEXT)
    text_rect = text.get_rect(center=timer_box.center)

    bg = pygame.Surface((timer_box.width, timer_box.height), pygame.SRCALPHA)
    pygame.draw.rect(bg, (*RAPID_TIMER_BOX, 210), bg.get_rect(), border_radius=16)
    pygame.draw.rect(bg, (*RAPID_TIMER_GLOW, 120), bg.get_rect(), 2, border_radius=16)
    surface.blit(bg, timer_box.topleft)

    glow = font.render(timer_text, True, RAPID_TIMER_GLOW)
    glow.set_alpha(70)
    surface.blit(glow, glow.get_rect(center=timer_box.center))
    surface.blit(text, text_rect)


def run_startup_logo_sequence(screen, fps_clock, screen_w, screen_h):
    """Show full-screen Bedford logo, then fade to black before main intro."""
    logo = None
    for path in ("Bedford-logo.jp", "bedford-logo.jp", "Bedford-logo.jpg", "bedford-logo.jpg"):
        try:
            logo = pygame.image.load(path).convert()
            break
        except (pygame.error, FileNotFoundError):
            continue

    if logo is None:
        return True

    logo = pygame.transform.smoothscale(logo, (screen_w, screen_h))
    fade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    start = time.time()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False

        elapsed = time.time() - start
        screen.blit(logo, (0, 0))

        if elapsed >= LOGO_HOLD_TIME:
            fade_t = min((elapsed - LOGO_HOLD_TIME) / LOGO_FADE_TIME, 1.0)
            fade.fill((0, 0, 0, int(255 * fade_t)))
            screen.blit(fade, (0, 0))

        pygame.display.flip()
        fps_clock.tick(60)

        if elapsed >= LOGO_HOLD_TIME + LOGO_FADE_TIME:
            break

    return True


def load_scaled_corner_logo(max_w, max_h):
    """Load and scale the top-left logo to fit inside max_w x max_h."""
    try:
        logo = pygame.image.load("bedford-logo-small.jpg").convert_alpha()
    except (pygame.error, FileNotFoundError):
        return None

    src_w, src_h = logo.get_size()
    if src_w <= 0 or src_h <= 0:
        return None

    scale = min(max_w / src_w, max_h / src_h)
    if scale <= 0:
        return None

    out_w = max(1, int(src_w * scale))
    out_h = max(1, int(src_h * scale))
    return pygame.transform.smoothscale(logo, (out_w, out_h))


def wrap_text(text, font, max_width):
    """Split *text* into lines that each fit within *max_width* pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_panel(surface, rect, label, font, border_col=COL_PANEL_BORDER,
               bg_col=COL_PANEL_BG, label_col=COL_PANEL_LABEL):
    """Draw a single status panel with a word-wrapped label centred inside."""
    # Background
    pygame.draw.rect(surface, bg_col, rect, border_radius=6)
    # Border (needs opaque colour for draw.rect, alpha handled via surface)
    border_rgb = border_col[:3] if len(border_col) == 4 else border_col
    pygame.draw.rect(surface, border_rgb, rect, 1, border_radius=6)

    # Word-wrap the label to fit inside the panel with some padding
    pad = 8
    lines = wrap_text(label, font, rect.width - pad * 2)
    total_h = len(lines) * font.get_linesize()
    start_y = rect.centery - total_h // 2
    for i, line in enumerate(lines):
        txt = font.render(line, True, label_col)
        txt_rect = txt.get_rect(center=(rect.centerx,
                                        start_y + i * font.get_linesize()
                                        + font.get_linesize() // 2))
        surface.blit(txt, txt_rect)


# ---------------------------------------------------------------------------
# Network listener – receives device status updates on LISTEN_PORT
# ---------------------------------------------------------------------------
# Shared state: 14 entries, one per panel.
# Each entry is a dict  {"status": "OFF"|"ACK"|"AUT", "extra": "..."}
# The mapping from index to panel is:
#   0-5  → Lane Controller 1-6   (top row cols 0-5)
#   6-11 → Snap Target 1-6       (bottom row cols 0-5)
#   12   → Foyer Display         (top row col 6)
#   13   → Range Display         (bottom row col 6)
# ---------------------------------------------------------------------------
panel_statuses = [{"status": "OFF", "extra": ""} for _ in range(14)]
lane_scores    = [0] * 6          # cumulative score per lane controller (indices 0-5)
_status_lock   = threading.Lock()
_score_queue = deque()
_snap_lock = threading.Lock()
_pending_snap_seconds = None
_rapid_lock = threading.Lock()
_pending_rapid_mode = None
_reset_lock = threading.Lock()
_pending_reset = False
_shutdown_lock = threading.Lock()
_pending_shutdown = False


def _set_pending_snap(seconds):
    """Store the latest SNAP duration request from the network thread."""
    global _pending_snap_seconds
    with _snap_lock:
        _pending_snap_seconds = seconds


def _consume_pending_snap():
    """Fetch and clear any queued SNAP duration request."""
    global _pending_snap_seconds
    with _snap_lock:
        seconds = _pending_snap_seconds
        _pending_snap_seconds = None
    return seconds


def _set_pending_rapid_mode(mode):
    """Store the latest RAPID mode request from the network thread."""
    global _pending_rapid_mode
    with _rapid_lock:
        _pending_rapid_mode = mode


def _consume_pending_rapid_mode():
    """Fetch and clear any queued RAPID mode request."""
    global _pending_rapid_mode
    with _rapid_lock:
        mode = _pending_rapid_mode
        _pending_rapid_mode = None
    return mode


def _set_pending_reset():
    """Queue a RESET request from the network thread."""
    global _pending_reset
    with _reset_lock:
        _pending_reset = True


def _consume_pending_reset():
    """Fetch and clear any queued RESET request."""
    global _pending_reset
    with _reset_lock:
        pending = _pending_reset
        _pending_reset = False
    return pending


def _set_pending_shutdown():
    """Queue a SHUTDOWN request from the network thread."""
    global _pending_shutdown
    with _shutdown_lock:
        _pending_shutdown = True


def _consume_pending_shutdown():
    """Fetch and clear any queued SHUTDOWN request."""
    global _pending_shutdown
    with _shutdown_lock:
        pending = _pending_shutdown
        _pending_shutdown = False
    return pending


def _parse_status_update(message):
    """Parse one status update in the form 'STATUS:index[:extra]'."""
    raw = message.strip()
    if not raw:
        return None

    # Accept optional wrapper punctuation in case upstream sends tuple-like text.
    raw = raw.strip("()[]{}")

    parts = [p.strip() for p in raw.split(":")]
    if len(parts) < 2:
        return None

    status = parts[0].upper()
    if status not in {"OFF", "ACK", "AUT"}:
        return None

    try:
        index = int(parts[1])
    except ValueError:
        return None

    if index < 0 or index >= len(panel_statuses):
        return None

    extra = ":".join(parts[2:]).strip() if len(parts) > 2 else ""
    return status, index, extra


def _parse_snap_command(message):
    """Parse SNAP command in the form 'SNAP[:numberOfSeconds]' or 'SNAPS'."""
    raw = message.strip()
    if not raw:
        return None

    raw = raw.strip("()[]{}")

    parts = [p.strip() for p in raw.split(":", 1)]
    command = parts[0].upper()
    if command not in {"SNAP", "SNAPS"}:
        return None

    if len(parts) == 1:
        return 1.0

    if len(parts) != 2:
        return None

    try:
        duration = float(parts[1])
    except ValueError:
        return None

    if duration <= 0:
        return None
    return duration


def _parse_rapid_command(message):
    """Parse RAPID command in the form 'RAPID:mode'."""
    raw = message.strip()
    if not raw:
        return None

    raw = raw.strip("()[]{}")

    parts = [p.strip() for p in raw.split(":", 1)]
    if len(parts) != 2 or parts[0].upper() != "RAPID":
        return None

    try:
        return int(parts[1])
    except ValueError:
        return None


def _parse_reset_command(message):
    """Parse RESET command in the exact form 'RESET'."""
    raw = message.strip()
    if not raw:
        return False

    raw = raw.strip("()[]{}:")
    return raw.upper() == "RESET"


def _parse_shutdown_command(message):
    """Parse SHUTDOWN command in the exact form 'SHUTDOWN'."""
    raw = message.strip()
    if not raw:
        return False

    raw = raw.strip("()[]{}:")
    return raw.upper() == "SHUTDOWN"


def _enqueue_lane_scores(index, extra):
    """Queue one or more comma-separated scores for lane indices 0-5."""
    if index < 0 or index >= 6:
        return
    for score in (s.strip() for s in extra.split(",")):
        if score:
            _score_queue.append((index + 1, score))


def _network_listener():
    """Run in a daemon thread. Accept TCP connections and read per-panel updates.

    Expected payload per connection:
        One update in the form ``"STATUS:index"`` where STATUS is one of
        ``OFF``, ``ACK``, or ``AUT``, and index is in range 0..13.
        Optional extra payload is accepted as ``"STATUS:index:extra_data"``.
        For lane indices 0..5, ``AUT:index:score,score,...`` queues one or
        more scores to animate on screen.
        SNAP animation can also be triggered with ``"SNAP"``,
        ``"SNAPS"``, or ``"SNAP:numberOfSeconds"``.
        RAPID mode can also be triggered with ``"RAPID:mode"``.
        SHUTDOWN sequence can also be triggered with ``"SHUTDOWN"``.
    The connection is closed after each message is processed.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", LISTEN_PORT))
    srv.listen(5)
    srv.settimeout(1.0)  # allow periodic check so thread can exit

    while True:
        try:
            conn, _addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                msg = data.decode("utf-8", errors="ignore")
                parsed = _parse_status_update(msg)
                if parsed is not None:
                    status, index, extra = parsed
                    with _status_lock:
                        panel_statuses[index] = {
                            "status": status,
                            "extra":  extra,
                        }
                        if status == "AUT" and extra and extra.lower() != "ok":
                            _enqueue_lane_scores(index, extra)
                            if index < 6:
                                for s in extra.split(","):
                                    try:
                                        lane_scores[index] += float(s.strip())
                                    except ValueError:
                                        pass
                        elif status == "ACK" and index < 6:
                            lane_scores[index] = 0
                else:
                    snap_seconds = _parse_snap_command(msg)
                    if snap_seconds is not None:
                        _set_pending_snap(snap_seconds)
                    else:
                        rapid_mode = _parse_rapid_command(msg)
                        if rapid_mode is not None:
                            _set_pending_rapid_mode(rapid_mode)
                        elif _parse_reset_command(msg):
                            _set_pending_reset()
                        elif _parse_shutdown_command(msg):
                            _set_pending_shutdown()
        except Exception:
            pass  # silently ignore malformed messages
        finally:
            conn.close()


def load_fullscreen_logo(screen_w, screen_h):
    """Load and scale the Bedford logo to full-screen dimensions."""
    for path in ("Bedford-logo.jp", "bedford-logo.jp", "Bedford-logo.jpg", "bedford-logo.jpg"):
        try:
            logo = pygame.image.load(path).convert()
            return pygame.transform.smoothscale(logo, (screen_w, screen_h))
        except (pygame.error, FileNotFoundError):
            continue
    return None


def get_primary_ip_address():
    """Return a best-effort LAN IP address for this machine."""
    for host in ("8.8.8.8", "1.1.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((host, 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
        finally:
            sock.close()

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass

    return "IP unavailable"


def request_system_shutdown():
    """Request OS shutdown; return True if a shutdown command was launched."""
    commands = [
        ["sudo", "shutdown", "-h", "now"],
        ["shutdown", "-h", "now"],
    ]
    for cmd in commands:
        try:
            subprocess.Popen(cmd)
            return True
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return False


def _status_bg_colour(index):
    """Return the background colour for panel *index* based on its status."""
    with _status_lock:
        status = panel_statuses[index]["status"]
    if status == "ACK":
        return COL_STATUS_ACK
    elif status == "OFF":
        return COL_STATUS_OFF
    elif status == "AUT":
        return COL_STATUS_AUT
    return COL_PANEL_BG   # default / unknown


# ---------------------------------------------------------------------------
# Score toast – animated score notification
# ---------------------------------------------------------------------------
TOAST_DURATION = 3.0   # seconds for the full rise-and-fade animation
TOAST_FADE_IN  = 0.4   # fraction of TOAST_DURATION used for fade-in
TOAST_FADE_OUT = 0.1   # fraction of TOAST_DURATION used for fade-out


class ScoreToast:
    """Represents one animating score pop-up for a lane."""
    def __init__(self, lane: int, score: str, start_y: int, travel: int,
                 lane_label: str = ""):
        self.lane    = lane        # 1-based lane number
        self.score   = score       # score string
        self.lane_label = lane_label
        self.start_y = start_y     # y centre when the toast starts
        self.travel  = travel      # total upward pixel travel over lifetime
        self.born    = time.time() # timestamp when toast was created

    @property
    def alive(self) -> bool:
        return time.time() - self.born < TOAST_DURATION

    def progress(self) -> float:
        """0.0 → 1.0 over TOAST_DURATION."""
        return min((time.time() - self.born) / TOAST_DURATION, 1.0)

    def alpha(self) -> int:
        p = self.progress()
        # Smooth ease-in/ease-out opacity while moving upward.
        if p < TOAST_FADE_IN:
            t = p / TOAST_FADE_IN
            return int(255 * (0.5 - 0.5 * math.cos(math.pi * t)))
        if p > 1.0 - TOAST_FADE_OUT:
            t = (1.0 - p) / TOAST_FADE_OUT
            return int(255 * (0.5 - 0.5 * math.cos(math.pi * max(0.0, t))))
        return 255

    def current_y(self) -> int:
        return int(self.start_y - self.travel * self.progress())


def poll_score_toasts(toasts: list, start_y: int, travel: int):
    """Drain queued scores; start next when current one reaches fade-out."""
    fade_out_start = 1.0 - TOAST_FADE_OUT

    # Only allow a new toast if none exist, or the newest existing toast has
    # reached the fade-out phase.
    if toasts:
        newest_progress = max(t.progress() for t in toasts)
        if newest_progress < fade_out_start:
            return

    with _status_lock:
        if _score_queue:
            lane, score = _score_queue.popleft()
            toasts.append(ScoreToast(lane=lane, score=score,
                                     start_y=start_y, travel=travel))


def enqueue_snap_toast(toasts: list, snap_count: int, start_y: int, travel: int):
    """Queue a SNAP toast using the same animation as score toasts."""
    toasts.append(ScoreToast(
        lane=0,
        score=str(snap_count),
        start_y=start_y,
        travel=travel,
        lane_label="Snap",
    ))


# ---------------------------------------------------------------------------
# Build the static clock-face surface (drawn once for performance)
# ---------------------------------------------------------------------------
def build_face(screen_w, screen_h, cx, cy, clock_radius, rapid_scale=False):
    face = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)

    # Outer glow rings
    for i in range(30, 0, -1):
        alpha = max(4, int(25 * (i / 30)))
        glow_col = (COL_GLOW[0], COL_GLOW[1], COL_GLOW[2], alpha)
        pygame.draw.circle(face, glow_col, (cx, cy), clock_radius + i, 2)

    # Main outer ring
    pygame.draw.circle(face, COL_RING_OUTER, (cx, cy), clock_radius, 3)
    pygame.draw.circle(face, COL_RING_INNER, (cx, cy), clock_radius - 4, 2)

    # Inner subtle ring
    pygame.draw.circle(face, (25, 35, 55), (cx, cy), int(clock_radius * 0.92), 1)

    # Tick marks
    for i in range(60):
        angle = i * 6
        if i % 5 == 0:
            outer_r = clock_radius - 8
            inner_r = clock_radius - 35
            colour  = COL_TICK_MAJOR
            width   = 3
        else:
            outer_r = clock_radius - 12
            inner_r = clock_radius - 22
            colour  = COL_TICK_MINOR
            width   = 1

        p1 = polar_to_cart(cx, cy, angle, outer_r)
        p2 = polar_to_cart(cx, cy, angle, inner_r)
        if width > 1:
            thick_aa_line(face, p1, p2, colour, width)
        else:
            pygame.draw.aaline(face, colour, p1, p2)

    # Clock-face numbers
    num_font_size = max(18, int(clock_radius * 0.13))
    num_font = pygame.font.SysFont("Arial", num_font_size, bold=True)
    for hour in range(1, 13):
        angle = hour * 30
        pos   = polar_to_cart(cx, cy, angle, clock_radius - 60)
        label = str(hour * 5) if rapid_scale else str(hour)
        txt   = num_font.render(label, True, COL_NUMBER)
        rect  = txt.get_rect(center=(int(pos[0]), int(pos[1])))
        face.blit(txt, rect)

    return face


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
def main():
    pygame.init()

    # Full-screen at desktop resolution
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN)
    pygame.display.set_caption("Bedford School Range – Status Screen")
    pygame.mouse.set_visible(False)

    fps_clock = pygame.time.Clock()

    if not run_startup_logo_sequence(screen, fps_clock, screen_w, screen_h):
        pygame.quit()
        sys.exit()

    # -----------------------------------------------------------------
    # Bottom status panels – 7 columns × 2 rows (14 panels total)
    # Laid out first so we know where the panel area starts, then we
    # centre the clock in the remaining gap above it.
    # -----------------------------------------------------------------
    panel_labels_top = [
        "Lane Controller 1", "Lane Controller 2", "Lane Controller 3",
        "Lane Controller 4", "Lane Controller 5", "Lane Controller 6",
        "Foyer Display",
    ]
    panel_labels_bot = [
        "Snap Target 1", "Snap Target 2", "Snap Target 3",
        "Snap Target 4", "Snap Target 5", "Snap Target 6",
        "Range Display",
    ]

    screen_border = 20                                  # 50 px border L/R/B
    num_cols      = 7
    panel_gap     = 6                                   # gap between panels
    panel_h       = max(36, int(screen_h * 0.042))      # slightly smaller rows
    total_panel_h = panel_h * 2 + panel_gap * 3         # 2 rows + gaps top/mid/bot
    panel_area_y  = screen_h - screen_border - total_panel_h  # top of panel region
    usable_w      = screen_w - screen_border * 2        # width inside L/R borders
    panel_w       = (usable_w - panel_gap * (num_cols - 1)) // num_cols

    panel_rects_top = []
    panel_rects_bot = []
    for col in range(num_cols):
        x = screen_border + col * (panel_w + panel_gap)
        top_rect = pygame.Rect(x, panel_area_y + panel_gap, panel_w, panel_h)
        bot_rect = pygame.Rect(x, panel_area_y + panel_gap * 2 + panel_h, panel_w, panel_h)
        panel_rects_top.append(top_rect)
        panel_rects_bot.append(bot_rect)

    # Clock geometry – two-thirds of screen height, in the left third,
    # vertically centred in the gap between screen top and panel area
    clock_diameter = int(screen_h * 2 / 3)
    clock_radius   = clock_diameter // 2
    cx = screen_w // 3 - 100     # shifted 20 px left
    cy = panel_area_y // 2      # centred in the space above the panels

    # Pre-render both static faces (normal and RAPID scale)
    face_surf_normal = build_face(screen_w, screen_h, cx, cy, clock_radius, rapid_scale=False)
    face_surf_rapid = build_face(screen_w, screen_h, cx, cy, clock_radius, rapid_scale=True)

    # Top-left corner logo (fades in after intro animation completes).
    logo_margin = 12
    max_logo_w = max(70, int(screen_w * 0.10))
    max_logo_h = max(35, int(screen_h * 0.07))
    corner_logo = load_scaled_corner_logo(max_logo_w, max_logo_h)
    corner_logo_alpha = 0
    corner_logo_fade_start = None

    ip_address_text = f"{get_primary_ip_address()}"
    ip_label_alpha = 0
    ip_label_fade_out_start = None
    ip_label_fade_out_from_alpha = 0
    ip_label_surface = None
    ip_label_pos = (logo_margin, logo_margin)

    if corner_logo is not None:
        ip_label_w = corner_logo.get_width()
        ip_label_h = max(26, int(corner_logo.get_height() * 0.42))
        ip_label_pos = (logo_margin, logo_margin + corner_logo.get_height() + 6)

        ip_font = fit_font_to_rect("Arial", ip_address_text,
                                   max(10, ip_label_w - 4),
                                   max(10, ip_label_h - 2),
                                   bold=False)
        ip_text = ip_font.render(ip_address_text, True, (255, 255, 255))
        ip_text_rect = ip_text.get_rect(center=(ip_label_w // 2, ip_label_h // 2))

        ip_label_surface = pygame.Surface((ip_label_w, ip_label_h), pygame.SRCALPHA)
        ip_label_surface.blit(ip_text, ip_text_rect)

    # Fonts
    digital_font = pygame.font.SysFont("Arial", max(16, int(clock_radius * 0.10)))
    date_font    = pygame.font.SysFont("Arial", max(14, int(clock_radius * 0.065)))
    label_font   = pygame.font.SysFont("Arial", max(12, int(clock_radius * 0.05)))
    panel_font      = pygame.font.SysFont("Arial", max(18, int(clock_radius * 0.055)))
    lane_score_font = pygame.font.SysFont("Arial", max(20, panel_h), bold=True)

    # Toast fonts – used in the right-hand score area
    toast_lane_font  = pygame.font.SysFont("Arial", max(88, int(clock_radius * 0.52)), bold=True)
    toast_score_font = pygame.font.SysFont("Consolas", max(240, int(clock_radius * 1.52)), bold=True)
    shutdown_font = pygame.font.SysFont("Arial", max(42, int(clock_radius * 0.24)), bold=True)

    # Score toast state
    # Toasts rise from 50% of screen height to the top edge (0%).
    toast_start_y  = int(screen_h * 0.50)
    toast_top_y    = 0
    toast_travel   = toast_start_y - toast_top_y
    score_toasts: list = []

    # -----------------------------------------------------------------
    # Start network listener (daemon thread – exits when main exits)
    # -----------------------------------------------------------------
    net_thread = threading.Thread(target=_network_listener, daemon=True)
    net_thread.start()

    # -----------------------------------------------------------------
    # Intro animation – capture the real time at launch
    # -----------------------------------------------------------------
    launch       = datetime.now()
    launch_h     = launch.hour % 12
    launch_m     = launch.minute
    launch_s     = launch.second
    launch_frac  = launch.microsecond / 1_000_000

    init_second  = (launch_s + launch_frac) * 6
    init_minute  = launch_m * 6 + launch_s * 0.1
    init_hour    = launch_h * 30 + launch_m * 0.5

    TWELVE       = 0.0                    # 0° == 12 o'clock
    intro_start  = time.time()
    intro_done   = False

    # SNAP animation state
    snap_start_time = None
    snap_duration = 0.0
    snap_toast_shown_for_cycle = False
    SnapCount = 1

    # RAPID mode state
    #   None -> normal clock mode
    #   0    -> RAPID armed/reset (animated to top, timer at 00:00)
    #   1    -> RAPID running
    #   2    -> RAPID stopped (frozen)
    rapid_mode = None
    rapid_anim_start = None
    rapid_from_second = 0.0
    rapid_from_minute = 0.0
    rapid_from_hour = 0.0
    rapid_run_start = None
    rapid_elapsed = 0.0
    rapid_timer_text = "00:00"

    # RESET animation state
    reset_anim_phase = None  # None | "up" | "down"
    reset_anim_start = 0.0
    reset_from_second = 0.0
    reset_from_minute = 0.0
    reset_from_hour = 0.0
    reset_show_rapid_face = False

    # SHUTDOWN sequence state
    shutdown_state = None  # None | "hands_up" | "logo_hold" | "logo_fade" | "message" | "poweroff"
    shutdown_phase_start = 0.0
    shutdown_from_second = 0.0
    shutdown_from_minute = 0.0
    shutdown_from_hour = 0.0
    shutdown_logo = load_fullscreen_logo(screen_w, screen_h)
    shutdown_poweroff_issued = False

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        # Current time
        now     = datetime.now()
        hours   = now.hour % 12
        minutes = now.minute
        seconds = now.second
        frac    = now.microsecond / 1_000_000   # smooth sweep fraction

        # Real-time target angles (0° = 12 o'clock, clockwise)
        target_second = (seconds + frac) * 6
        target_minute = minutes * 6 + seconds * 0.1
        target_hour   = hours * 30 + minutes * 0.5

        # --- intro animation (two phases) ----------------------------
        # Phase 1: initial time  →  12 o'clock
        # Phase 2: 12 o'clock   →  current real time
        if not intro_done:
            elapsed = time.time() - intro_start
            if elapsed < INTRO_DURATION:
                # Phase 1 – sweep hands UP to 12
                t = ease_in_out_cubic(min(elapsed / INTRO_DURATION, 1.0))
                second_angle = lerp_angle(init_second, TWELVE, t)
                minute_angle = lerp_angle(init_minute, TWELVE, t)
                hour_angle   = lerp_angle(init_hour,   TWELVE, t)
            elif elapsed < INTRO_DURATION * 2:
                # Phase 2 – sweep hands DOWN from 12 to real time
                t = ease_in_out_cubic(min((elapsed - INTRO_DURATION) / INTRO_DURATION, 1.0))
                second_angle = lerp_angle(TWELVE, target_second, t)
                minute_angle = lerp_angle(TWELVE, target_minute, t)
                hour_angle   = lerp_angle(TWELVE, target_hour,   t)
            else:
                intro_done   = True
                second_angle = target_second
                minute_angle = target_minute
                hour_angle   = target_hour
        else:
            second_angle = target_second
            minute_angle = target_minute
            hour_angle   = target_hour

        if intro_done and corner_logo is not None and corner_logo_fade_start is None:
            corner_logo_fade_start = time.time()

        if corner_logo_fade_start is not None:
            fade_elapsed = time.time() - corner_logo_fade_start
            fade_t = min(fade_elapsed / CORNER_LOGO_FADE_TIME, 1.0)
            corner_logo_alpha = int(255 * ease_in_out_cubic(fade_t))
            if ip_label_fade_out_start is None:
                ip_label_alpha = corner_logo_alpha

        if (
            corner_logo_fade_start is not None
            and ip_label_fade_out_start is None
            and (time.time() - corner_logo_fade_start) >= IP_LABEL_HOLD_TIME
        ):
            ip_label_fade_out_start = time.time()
            ip_label_fade_out_from_alpha = ip_label_alpha

        if ip_label_fade_out_start is not None:
            fade_out_elapsed = time.time() - ip_label_fade_out_start
            fade_out_t = min(fade_out_elapsed / IP_LABEL_FADE_OUT_TIME, 1.0)
            ip_label_alpha = int(ip_label_fade_out_from_alpha * (1.0 - fade_out_t))

        pending_shutdown = _consume_pending_shutdown()
        if pending_shutdown and shutdown_state is None:
            # Capture the currently visible hand positions for the final sweep-up.
            from_second = second_angle
            from_minute = minute_angle
            from_hour = hour_angle

            if rapid_mode == 2:
                from_second = (rapid_elapsed * 360.0) % 360.0
                from_minute = (rapid_elapsed * 6.0) % 360.0
                from_hour = ((rapid_elapsed / 60.0) * 6.0) % 360.0
            elif rapid_mode == 1 and rapid_run_start is not None:
                run_elapsed = max(0.0, time.time() - rapid_run_start)
                from_second = (run_elapsed * 360.0) % 360.0
                from_minute = (run_elapsed * 6.0) % 360.0
                from_hour = ((run_elapsed / 60.0) * 6.0) % 360.0
            elif rapid_mode == 0 and rapid_anim_start is not None:
                anim_elapsed = time.time() - rapid_anim_start
                t = ease_in_out_cubic(min(anim_elapsed / INTRO_DURATION, 1.0))
                from_second = lerp_angle(rapid_from_second, TWELVE, t)
                from_minute = lerp_angle(rapid_from_minute, TWELVE, t)
                from_hour = lerp_angle(rapid_from_hour, TWELVE, t)

            shutdown_state = "hands_up"
            shutdown_phase_start = time.time()
            shutdown_from_second = from_second
            shutdown_from_minute = from_minute
            shutdown_from_hour = from_hour

            # Stop all active side animations and modes while shutdown runs.
            rapid_mode = None
            rapid_anim_start = None
            rapid_run_start = None
            snap_start_time = None

        if shutdown_state is not None:
            elapsed = time.time() - shutdown_phase_start

            if shutdown_state == "hands_up":
                if elapsed < INTRO_DURATION:
                    t = ease_in_out_cubic(min(elapsed / INTRO_DURATION, 1.0))
                    second_angle = lerp_angle(shutdown_from_second, TWELVE, t)
                    minute_angle = lerp_angle(shutdown_from_minute, TWELVE, t)
                    hour_angle = lerp_angle(shutdown_from_hour, TWELVE, t)
                else:
                    second_angle = TWELVE
                    minute_angle = TWELVE
                    hour_angle = TWELVE
                    shutdown_state = "logo_hold"
                    shutdown_phase_start = time.time()

                screen.fill(COL_BG)
                screen.blit(face_surf_normal, (0, 0))

                h_end = polar_to_cart(cx, cy, hour_angle, clock_radius * 0.50)
                h_tail = polar_to_cart(cx, cy, hour_angle + 180, clock_radius * 0.08)
                thick_aa_line(screen, h_tail, h_end, COL_HOUR_HAND, 7)

                m_end = polar_to_cart(cx, cy, minute_angle, clock_radius * 0.72)
                m_tail = polar_to_cart(cx, cy, minute_angle + 180, clock_radius * 0.10)
                thick_aa_line(screen, m_tail, m_end, COL_MINUTE_HAND, 4)

                s_end = polar_to_cart(cx, cy, second_angle, clock_radius * 0.80)
                s_tail = polar_to_cart(cx, cy, second_angle + 180, clock_radius * 0.15)
                thick_aa_line(screen, s_tail, s_end, COL_SECOND_HAND, 2)

                aa_filled_circle(screen, cx, cy, 8, COL_CENTRE_DOT)
                aa_filled_circle(screen, cx, cy, 4, COL_SECOND_HAND)
            elif shutdown_state == "logo_hold":
                if shutdown_logo is not None:
                    screen.blit(shutdown_logo, (0, 0))
                else:
                    screen.fill((0, 0, 0))
                if elapsed >= SHUTDOWN_LOGO_HOLD_TIME:
                    shutdown_state = "logo_fade"
                    shutdown_phase_start = time.time()
            elif shutdown_state == "logo_fade":
                if shutdown_logo is not None:
                    screen.blit(shutdown_logo, (0, 0))
                else:
                    screen.fill((0, 0, 0))

                fade_t = min(elapsed / SHUTDOWN_LOGO_FADE_TIME, 1.0)
                fade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
                fade.fill((0, 0, 0, int(255 * fade_t)))
                screen.blit(fade, (0, 0))

                if elapsed >= SHUTDOWN_LOGO_FADE_TIME:
                    shutdown_state = "message"
                    shutdown_phase_start = time.time()
            elif shutdown_state == "message":
                screen.fill((0, 0, 0))
                msg = shutdown_font.render("Shutting Down", True, (220, 220, 220))
                msg_rect = msg.get_rect(center=(screen_w // 2, screen_h // 2))
                screen.blit(msg, msg_rect)

                if elapsed >= SHUTDOWN_MESSAGE_TIME:
                    shutdown_state = "poweroff"
                    shutdown_phase_start = time.time()
            elif shutdown_state == "poweroff":
                if not shutdown_poweroff_issued:
                    request_system_shutdown()
                    shutdown_poweroff_issued = True
                running = False

            pygame.display.flip()
            fps_clock.tick(60)
            continue

        pending_reset = _consume_pending_reset()
        if pending_reset:
            # Capture visible hand positions before leaving RAPID mode.
            from_second = second_angle
            from_minute = minute_angle
            from_hour = hour_angle

            if rapid_mode == 2:
                from_second = (rapid_elapsed * 360.0) % 360.0
                from_minute = (rapid_elapsed * 6.0) % 360.0
                from_hour = ((rapid_elapsed / 60.0) * 6.0) % 360.0
            elif rapid_mode == 1 and rapid_run_start is not None:
                run_elapsed = max(0.0, time.time() - rapid_run_start)
                from_second = (run_elapsed * 360.0) % 360.0
                from_minute = (run_elapsed * 6.0) % 360.0
                from_hour = ((run_elapsed / 60.0) * 6.0) % 360.0
            elif rapid_mode == 0 and rapid_anim_start is not None:
                anim_elapsed = time.time() - rapid_anim_start
                t = ease_in_out_cubic(min(anim_elapsed / INTRO_DURATION, 1.0))
                from_second = lerp_angle(rapid_from_second, TWELVE, t)
                from_minute = lerp_angle(rapid_from_minute, TWELVE, t)
                from_hour = lerp_angle(rapid_from_hour, TWELVE, t)

            # Reset all panel statuses to red (OFF) awaiting fresh updates.
            with _status_lock:
                for i in range(len(panel_statuses)):
                    panel_statuses[i] = {"status": "OFF", "extra": ""}
                for i in range(6):
                    lane_scores[i] = 0

            # Start reset sequence: up to 12, then down to current time.
            reset_anim_phase = "up"
            reset_anim_start = time.time()
            reset_from_second = from_second
            reset_from_minute = from_minute
            reset_from_hour = from_hour
            reset_show_rapid_face = rapid_mode in (0, 1, 2)

            # Leave RAPID mode immediately (hides right-hand timer).
            rapid_mode = None
            rapid_anim_start = None
            rapid_run_start = None
            rapid_elapsed = 0.0
            rapid_timer_text = "00:00"

        pending_rapid_mode = _consume_pending_rapid_mode()
        if pending_rapid_mode is not None and reset_anim_phase is None:
            if pending_rapid_mode == 0:
                # Enter/reset RAPID arm state: animate current hand positions
                # back to 12 and reset timer to 00:00.
                from_second = second_angle
                from_minute = minute_angle
                from_hour = hour_angle

                if rapid_mode == 2:
                    # If frozen, animate from frozen RAPID hand positions.
                    from_second = (rapid_elapsed * 360.0) % 360.0
                    from_minute = (rapid_elapsed * 6.0) % 360.0
                    from_hour = ((rapid_elapsed / 60.0) * 6.0) % 360.0
                elif rapid_mode == 1 and rapid_run_start is not None:
                    # If running, animate from current RAPID hand positions.
                    run_elapsed = max(0.0, time.time() - rapid_run_start)
                    from_second = (run_elapsed * 360.0) % 360.0
                    from_minute = (run_elapsed * 6.0) % 360.0
                    from_hour = ((run_elapsed / 60.0) * 6.0) % 360.0

                rapid_mode = 0
                rapid_anim_start = time.time()
                rapid_from_second = from_second
                rapid_from_minute = from_minute
                rapid_from_hour = from_hour
                rapid_run_start = None
                rapid_elapsed = 0.0
                rapid_timer_text = "00:00"
            elif pending_rapid_mode == 1:
                # Start RAPID timer. If currently stopped, resume from frozen
                # elapsed time; otherwise start/restart from zero.
                if rapid_mode == 2:
                    rapid_mode = 1
                    rapid_anim_start = None
                    rapid_run_start = time.time() - rapid_elapsed
                else:
                    rapid_mode = 1
                    rapid_anim_start = None
                    rapid_run_start = time.time()
                    rapid_elapsed = 0.0
                    rapid_timer_text = "00:00"
            elif pending_rapid_mode == 2 and rapid_mode in (0, 1, 2):
                # Stop/freeze RAPID timers at current elapsed value.
                if rapid_mode == 1 and rapid_run_start is not None:
                    rapid_elapsed = max(0.0, time.time() - rapid_run_start)
                rapid_mode = 2
                rapid_run_start = None
                rapid_anim_start = None

        if reset_anim_phase == "up":
            elapsed = time.time() - reset_anim_start
            if elapsed < INTRO_DURATION:
                t = ease_in_out_cubic(min(elapsed / INTRO_DURATION, 1.0))
                second_angle = lerp_angle(reset_from_second, TWELVE, t)
                minute_angle = lerp_angle(reset_from_minute, TWELVE, t)
                hour_angle = lerp_angle(reset_from_hour, TWELVE, t)
            else:
                second_angle = TWELVE
                minute_angle = TWELVE
                hour_angle = TWELVE
                reset_anim_phase = "down"
                reset_anim_start = time.time()
                # After reaching 12, restore normal clock-face labels.
                reset_show_rapid_face = False
        elif reset_anim_phase == "down":
            elapsed = time.time() - reset_anim_start
            if elapsed < INTRO_DURATION:
                t = ease_in_out_cubic(min(elapsed / INTRO_DURATION, 1.0))
                second_angle = lerp_angle(TWELVE, target_second, t)
                minute_angle = lerp_angle(TWELVE, target_minute, t)
                hour_angle = lerp_angle(TWELVE, target_hour, t)
            else:
                reset_anim_phase = None
                second_angle = target_second
                minute_angle = target_minute
                hour_angle = target_hour
        elif rapid_mode == 0:
            if rapid_anim_start is not None:
                anim_elapsed = time.time() - rapid_anim_start
                if anim_elapsed < INTRO_DURATION:
                    t = ease_in_out_cubic(min(anim_elapsed / INTRO_DURATION, 1.0))
                    second_angle = lerp_angle(rapid_from_second, TWELVE, t)
                    minute_angle = lerp_angle(rapid_from_minute, TWELVE, t)
                    hour_angle = lerp_angle(rapid_from_hour, TWELVE, t)
                else:
                    rapid_anim_start = None
                    second_angle = 0.0
                    minute_angle = 0.0
                    hour_angle = 0.0
            else:
                second_angle = 0.0
                minute_angle = 0.0
                hour_angle = 0.0

            rapid_elapsed = 0.0
            rapid_timer_text = "00:00"
        elif rapid_mode == 1:
            rapid_elapsed = max(0.0, time.time() - rapid_run_start) if rapid_run_start else 0.0
            # RAPID mapping:
            #   red second hand   -> milliseconds (1 rotation / second)
            #   long minute hand  -> seconds      (1 rotation / minute)
            #   short hour hand   -> minutes      (1 rotation / hour)
            second_angle = (rapid_elapsed * 360.0) % 360.0
            minute_angle = (rapid_elapsed * 6.0) % 360.0
            hour_angle = ((rapid_elapsed / 60.0) * 6.0) % 360.0

            whole_seconds = int(rapid_elapsed)
            rapid_timer_text = f"{whole_seconds // 60:02d}:{whole_seconds % 60:02d}"
        elif rapid_mode == 2:
            # Keep displaying the frozen elapsed value and corresponding hand angles.
            second_angle = (rapid_elapsed * 360.0) % 360.0
            minute_angle = (rapid_elapsed * 6.0) % 360.0
            hour_angle = ((rapid_elapsed / 60.0) * 6.0) % 360.0
            whole_seconds = int(rapid_elapsed)
            rapid_timer_text = f"{whole_seconds // 60:02d}:{whole_seconds % 60:02d}"

        # --- draw ----------------------------------------------------
        screen.fill(COL_BG)
        face_surf = face_surf_rapid if (reset_show_rapid_face or rapid_mode in (0, 1, 2)) else face_surf_normal
        screen.blit(face_surf, (0, 0))

        # Trigger/restart SNAP animation if a new command has arrived.
        pending_snap_seconds = _consume_pending_snap()
        if pending_snap_seconds is not None:
            snap_start_time = time.time()
            snap_duration = pending_snap_seconds
            snap_toast_shown_for_cycle = False

        if snap_start_time is not None:
            snap_elapsed = time.time() - snap_start_time
            snap_visible = False
            snap_end_angle = SNAP_START_ANGLE

            if snap_elapsed < snap_duration:
                t = min(snap_elapsed / snap_duration, 1.0)
                snap_end_angle = lerp_clockwise(SNAP_START_ANGLE, SNAP_END_ANGLE, t)
                snap_visible = True
            elif snap_elapsed < snap_duration + SNAP_HOLD_TIME:
                snap_end_angle = SNAP_END_ANGLE
                snap_visible = True
                if not snap_toast_shown_for_cycle:
                    enqueue_snap_toast(score_toasts, SnapCount, toast_start_y, toast_travel)
                    snap_toast_shown_for_cycle = True
                    SnapCount += 1
                    if SnapCount > 5:
                        SnapCount = 1
            elif snap_elapsed < snap_duration + SNAP_HOLD_TIME + SNAP_RETURN_TIME:
                t = ((snap_elapsed - snap_duration - SNAP_HOLD_TIME)
                     / SNAP_RETURN_TIME)
                snap_end_angle = lerp_anticlockwise(SNAP_END_ANGLE, SNAP_START_ANGLE, t)
                snap_visible = True
            else:
                snap_start_time = None

            if snap_visible:
                draw_snap_ring(screen, screen_w, screen_h, cx, cy, clock_radius,
                               SNAP_START_ANGLE, snap_end_angle)

        # Decorative rotating arcs (subtle futuristic flair)
        arc_time = time.time()
        for k, offset in enumerate([0, 120, 240]):
            arc_start = math.radians((arc_time * (8 + k * 3)) % 360 + offset)
            arc_end   = arc_start + math.radians(40)
            arc_r     = int(clock_radius * (0.82 - k * 0.06))
            arc_rect  = pygame.Rect(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
            arc_col   = (COL_GLOW[0], COL_GLOW[1], COL_GLOW[2], 50 + k * 15)
            tmp = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            pygame.draw.arc(tmp, arc_col, arc_rect, arc_start, arc_end, 2)
            screen.blit(tmp, (0, 0))

        # Hour hand
        h_end   = polar_to_cart(cx, cy, hour_angle, clock_radius * 0.50)
        h_tail  = polar_to_cart(cx, cy, hour_angle + 180, clock_radius * 0.08)
        thick_aa_line(screen, h_tail, h_end, COL_HOUR_HAND, 7)

        # Minute hand
        m_end   = polar_to_cart(cx, cy, minute_angle, clock_radius * 0.72)
        m_tail  = polar_to_cart(cx, cy, minute_angle + 180, clock_radius * 0.10)
        thick_aa_line(screen, m_tail, m_end, COL_MINUTE_HAND, 4)

        # Second hand (thin, with counter-weight tail)
        s_end   = polar_to_cart(cx, cy, second_angle, clock_radius * 0.80)
        s_tail  = polar_to_cart(cx, cy, second_angle + 180, clock_radius * 0.15)
        thick_aa_line(screen, s_tail, s_end, COL_SECOND_HAND, 2)

        # Centre dot
        aa_filled_circle(screen, cx, cy, 8, COL_CENTRE_DOT)
        aa_filled_circle(screen, cx, cy, 4, COL_SECOND_HAND)

        # Digital time readout below centre
        time_str = now.strftime("%H:%M:%S")
        d_txt  = digital_font.render(time_str, True, COL_DIGITAL)
        d_rect = d_txt.get_rect(center=(cx, cy + int(clock_radius * 0.32)))
        pad = 10
        backing = pygame.Rect(d_rect.left - pad, d_rect.top - pad // 2,
                               d_rect.width + pad * 2, d_rect.height + pad)
        pygame.draw.rect(screen, (15, 20, 30), backing, border_radius=6)
        pygame.draw.rect(screen, COL_RING_OUTER, backing, 1, border_radius=6)
        screen.blit(d_txt, d_rect)

        # Date above centre
        date_str = now.strftime("%A %d %B %Y").upper()
        dt_txt   = date_font.render(date_str, True, COL_DATE)
        dt_rect  = dt_txt.get_rect(center=(cx, cy - int(clock_radius * 0.28)))
        screen.blit(dt_txt, dt_rect)

        # Small label near bottom of face
        lbl_txt  = label_font.render("Bedford School Range", True, (60, 80, 100))
        lbl_rect = lbl_txt.get_rect(center=(cx, cy + int(clock_radius * 0.48)))
        screen.blit(lbl_txt, lbl_rect)

        # ----- score toasts (right-hand area) ------------------------
        # Right-hand area: centred within the horizontal gap between the
        # clock's right edge and the right screen border.
        clock_right_x = cx + clock_radius
        right_edge_x  = screen_w - screen_border
        toast_center_x = (clock_right_x + right_edge_x) // 2

        toast_area_top    = toast_top_y
        toast_area_bottom = screen_h - 10

        if rapid_mode in (0, 1, 2):
            rapid_left = clock_right_x + 50
            rapid_rect = pygame.Rect(
                rapid_left,
                screen_border,
                max(80, right_edge_x - rapid_left - 20),
                max(80, panel_area_y - screen_border - 12),
            )
            draw_rapid_timer(screen, rapid_rect, rapid_timer_text)
        else:
            poll_score_toasts(score_toasts, toast_start_y, toast_travel)
            score_toasts[:] = [t for t in score_toasts if t.alive]

            for toast in score_toasts:
                a = toast.alpha()
                cy_toast = toast.current_y()

                # Measure text
                lane_str  = toast.lane_label if toast.lane_label else f"LANE {toast.lane}"
                score_str = toast.score

                lane_surf  = toast_lane_font.render(lane_str,  True, (180, 220, 255))
                score_surf = toast_score_font.render(score_str, True, (255, 255, 100))

                total_h = lane_surf.get_height() + score_surf.get_height() + 4
                # Keep bottom bound only; allow upward motion to continue to top.
                cy_toast = min(cy_toast, toast_area_bottom - total_h // 2)

                lane_rect  = lane_surf.get_rect(
                    centerx=toast_center_x,
                    bottom=cy_toast - 2)
                score_rect = score_surf.get_rect(
                    centerx=toast_center_x,
                    top=cy_toast + 2)

                # Lane label
                ls_alpha = lane_surf.copy()
                ls_alpha.set_alpha(a)
                screen.blit(ls_alpha, lane_rect)

                # Score value
                ss_alpha = score_surf.copy()
                ss_alpha.set_alpha(a)
                screen.blit(ss_alpha, score_rect)

        # ----- bottom status panels ----------------------------------
        # Snapshot lane scores for this frame (under lock to avoid races).
        with _status_lock:
            frame_lane_scores = [
                lane_scores[i] if panel_statuses[i]["status"] == "AUT" else None
                for i in range(6)
            ]
        # Top row: cols 0-5 → status indices 0-5, col 6 → index 12
        for col, (rect, label) in enumerate(zip(panel_rects_top, panel_labels_top)):
            idx = col if col < 6 else 12
            draw_panel(screen, rect, label, panel_font, bg_col=_status_bg_colour(idx))
        # Lane score numbers above each lane-controller panel when in AUT mode.
        for col in range(6):
            score_val = frame_lane_scores[col]
            if score_val is not None:
                s_txt = lane_score_font.render(str(int(score_val)), True, (255, 255, 100))
                s_rect = s_txt.get_rect(
                    centerx=panel_rects_top[col].centerx,
                    bottom=panel_rects_top[col].top - 4,
                )
                screen.blit(s_txt, s_rect)
        # Bottom row: cols 0-5 → status indices 6-11, col 6 → index 13
        for col, (rect, label) in enumerate(zip(panel_rects_bot, panel_labels_bot)):
            idx = col + 6 if col < 6 else 13
            draw_panel(screen, rect, label, panel_font, bg_col=_status_bg_colour(idx))

        if corner_logo is not None and corner_logo_alpha > 0:
            corner_logo_draw = corner_logo.copy()
            corner_logo_draw.set_alpha(corner_logo_alpha)
            screen.blit(corner_logo_draw, (logo_margin, logo_margin))

        if ip_label_surface is not None and ip_label_alpha > 0:
            ip_label_draw = ip_label_surface.copy()
            ip_label_draw.set_alpha(ip_label_alpha)
            screen.blit(ip_label_draw, ip_label_pos)

        pygame.display.flip()
        fps_clock.tick(60)   # 60 FPS for smooth second-hand sweep

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
