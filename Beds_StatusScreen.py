# filepath: c:\Users\pscullion\OneDrive - Harpur Trust (Bedford School)\5_Code\Git\Bedford-Range-FeedbackScreen\Beds_StatusScreen.py

import pygame
import sys
import math
import time
import socket
import threading
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Colour palette – futuristic neon-on-dark theme
# ---------------------------------------------------------------------------
COL_BG            = (10,  12,  18)
COL_RING_OUTER    = (0,   220, 255)      # cyan glow
COL_RING_INNER    = (20,  30,  50)
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
COL_STATUS_AUT    = (20,  40,  160)       # blue  – device in automatic mode
LISTEN_PORT       = 5001

# ---------------------------------------------------------------------------
# Animation / easing helpers
# ---------------------------------------------------------------------------
INTRO_DURATION = 1.5 # seconds per phase (sweep-up / sweep-down)


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
# Each entry is a dict  {"status": "OFF"|"ACK", "extra": "..."}
# The mapping from array index to panel is:
#   0-5  → Lane Controller 1-6   (top row cols 0-5)
#   6-11 → Snap Target 1-6       (bottom row cols 0-5)
#   12   → Foyer Display         (top row col 6)
#   13   → Range Display         (bottom row col 6)
# ---------------------------------------------------------------------------
panel_statuses = [{"status": "OFF", "extra": ""} for _ in range(14)]
_status_lock   = threading.Lock()


def _network_listener():
    """Run in a daemon thread.  Accepts TCP connections and reads JSON arrays.

    Expected payload per connection:
        A JSON-encoded array of 14 strings.  Each string has the form
        ``"STATUS:extra_data"`` where STATUS is ``OFF`` or ``ACK``.
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
                arr = json.loads(data.decode("utf-8"))
                if isinstance(arr, list) and len(arr) >= 14:
                    with _status_lock:
                        for i in range(14):
                            parts = str(arr[i]).split(":", 1)
                            status = parts[0].strip().upper()
                            extra  = parts[1].strip() if len(parts) > 1 else ""
                            panel_statuses[i] = {
                                "status": status,
                                "extra":  extra,
                            }
        except Exception:
            pass  # silently ignore malformed messages
        finally:
            conn.close()


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
TOAST_FADE_OUT = 0.4   # fraction of TOAST_DURATION used for fade-out


class ScoreToast:
    """Represents one animating score pop-up for a lane."""
    def __init__(self, lane: int, score: str, start_y: int, travel: int):
        self.lane    = lane        # 1-based lane number
        self.score   = score       # score string
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
        if p < TOAST_FADE_IN:
            return int(255 * (p / TOAST_FADE_IN))
        elif p > 1.0 - TOAST_FADE_OUT:
            return int(255 * ((1.0 - p) / TOAST_FADE_OUT))
        return 255

    def current_y(self) -> int:
        return int(self.start_y - self.travel * self.progress())


# Track the last-seen extra value per lane (indices 0-5) to detect new scores
_last_extra = [""] * 6


def poll_score_toasts(toasts: list, start_y: int, travel: int):
    """Check panel_statuses for new AUT score messages and spawn toasts."""
    global _last_extra
    with _status_lock:
        snapshot = [(panel_statuses[i]["status"], panel_statuses[i]["extra"])
                    for i in range(6)]
    for i, (status, extra) in enumerate(snapshot):
        if status == "AUT" and extra and extra != "ok" and extra != _last_extra[i]:
            _last_extra[i] = extra
            toasts.append(ScoreToast(lane=i + 1, score=extra,
                                     start_y=start_y, travel=travel))


# ---------------------------------------------------------------------------
# Build the static clock-face surface (drawn once for performance)
# ---------------------------------------------------------------------------
def build_face(screen_w, screen_h, cx, cy, clock_radius):
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

    # Hour numbers
    num_font_size = max(18, int(clock_radius * 0.13))
    num_font = pygame.font.SysFont("Consolas", num_font_size, bold=True)
    for hour in range(1, 13):
        angle = hour * 30
        pos   = polar_to_cart(cx, cy, angle, clock_radius - 60)
        txt   = num_font.render(str(hour), True, COL_NUMBER)
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

    fps_clock = pygame.time.Clock()

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

    screen_border = 50                                  # 50 px border L/R/B
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
    cx = screen_w // 3          # centre of the left third
    cy = panel_area_y // 2      # centred in the space above the panels

    # Pre-render the static face
    face_surf = build_face(screen_w, screen_h, cx, cy, clock_radius)

    # Fonts
    digital_font = pygame.font.SysFont("Consolas", max(16, int(clock_radius * 0.10)))
    date_font    = pygame.font.SysFont("Consolas", max(14, int(clock_radius * 0.065)))
    label_font   = pygame.font.SysFont("Consolas", max(12, int(clock_radius * 0.05)))
    panel_font   = pygame.font.SysFont("Consolas", max(13, int(clock_radius * 0.055)))

    # Toast fonts – used in the right-hand score area
    toast_lane_font  = pygame.font.SysFont("Consolas", max(22, int(clock_radius * 0.13)), bold=True)
    toast_score_font = pygame.font.SysFont("Consolas", max(60, int(clock_radius * 0.38)), bold=True)

    # Score toast state
    # Toasts rise from the bottom of the upper content area (panel_area_y) upward
    toast_start_y  = panel_area_y - 20        # y-centre where a new toast appears
    toast_travel   = int(panel_area_y * 0.55) # upward travel in pixels over lifetime
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

        # --- draw ----------------------------------------------------
        screen.fill(COL_BG)
        screen.blit(face_surf, (0, 0))

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
        poll_score_toasts(score_toasts, toast_start_y, toast_travel)
        score_toasts[:] = [t for t in score_toasts if t.alive]

        # Right-hand area: from cx to screen right, top to panel_area_y
        toast_area_x      = cx + screen_border // 2
        toast_area_w      = screen_w - toast_area_x - screen_border // 2
        toast_area_top    = 10
        toast_area_bottom = panel_area_y - 10

        for toast in score_toasts:
            a = toast.alpha()
            cy_toast = toast.current_y()

            # Measure text
            lane_str  = f"LANE {toast.lane}"
            score_str = toast.score

            lane_surf  = toast_lane_font.render(lane_str,  True, (180, 220, 255))
            score_surf = toast_score_font.render(score_str, True, (255, 255, 100))

            total_h = lane_surf.get_height() + score_surf.get_height() + 4
            # Clamp so toast never clips top or bottom of area
            cy_toast = max(toast_area_top  + total_h // 2,
                           min(cy_toast, toast_area_bottom - total_h // 2))

            lane_rect  = lane_surf.get_rect(
                centerx=toast_area_x + toast_area_w // 2,
                bottom=cy_toast - 2)
            score_rect = score_surf.get_rect(
                centerx=toast_area_x + toast_area_w // 2,
                top=cy_toast + 2)

            # Draw onto a per-toast SRCALPHA surface for alpha blending
            toast_surf = pygame.Surface((toast_area_w, total_h + 20), pygame.SRCALPHA)
            off_x = toast_area_x
            off_y = cy_toast - total_h // 2 - 10

            # Lane label
            ls_alpha = lane_surf.copy()
            ls_alpha.set_alpha(a)
            screen.blit(ls_alpha, lane_rect)

            # Score value
            ss_alpha = score_surf.copy()
            ss_alpha.set_alpha(a)
            screen.blit(ss_alpha, score_rect)

        # ----- bottom status panels ----------------------------------
        # Top row: cols 0-5 → status indices 0-5, col 6 → index 12
        for col, (rect, label) in enumerate(zip(panel_rects_top, panel_labels_top)):
            idx = col if col < 6 else 12
            draw_panel(screen, rect, label, panel_font, bg_col=_status_bg_colour(idx))
        # Bottom row: cols 0-5 → status indices 6-11, col 6 → index 13
        for col, (rect, label) in enumerate(zip(panel_rects_bot, panel_labels_bot)):
            idx = col + 6 if col < 6 else 13
            draw_panel(screen, rect, label, panel_font, bg_col=_status_bg_colour(idx))

        pygame.display.flip()
        fps_clock.tick(60)   # 60 FPS for smooth second-hand sweep

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
