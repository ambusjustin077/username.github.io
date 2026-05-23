import kivy.app
import kivy.uix.widget
import kivy.uix.label
import kivy.uix.button
import kivy.uix.floatlayout
import kivy.uix.gridlayout
import kivy.uix.boxlayout
import kivy.uix.screenmanager
import kivy.core.window
import kivy.graphics
import kivy.clock
import kivy.utils
import kivy.properties
import kivy.uix.textinput
import kivy.uix.popup
import kivy.uix.image
import kivy.uix.behaviors
import kivy.animation
import json
import math
import os
import struct
import wave
import datetime  # Changed from "from datetime import datetime"


def _app_writable_root(app=None):
    """Writable directory for saves and generated audio.

    The iOS app bundle (paths next to this file) is read-only; use Kivy's
    user_data_dir on iOS and Android. Desktop keeps files beside the script.
    """
    plat = kivy.utils.platform
    if plat in ("ios", "android"):
        app = app or kivy.app.App.get_running_app()
        if app is not None:
            d = app.user_data_dir
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
            return d
        import tempfile

        return tempfile.gettempdir()
    return os.path.abspath(os.path.dirname(__file__))


kivy.core.window.Window.clearcolor = (0.05, 0.05, 0.1, 1)
if kivy.utils.platform not in ("ios", "android"):
    kivy.core.window.Window.size = (900, 700)
    kivy.core.window.Window.fullscreen = "auto"


class GameState:
    MENU = 1
    PLAYING = 2
    GAME_OVER = 3
    LEVEL_COMPLETE = 4
    PAUSED = 5
    LEVEL_SELECT = 6
    LOGIN = 7
    REGISTER = 8
    INSTRUCTIONS = 9


class PowerUpType:
    SLOW_MOTION = 1
    GIANT_BALL = 2
    MULTI_BALL = 3
    MAGNET = 4
    LASER = 5
    SHIELD = 6
    SUPER_BOUNCE = 7

    _names = {
        1: "SLOW_MOTION",
        2: "GIANT_BALL",
        3: "MULTI_BALL",
        4: "MAGNET",
        5: "LASER",
        6: "SHIELD",
        7: "SUPER_BOUNCE"
    }

    @classmethod
    def get_name(cls, value):
        return cls._names.get(value, "UNKNOWN")


class SimpleRandom:
    def __init__(self, seed=1):
        self.seed = seed

    def random(self):
        self.seed = (self.seed * 1103515245 + 12345) & 0xFFFFFFFF
        return self.seed / 0xFFFFFFFF

    def choice(self, items):
        index = int(self.random() * len(items))
        return items[index]

    def randint(self, a, b):
        return a + int(self.random() * (b - a + 1))

    def uniform(self, a, b):
        return a + self.random() * (b - a)


rnd = SimpleRandom(42)

_BGM_ASSET_VERSION = 6


def _synthesize_loop_wav(path, style):
    """Write a short mono PCM WAV loop — Game Boy / DMG-style chiptune (pulse + pulse + tri + noise)."""
    rate = 22050
    beats = 8

    def pulse(ph, duty):
        p = ph - math.floor(ph)
        return 1.0 if p < duty else -1.0

    def tri_wave(ph):
        p = ph - math.floor(ph)
        return -1.0 + 4.0 * p if p < 0.5 else 3.0 - 4.0 * p

    if style == "lobby":
        bpm = 92
        drive = 0.22
    else:
        bpm = 118
        drive = 0.26

    duties = (0.125, 0.25, 0.5, 0.75)
    spb = int(round(rate * 60 / bpm))
    if spb <= 0:
        spb = rate // 2
    n = beats * spb
    lfsr = [0x7FFF]
    samples = []
    for i in range(n):
        beat = i // spb
        pos = i % spb
        t = i / rate
        duty = duties[beat % 4]
        sp16 = max(1, spb // 16)
        step = (pos // sp16) % 16

        if style == "lobby":
            mel_notes = [523.25, 659.25, 783.99, 659.25, 587.33, 493.88, 440.0, 493.88]
            f1 = mel_notes[beat % len(mel_notes)]
            arp_i = (pos // max(1, spb // 6)) % 3
            arp_f = [f1, f1 * 1.2599, f1 * 1.4983][arp_i]
            ph1 = t * arp_f
            sq1 = 0.38 * pulse(ph1, duty)
            f2 = [196.0, 174.61, 164.81, 174.61][beat % 4]
            ph2 = t * f2
            sq2 = 0.28 * pulse(ph2, 0.5)
            fbass = [130.81, 146.83, 130.81, 116.54][beat % 4]
            tri_b = 0.32 * tri_wave(t * fbass * 0.5)
            x = lfsr[0]
            bit = ((x >> 1) ^ (x >> 13)) & 1
            lfsr[0] = (x >> 1) | (bit << 14)
            nz = 2.0 * bit - 1.0
            nk = max(1, spb // 10)
            kenv = max(0.0, 1.0 - pos / nk) if pos < nk else 0.0
            hat = 0.0
            if step % 4 == 2:
                he = math.sin(math.pi * (pos % sp16) / sp16)
                hat = 0.08 * he * nz
            kick_nz = 0.12 * kenv * nz if beat % 2 == 0 else 0.06 * kenv * nz
            s = drive * (sq1 + sq2 + tri_b + kick_nz + hat)
        else:
            mel = [659.25, 783.99, 880.0, 783.99, 739.99, 659.25, 587.33, 659.25]
            f1 = mel[beat % len(mel)]
            arp_i = (pos // max(1, spb // 8)) % 4
            arp_f = [f1, f1 * 1.122, f1 * 1.335, f1 * 1.498][arp_i]
            ph1 = t * arp_f
            sq1 = 0.4 * pulse(ph1, duties[(beat + 1) % 4])
            f2 = [392.0, 369.99, 329.63, 293.66, 329.63, 349.23, 392.0, 440.0][beat % 8]
            ph2 = t * f2
            sq2 = 0.22 * pulse(ph2, 0.25)
            fb = [98.0, 87.31, 98.0, 110.0, 98.0, 87.31, 82.41, 87.31][beat % 8]
            tri_b = 0.34 * tri_wave(t * fb)
            x = lfsr[0]
            bit = ((x >> 1) ^ (x >> 13)) & 1
            lfsr[0] = (x >> 1) | (bit << 14)
            nz = 2.0 * bit - 1.0
            nk = max(1, spb // 14)
            kenv = max(0.0, 1.0 - pos / nk) if pos < nk else 0.0
            kick = 0.14 * kenv * nz
            sk = max(1, spb // 12)
            sn = 0.0
            if beat % 4 == 2 and pos < sk:
                se = 1.0 - pos / sk
                sn = 0.12 * se * nz
            hh = 0.0
            if step % 2 == 0:
                he = math.sin(math.pi * (pos % sp16) / sp16)
                hh = 0.07 * he * nz
            s = drive * (sq1 + sq2 + tri_b + kick + sn + hh)

        samples.append(max(-1.0, min(1.0, s)))

    peak = max((abs(x) for x in samples), default=1.0) or 1.0
    fade = min(400, n // 8)
    for i in range(fade):
        samples[i] *= i / fade
        samples[n - 1 - i] *= i / fade
    framed = [int(30000 * x / peak) for x in samples]
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, v))) for v in framed))


def _synthesize_ui_click_wav(path):
    """Short soft UI click — clear feedback without being sharp or loud."""
    rate = 22050
    dur = 0.045
    n = int(rate * dur)
    samples = []
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 55.0)
        f0 = 880.0 * math.exp(-t * 28.0) + 220.0
        tick = env * math.sin(2 * math.pi * f0 * t)
        tick += 0.22 * math.exp(-t * 90.0) * math.sin(2 * math.pi * 2100.0 * t)
        samples.append(max(-1.0, min(1.0, 0.55 * tick)))
    peak = max((abs(x) for x in samples), default=1.0) or 1.0
    framed = [int(24000 * x / peak) for x in samples]
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, v))) for v in framed))


def _synthesize_target_hit_wav(path):
    """Short sci-fi impact when the ball or laser hits a brick."""
    rate = 22050
    dur = 0.1
    n = int(rate * dur)
    samples = []
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 28.0)
        fc = 1050.0 * math.exp(-t * 22.0) + 320.0
        body = env * math.sin(2 * math.pi * fc * t)
        ring = 0.38 * math.exp(-t * 38.0) * math.sin(2 * math.pi * fc * 1.498 * t + 1.4 * math.sin(2 * math.pi * 7.0 * t))
        sparkle = 0.18 * math.exp(-t * 70.0) * math.sin(2 * math.pi * 2400.0 * t)
        samples.append(max(-1.0, min(1.0, 0.62 * (body + ring) + sparkle)))
    peak = max((abs(x) for x in samples), default=1.0) or 1.0
    framed = [int(26000 * x / peak) for x in samples]
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, v))) for v in framed))


def ensure_bgm_wav_files(app=None):
    audio_dir = os.path.join(_app_writable_root(app), "audio")
    os.makedirs(audio_dir, exist_ok=True)
    menu_mp3 = os.path.join(audio_dir, "bgm_menu.mp3")
    menu_wav = os.path.join(audio_dir, "bgm_menu.wav")
    game_wav = os.path.join(audio_dir, "bgm_game.wav")
    click_path = os.path.join(audio_dir, "ui_click.wav")
    hit_path = os.path.join(audio_dir, "target_hit.wav")
    version_path = os.path.join(audio_dir, "bgm_version.txt")
    has_menu = os.path.isfile(menu_mp3) or os.path.isfile(menu_wav)
    need = (
        (not has_menu)
        or (not os.path.isfile(game_wav))
        or (not os.path.isfile(click_path))
        or (not os.path.isfile(hit_path))
    )
    if not need:
        try:
            with open(version_path, "r", encoding="utf-8") as vf:
                need = int(vf.read().strip()) != _BGM_ASSET_VERSION
        except Exception:
            need = True
    if need:
        if not os.path.isfile(menu_mp3):
            _synthesize_loop_wav(menu_wav, "lobby")
        _synthesize_loop_wav(game_wav, "action")
        _synthesize_ui_click_wav(click_path)
        _synthesize_target_hit_wav(hit_path)
        try:
            with open(version_path, "w", encoding="utf-8") as vf:
                vf.write(str(_BGM_ASSET_VERSION))
        except Exception:
            pass


class BackgroundMusic:
    def __init__(self):
        self.menu_sound = None
        self.game_sound = None
        self._active = None
        self.bgm_muted = False
        self._vol_menu = 0.28
        self._vol_game = 0.3

    def load(self):
        try:
            from kivy.core.audio import SoundLoader
        except Exception:
            return
        base = os.path.join(_app_writable_root(), "audio")
        menu_mp3 = os.path.join(base, "bgm_menu.mp3")
        menu_wav = os.path.join(base, "bgm_menu.wav")
        game_wav = os.path.join(base, "bgm_game.wav")
        self.menu_sound = None
        if os.path.isfile(menu_mp3):
            self.menu_sound = SoundLoader.load(menu_mp3)
        if self.menu_sound is None and os.path.isfile(menu_wav):
            self.menu_sound = SoundLoader.load(menu_wav)
        self.game_sound = SoundLoader.load(game_wav) if os.path.isfile(game_wav) else None
        if self.menu_sound:
            self.menu_sound.loop = True
        if self.game_sound:
            self.game_sound.loop = True
        self.apply_bgm_mute()

    def apply_bgm_mute(self):
        vm = 0.0 if self.bgm_muted else self._vol_menu
        vg = 0.0 if self.bgm_muted else self._vol_game
        if self.menu_sound:
            try:
                self.menu_sound.volume = vm
            except Exception:
                pass
        if self.game_sound:
            try:
                self.game_sound.volume = vg
            except Exception:
                pass

    def stop_all(self):
        for s in (self.menu_sound, self.game_sound):
            if s:
                try:
                    s.stop()
                except Exception:
                    pass
        self._active = None

    def sync(self, screen_name, game_state):
        want_game = (
            screen_name == "game"
            and game_state == GameState.PLAYING
            and self.game_sound is not None
        )
        want = "game" if want_game else "menu"
        if want == self._active:
            return
        self.stop_all()
        self._active = want
        if want == "game" and self.game_sound:
            self.game_sound.play()
        elif self.menu_sound:
            self.menu_sound.play()
        elif self.game_sound:
            self.game_sound.play()
        self.apply_bgm_mute()


_ui_click_sound = None


def play_ui_click():
    global _ui_click_sound
    try:
        from kivy.core.audio import SoundLoader
    except Exception:
        return
    if _ui_click_sound is None:
        p = os.path.join(_app_writable_root(), "audio", "ui_click.wav")
        if not os.path.isfile(p):
            try:
                _synthesize_ui_click_wav(p)
            except Exception:
                return
        _ui_click_sound = SoundLoader.load(p)
        if _ui_click_sound:
            _ui_click_sound.volume = 0.42
    if _ui_click_sound:
        try:
            _ui_click_sound.stop()
            _ui_click_sound.play()
        except Exception:
            pass


_target_hit_pool = []
_target_hit_i = 0


def play_target_hit():
    global _target_hit_pool, _target_hit_i
    try:
        from kivy.core.audio import SoundLoader
    except Exception:
        return
    if not _target_hit_pool:
        p = os.path.join(_app_writable_root(), "audio", "target_hit.wav")
        if not os.path.isfile(p):
            try:
                _synthesize_target_hit_wav(p)
            except Exception:
                return
        for _ in range(4):
            s = SoundLoader.load(p)
            if s:
                s.volume = 0.38
                _target_hit_pool.append(s)
        if not _target_hit_pool:
            return
    s = _target_hit_pool[_target_hit_i % len(_target_hit_pool)]
    _target_hit_i += 1
    try:
        s.stop()
        s.play()
    except Exception:
        pass


def simple_sin(x):
    x = x % (2 * 3.14159)
    if x > 3.14159:
        x = 2 * 3.14159 - x
    x2 = x * x
    x3 = x2 * x
    x5 = x3 * x2
    return x - x3 / 6 + x5 / 120


class Star:
    def __init__(self, x, y, size, speed, angle=0):
        self.x = x
        self.y = y
        self.size = size
        self.speed = speed
        self.angle = angle
        self.twinkle_speed = 0.5 + speed * 2
        self.trail = []

    def update(self, width, height, dt):
        self.y -= self.speed * 60 * dt
        self.angle += 0.05 * self.speed
        if self.y < -10:
            self.y = height + 10
            self.x = (self.x + rnd.randint(-50, 50)) % width
            if rnd.random() < 0.05:
                self.speed = rnd.uniform(5, 15)
                self.size = rnd.randint(2, 5)
            else:
                self.speed = rnd.uniform(0.5, 3)
                self.size = rnd.randint(1, 3)
        elif self.y > height + 10:
            self.y = -10


class Nebula:
    def __init__(self, x, y, width, height, color, speed):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.speed = speed

    def update(self, dt):
        self.x -= self.speed * 60 * dt
        if self.x < -self.width:
            self.x = kivy.core.window.Window.width


class GradientBackground(kivy.uix.widget.Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stars = []
        self.nebulas = []
        self.time = 0
        self.init_background()
        kivy.clock.Clock.schedule_interval(self.update_background, 1.0 / 60.0)

    def init_background(self):
        for i in range(200):
            x = rnd.uniform(0, kivy.core.window.Window.width)
            y = rnd.uniform(0, kivy.core.window.Window.height)
            size = rnd.randint(1, 3)
            speed = rnd.uniform(0.2, 3)
            self.stars.append(Star(x, y, size, speed))

        nebula_colors = [
            (0.5, 0.2, 0.7, 0.2),
            (0.2, 0.3, 0.8, 0.18),
            (0.7, 0.3, 0.4, 0.15),
            (0.3, 0.6, 0.3, 0.12),
            (0.8, 0.4, 0.2, 0.1),
        ]
        for i in range(6):
            self.nebulas.append(Nebula(
                rnd.uniform(-300, kivy.core.window.Window.width),
                rnd.uniform(0, kivy.core.window.Window.height),
                rnd.randint(200, 500),
                rnd.randint(150, 300),
                nebula_colors[i % len(nebula_colors)],
                rnd.uniform(0.05, 0.3)
            ))

    def update_background(self, dt):
        self.time += dt
        for star in self.stars:
            star.update(kivy.core.window.Window.width, kivy.core.window.Window.height, dt)
        for nebula in self.nebulas:
            nebula.update(dt)
        self.canvas.clear()
        self.draw()

    def draw(self):
        with self.canvas:
            for i in range(0, kivy.core.window.Window.height, 2):
                color_val = 0.02 + (i / kivy.core.window.Window.height) * 0.1
                kivy.graphics.Color(color_val, color_val * 0.7, color_val * 1.2)
                kivy.graphics.Rectangle(pos=(0, i), size=(kivy.core.window.Window.width, 2))

            for nebula in self.nebulas:
                kivy.graphics.Color(*nebula.color)
                kivy.graphics.Ellipse(pos=(nebula.x, nebula.y),
                                      size=(nebula.width, nebula.height))

            for star in self.stars:
                twinkle = 0.4 + 0.6 * abs(simple_sin(self.time * star.twinkle_speed + star.angle))
                if star.speed > 1.5:
                    kivy.graphics.Color(0.7, 0.8, 1.0, twinkle)
                elif star.speed > 0.8:
                    kivy.graphics.Color(1.0, 1.0, 0.9, twinkle)
                else:
                    kivy.graphics.Color(1.0, 0.9, 0.7, twinkle)

                if star.size > 2:
                    kivy.graphics.Color(1, 1, 1, 0.2)
                    kivy.graphics.Ellipse(pos=(star.x - star.size / 2, star.y - star.size / 2),
                                          size=(star.size * 2, star.size * 2))

                kivy.graphics.Ellipse(pos=(star.x - star.size / 2, star.y - star.size / 2),
                                      size=(star.size, star.size))


class IconButton(kivy.uix.button.Button):
    def __init__(self, icon="", text="", **kwargs):
        if icon and text:
            button_text = f"{icon}  {text}"
        elif icon:
            button_text = icon
        else:
            button_text = text

        super().__init__(text=button_text, **kwargs)
        self.background_normal = ''
        self.background_color = kwargs.get('background_color', (0.2, 0.2, 0.3, 1))
        self.font_size = kwargs.get('font_size', 24)
        self.bold = True
        self.color = (1, 1, 1, 1)
        self.bind(on_press=self.on_press_animation)

    def on_press_animation(self, instance):
        play_ui_click()
        anim = kivy.animation.Animation(background_color=(0.5, 0.5, 0.7, 1), duration=0.1)
        anim.bind(
            on_complete=lambda *args: kivy.animation.Animation(background_color=self.background_color,
                                                               duration=0.1).start(
                self))
        anim.start(self)


class GlowButton(kivy.uix.button.Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0.2, 0.2, 0.3, 1)
        self.font_size = kwargs.get('font_size', 24)
        self.bold = True
        self.color = (1, 1, 1, 1)
        self.bind(on_press=self.on_press_animation)

    def on_press_animation(self, instance):
        play_ui_click()
        anim = kivy.animation.Animation(background_color=(0.5, 0.5, 0.7, 1), duration=0.1)
        anim.bind(
            on_complete=lambda *args: kivy.animation.Animation(background_color=(0.2, 0.2, 0.3, 1), duration=0.1).start(
                self))
        anim.start(self)


class GlowTextInput(kivy.uix.textinput.TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0.15, 0.15, 0.25, 1)
        self.foreground_color = (1, 1, 1, 1)
        self.cursor_color = (0, 1, 1, 1)
        self.hint_text_color = (0.6, 0.6, 0.8, 1)
        self.font_size = kwargs.get('font_size', 20)
        self.padding = [15, 12, 15, 12]
        self.border = (10, 10, 10, 10)
        self.bind(focus=self.on_focus)

    def on_focus(self, instance, value):
        if value:
            anim = kivy.animation.Animation(background_color=(0.25, 0.25, 0.4, 1), duration=0.2)
            anim.start(self)
        else:
            anim = kivy.animation.Animation(background_color=(0.15, 0.15, 0.25, 1), duration=0.2)
            anim.start(self)


class AnimatedTitle(kivy.uix.label.Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = kwargs.get('font_size', 72)
        self.bold = True
        self.color = (0, 1, 1, 1)
        self.pulse_anim = kivy.animation.Animation(color=(0.5, 1, 1, 1), duration=1.5) + \
                          kivy.animation.Animation(color=(0, 1, 1, 1), duration=1.5)
        self.pulse_anim.repeat = True
        self.pulse_anim.start(self)


class UserManager:
    def __init__(self):
        self.data_file = os.path.join(_app_writable_root(), "user_data.json")
        self.users = {}
        self.scores = {}
        self.current_user = None
        self.load_data()

    def default_score_data(self):
        return {
            "high_score": 0,
            "total_games": 0,
            "total_score": 0,
            "games_won": 0,
            "best_combo": 0,
            "levels_completed": [False, False, False]
        }

    def ensure_default_users(self):
        if "guest" not in self.users:
            self.users["guest"] = {"password": "guest", "created": "2024-01-01 00:00:00"}
        if "guest" not in self.scores:
            self.scores["guest"] = self.default_score_data()

        if "player1" not in self.users:
            self.users["player1"] = {"password": "1234", "created": "2024-01-01 00:00:00"}
        if "player1" not in self.scores:
            self.scores["player1"] = self.default_score_data()

        if "Guest" in self.scores:
            old_guest = self.scores.pop("Guest")
            guest_scores = self.scores["guest"]
            guest_scores["high_score"] = max(guest_scores["high_score"], old_guest.get("high_score", 0))
            guest_scores["total_games"] += old_guest.get("total_games", 0)
            guest_scores["total_score"] += old_guest.get("total_score", 0)
            guest_scores["games_won"] += old_guest.get("games_won", 0)
            guest_scores["best_combo"] = max(guest_scores["best_combo"], old_guest.get("best_combo", 0))
            old_levels = old_guest.get("levels_completed", [False, False, False])
            guest_levels = guest_scores["levels_completed"]
            guest_scores["levels_completed"] = [
                bool(guest_levels[i] or old_levels[i]) for i in range(len(guest_levels))
            ]
            self.users.pop("Guest", None)

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as file:
                    data = json.load(file)
                self.users = data.get("users", {})
                self.scores = data.get("scores", {})
            except (OSError, json.JSONDecodeError):
                self.users = {}
                self.scores = {}

        self.ensure_default_users()
        self.save_data()

    def save_data(self):
        data = {"users": self.users, "scores": self.scores}
        with open(self.data_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    def create_timestamp(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Changed from datetime.now()

    def ensure_user_score(self, username):
        if username not in self.scores:
            self.scores[username] = self.default_score_data()

    def register(self, username, password, confirm_password):
        username = username.strip()
        if not username or not password:
            return False, "Username and password cannot be empty"
        if len(username) < 3:
            return False, "Username must be at least 3 characters"
        if len(password) < 4:
            return False, "Password must be at least 4 characters"
        if password != confirm_password:
            return False, "Passwords do not match"
        if username in self.users:
            return False, "Username already exists"

        self.users[username] = {"password": password, "created": self.create_timestamp()}
        self.ensure_user_score(username)
        self.save_data()
        return True, "Registration successful!"

    def login(self, username, password):
        username = username.strip()
        if username.lower() == "guest":
            username = "guest"
        if username in self.users and self.users[username]["password"] == password:
            self.current_user = username
            self.ensure_user_score(username)
            self.save_data()
            return True, "Login successful!"
        return False, "Invalid username or password"

    def logout(self):
        self.current_user = None
        self.save_data()

    def update_score(self, score, level, combo, completed):
        if self.current_user and self.current_user in self.scores:
            user_scores = self.scores[self.current_user]
            user_scores["total_games"] += 1
            user_scores["total_score"] += score
            if score > user_scores["high_score"]:
                user_scores["high_score"] = score
            if combo > user_scores["best_combo"]:
                user_scores["best_combo"] = combo
            if completed:
                user_scores["games_won"] += 1
                if level < len(user_scores["levels_completed"]):
                    user_scores["levels_completed"][level] = True
            self.save_data()

    def get_stats(self):
        if self.current_user and self.current_user in self.scores:
            stats = self.scores[self.current_user]
            avg_score = stats["total_score"] // stats["total_games"] if stats["total_games"] > 0 else 0
            win_rate = (stats["games_won"] / stats["total_games"] * 100) if stats["total_games"] > 0 else 0
            return {
                "high_score": stats["high_score"],
                "total_games": stats["total_games"],
                "avg_score": avg_score,
                "win_rate": win_rate,
                "best_combo": stats["best_combo"],
                "levels_completed": stats["levels_completed"]
            }
        return None


class GameWidget(kivy.uix.widget.Widget):
    game = kivy.properties.ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._keyboard = None
        self.ensure_keyboard()

        self.pressed_keys = set()
        self.game_area = {
            'x': 0,
            'y': 60,
            'width': kivy.core.window.Window.width,
            'height': kivy.core.window.Window.height - 60
        }

        self.stars = []
        for i in range(300):
            x = rnd.uniform(0, kivy.core.window.Window.width)
            y = rnd.uniform(0, kivy.core.window.Window.height)
            size = rnd.randint(1, 4)
            speed = rnd.uniform(0.3, 4)
            self.stars.append(Star(x, y, size, speed))

        self.nebulas = []
        nebula_colors = [
            (0.4, 0.2, 0.6, 0.15),
            (0.2, 0.3, 0.7, 0.12),
            (0.6, 0.2, 0.3, 0.1),
            (0.3, 0.6, 0.2, 0.08),
        ]
        for i in range(5):
            self.nebulas.append(Nebula(
                rnd.uniform(-200, kivy.core.window.Window.width),
                rnd.uniform(0, kivy.core.window.Window.height - 100),
                rnd.randint(150, 400),
                rnd.randint(100, 250),
                nebula_colors[i % len(nebula_colors)],
                rnd.uniform(0.1, 0.5)
            ))

        self.time = 0
        kivy.clock.Clock.schedule_interval(self.update, 1.0 / 60.0)
        kivy.core.window.Window.bind(on_resize=self.on_window_resize)

    def ensure_keyboard(self):
        if self._keyboard:
            return
        self._keyboard = kivy.core.window.Window.request_keyboard(self._keyboard_closed, self)
        if self._keyboard:
            self._keyboard.bind(on_key_down=self._on_key_down)
            self._keyboard.bind(on_key_up=self._on_key_up)

    def on_window_resize(self, window, width, height):
        self.game_area['width'] = width
        self.game_area['height'] = height - 60
        self.game_area['x'] = 0
        self.game_area['y'] = 60

        self.stars = []
        for i in range(300):
            x = rnd.uniform(0, width)
            y = rnd.uniform(0, height)
            size = rnd.randint(1, 4)
            speed = rnd.uniform(0.3, 4)
            self.stars.append(Star(x, y, size, speed))

        if self.game:
            self.game.update_positions(width, height)

    def _keyboard_closed(self, *args):
        if not self._keyboard:
            return
        self._keyboard.unbind(on_key_down=self._on_key_down)
        self._keyboard.unbind(on_key_up=self._on_key_up)
        self._keyboard = None

    def _on_key_down(self, keyboard, keycode, text, modifiers):
        if not self.game:
            return True

        key_name = keycode[1] if keycode and len(keycode) > 1 else None
        if key_name:
            self.pressed_keys.add(key_name)

        is_space = (
            key_name in ('spacebar', 'space') or
            key_name == ' ' or
            text == ' '
        )
        if is_space:
            if self.game.state == GameState.PLAYING:
                launched = False
                launch_speed_x, launch_speed_y = self.game.get_ball_launch_speed()
                for ball in self.game.balls:
                    if ball.attached:
                        ball.launch(launch_speed_x, launch_speed_y)
                        launched = True
                if self.game.power_up_active == PowerUpType.LASER and not launched:
                    self.game.paddle.shoot_laser()

        elif key_name == 'p':
            if self.game.state == GameState.PLAYING:
                self.game.state = GameState.PAUSED
            elif self.game.state == GameState.PAUSED:
                self.game.state = GameState.PLAYING

        elif key_name in ('escape', 'esc'):
            if self.game.state == GameState.PLAYING:
                self.game.state = GameState.PAUSED
            elif self.game.state == GameState.PAUSED:
                self.game.state = GameState.PLAYING

        elif key_name == 'r' and self.game.state == GameState.GAME_OVER:
            self.game.reset_game()
            self.game.state = GameState.PLAYING

        elif key_name == 'n' and self.game.state == GameState.LEVEL_COMPLETE:
            self.game.next_level()

        elif key_name == 'i':
            if self.game.state == GameState.PLAYING:
                self.game.state = GameState.INSTRUCTIONS

        return True

    def _on_key_up(self, keyboard, keycode):
        key_name = keycode[1] if keycode and len(keycode) > 1 else None
        if key_name:
            self.pressed_keys.discard(key_name)
        return True

    def update(self, dt):
        self.time += dt
        for star in self.stars:
            star.update(self.game_area['width'], self.game_area['height'], dt)
        for nebula in self.nebulas:
            nebula.update(dt)

        if not self.game:
            return

        if self.game.state == GameState.PLAYING:
            if 'left' in self.pressed_keys:
                self.game.paddle.move_left()
            if 'right' in self.pressed_keys:
                self.game.paddle.move_right(self.game_area['width'])
            self.game.update(self.game_area)

        self.canvas.clear()
        self.draw()

    def draw(self):
        if not self.game:
            return

        with self.canvas:
            for i in range(0, int(self.game_area['height']), 2):
                color_val = 0.02 + (i / self.game_area['height']) * 0.08
                kivy.graphics.Color(color_val, color_val * 0.8, color_val * 1.2)
                kivy.graphics.Rectangle(pos=(self.game_area['x'], self.game_area['y'] + i),
                                        size=(self.game_area['width'], 2))

            for nebula in self.nebulas:
                kivy.graphics.Color(*nebula.color)
                kivy.graphics.Ellipse(pos=(nebula.x, nebula.y),
                                      size=(nebula.width, nebula.height))

            for star in self.stars:
                twinkle = 0.4 + 0.6 * abs(simple_sin(self.time * star.twinkle_speed + star.angle))
                if star.speed > 2:
                    kivy.graphics.Color(0.8, 0.9, 1.0, twinkle)
                elif star.speed > 1:
                    kivy.graphics.Color(1.0, 1.0, 0.9, twinkle)
                else:
                    kivy.graphics.Color(1.0, 0.9, 0.7, twinkle)

                if star.size > 2:
                    kivy.graphics.Color(1, 1, 1, 0.3)
                    kivy.graphics.Ellipse(pos=(star.x - star.size / 2, star.y - star.size / 2),
                                          size=(star.size * 2, star.size * 2))
                    kivy.graphics.Color(1, 1, 1, twinkle)
                    kivy.graphics.Ellipse(pos=(star.x - star.size / 4, star.y - star.size / 4),
                                          size=(star.size * 1.5, star.size * 1.5))

                kivy.graphics.Color(1, 1, 1, twinkle)
                kivy.graphics.Ellipse(pos=(star.x - star.size / 2, star.y - star.size / 2),
                                      size=(star.size, star.size))

            if rnd.random() < 0.005:
                shooting_x = rnd.uniform(0, self.game_area['width'])
                shooting_y = rnd.uniform(self.game_area['height'] * 0.7, self.game_area['height'])
                for i in range(20):
                    alpha = 0.8 - i * 0.04
                    kivy.graphics.Color(1, 1, 0.5, alpha)
                    kivy.graphics.Line(points=[shooting_x - i * 5, shooting_y + i * 2,
                                               shooting_x - i * 8, shooting_y + i * 4],
                                       width=2)

            for brick in self.game.bricks:
                kivy.graphics.Color(*brick.color)
                kivy.graphics.RoundedRectangle(pos=brick.pos, size=brick.size, radius=[5])
                kivy.graphics.Color(1, 1, 1, 0.3)
                kivy.graphics.Line(rounded_rectangle=(brick.x, brick.y + 2, brick.width, 3, 5, 5, 5, 5), width=1)
                kivy.graphics.Color(1, 1, 1, 0.8)
                kivy.graphics.Line(rounded_rectangle=(brick.x, brick.y, brick.width, brick.height, 5, 5, 5, 5), width=2)

                if brick.max_hp > 1:
                    kivy.graphics.Color(1, 1, 1)
                    for i in range(brick.hp):
                        dot_x = brick.x + brick.width / 2 - (brick.hp * 5) + i * 10
                        kivy.graphics.Ellipse(pos=(dot_x, brick.y + brick.height - 8), size=(4, 4))

            for pu in self.game.power_ups:
                pulse = abs(simple_sin(pu.angle)) * 3
                kivy.graphics.Color(*pu.color[:3], 0.3)
                kivy.graphics.Ellipse(pos=(pu.x - 3 - pulse, pu.y - 3 - pulse),
                                      size=(pu.width + 6 + pulse * 2, pu.height + 6 + pulse * 2))
                kivy.graphics.Color(*pu.color)
                kivy.graphics.Ellipse(pos=pu.pos, size=pu.size)
                kivy.graphics.Color(1, 1, 1)
                kivy.graphics.Line(ellipse=(pu.x, pu.y, pu.width, pu.height), width=2)

            for ball in self.game.balls:
                for i, (tx, ty) in enumerate(ball.trail):
                    alpha = i / len(ball.trail) * 0.5
                    if ball.super_bounce:
                        kivy.graphics.Color(1, 0.84, 0, alpha)
                    else:
                        kivy.graphics.Color(*ball.color[:3], alpha)
                    kivy.graphics.Ellipse(pos=(tx - 10 + i / 2, ty - 10 + i / 2), size=(20 - i, 20 - i))

                if ball.super_bounce or ball.giant:
                    if ball.super_bounce:
                        kivy.graphics.Color(1, 0.84, 0, 0.2)
                    else:
                        kivy.graphics.Color(*ball.color[:3], 0.2)
                    glow_size = ball.width + 20
                    kivy.graphics.Ellipse(pos=(ball.x - 10, ball.y - 10), size=(glow_size, glow_size))

                if ball.shielded:
                    kivy.graphics.Color(0, 1, 1, 0.3)
                    kivy.graphics.Line(circle=(ball.x + 15, ball.y + 15, 20), width=2)

                if ball.super_bounce:
                    kivy.graphics.Color(1, 0.84, 0)
                elif ball.giant:
                    kivy.graphics.Color(1, 0.5, 0)
                else:
                    kivy.graphics.Color(*ball.color)
                kivy.graphics.Ellipse(pos=ball.pos, size=ball.size)
                kivy.graphics.Color(1, 1, 1, 0.5)
                kivy.graphics.Ellipse(pos=(ball.x + 5, ball.y + 20), size=(8, 8))

            if self.game.paddle.bounce_boost:
                kivy.graphics.Color(1, 0.84, 0)
            else:
                kivy.graphics.Color(*self.game.paddle.color)

            kivy.graphics.RoundedRectangle(pos=self.game.paddle.pos, size=self.game.paddle.size, radius=[10])
            kivy.graphics.Color(1, 1, 1, 0.3)
            kivy.graphics.RoundedRectangle(pos=(self.game.paddle.x, self.game.paddle.y + 15),
                                           size=(self.game.paddle.width, 3), radius=[5])
            kivy.graphics.Color(1, 1, 1)
            kivy.graphics.Line(rounded_rectangle=(self.game.paddle.x, self.game.paddle.y,
                                                  self.game.paddle.width, self.game.paddle.height, 10, 10, 10, 10),
                               width=2)

            for laser in self.game.paddle.lasers:
                kivy.graphics.Color(1, 0, 0)
                kivy.graphics.Rectangle(pos=(laser['x'], laser['y']),
                                        size=(laser['width'], laser['height']))
                kivy.graphics.Color(1, 0.5, 0)
                kivy.graphics.Line(rectangle=(laser['x'], laser['y'], laser['width'], laser['height']), width=1)


class Game:
    def __init__(self):
        self.game_area = {'width': 900, 'height': 640}
        self.reset_game()
        self.setup_levels()
        self.power_up_counter = 0
        self.user_manager = UserManager()

    def update_positions(self, screen_width, screen_height):
        self.game_area['width'] = screen_width
        self.game_area['height'] = screen_height - 60
        if self.paddle:
            self.paddle.center_paddle(self.game_area['width'])
            self.paddle.y = 50
        if self.bricks:
            self.create_level(self.current_level)
        for ball in self.balls:
            if ball.attached:
                ball.x = self.paddle.x + self.paddle.width / 2 - 15
                ball.y = self.paddle.y + 50

    def setup_levels(self):
        self.levels = [
            {"id": 0, "name": "EASY", "display_name": "EASY", "rows": 3, "cols": 6,
             "colors": [(0, 1, 0)], "hp_base": 1, "difficulty": 1, "ball_speed_x": 27, "ball_speed_y": 32,
             "description": "Perfect for beginners",
             "unlocked": True},
            {"id": 1, "name": "MEDIUM", "display_name": "MEDIUM", "rows": 4, "cols": 8,
             "colors": [(1, 1, 0)], "hp_base": 2, "difficulty": 2, "ball_speed_x": 50, "ball_speed_y": 55,
             "description": "For casual players",
             "unlocked": True},
            {"id": 2, "name": "HARD", "display_name": "HARD", "rows": 5, "cols": 10,
             "colors": [(1, 0, 0)], "hp_base": 3, "difficulty": 3, "ball_speed_x": 65, "ball_speed_y": 70,
             "description": "Challenge yourself!",
             "unlocked": True}
        ]

    def get_ball_launch_speed(self):
        level_data = self.levels[self.current_level]
        return level_data["ball_speed_x"], level_data["ball_speed_y"]

    def reset_game(self):
        self.paddle = Paddle()
        self.paddle.center_paddle(self.game_area['width'])
        self.paddle.y = 50
        ball_x = self.paddle.x + self.paddle.width / 2 - 15
        self.balls = [Ball(pos=(ball_x, self.paddle.y + 50))]
        self.bricks = []
        self.power_ups = []
        self.score = 0
        self.lives = 3
        self.state = GameState.MENU
        self.current_level = 0
        self.combo = 0
        self.combo_timer = 0
        self.max_combo = 0
        self.total_bounces = 0
        self.power_up_active = None
        self.power_up_timer = 0

    def create_level(self, level_id=None):
        if level_id is not None:
            self.current_level = level_id
        self.bricks = []
        level_data = self.levels[self.current_level]
        start_x = (self.game_area['width'] - (level_data["cols"] * 75)) / 2
        for row in range(level_data["rows"]):
            for col in range(level_data["cols"]):
                x = start_x + col * 75
                y = self.game_area['height'] - 100 - row * 30
                color = level_data["colors"][0]
                hp = level_data["hp_base"]
                points = 100 * level_data["hp_base"]
                self.bricks.append(Brick(x, y, color, hp, points))

    def start_level(self, level_id):
        self.current_level = level_id
        self.create_level(level_id)
        self.paddle.center_paddle(self.game_area['width'])
        self.paddle.y = 50
        ball_x = self.paddle.x + self.paddle.width / 2 - 15
        self.balls = [Ball(pos=(ball_x, self.paddle.y + 50))]
        self.lives = 3
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.total_bounces = 0
        self.state = GameState.PLAYING

    def next_level(self):
        if self.current_level + 1 < len(self.levels):
            self.current_level = self.current_level + 1
        else:
            self.current_level = 0
        self.create_level()
        self.paddle.center_paddle(self.game_area['width'])
        self.paddle.y = 50
        ball_x = self.paddle.x + self.paddle.width / 2 - 15
        self.balls = [Ball(pos=(ball_x, self.paddle.y + 50))]
        self.state = GameState.PLAYING

    def update(self, game_area):
        self.game_area = game_area
        if self.state != GameState.PLAYING:
            return

        if self.power_up_active:
            self.power_up_timer -= 1
            if self.power_up_timer <= 0:
                self.deactivate_power_up()

        for laser in self.paddle.lasers[:]:
            laser['y'] += 10
            if laser['y'] > self.game_area['height']:
                self.paddle.lasers.remove(laser)
            laser_rect = [laser['x'], laser['y'], laser['width'], laser['height']]
            for brick in self.bricks[:]:
                if (laser_rect[0] < brick.x + brick.width and
                        laser_rect[0] + laser_rect[2] > brick.x and
                        laser_rect[1] < brick.y + brick.height and
                        laser_rect[1] + laser_rect[3] > brick.y):
                    play_target_hit()
                    if brick.hit():
                        self.bricks.remove(brick)
                        self.score += brick.points
                    if laser in self.paddle.lasers:
                        self.paddle.lasers.remove(laser)
                    break

        for ball in self.balls[:]:
            ball.update_trail()
            if ball.attached:
                ball.x = self.paddle.x + self.paddle.width / 2 - 15
                continue
            ball.x += ball.vx
            ball.y += ball.vy

            if ball.x <= 0:
                ball.x = 0
                ball.vx = abs(ball.vx)
                self.total_bounces += 1
            elif ball.x >= self.game_area['width'] - ball.width:
                ball.x = self.game_area['width'] - ball.width
                ball.vx = -abs(ball.vx)
                self.total_bounces += 1
            if ball.y >= self.game_area['height'] - ball.height:
                ball.y = self.game_area['height'] - ball.height
                ball.vy = -abs(ball.vy)
                self.total_bounces += 1
            if ball.y <= 0:
                self.balls.remove(ball)
                self.lives -= 1
                self.combo = 0
                if self.lives <= 0:
                    self.state = GameState.GAME_OVER
                    self.user_manager.update_score(self.score, self.current_level, self.max_combo, False)
                elif len(self.balls) == 0:
                    ball_x = self.paddle.x + self.paddle.width / 2 - 15
                    self.balls.append(Ball(pos=(ball_x, self.paddle.y + 50)))
                continue

            if (ball.collide_widget(self.paddle) and ball.vy < 0):
                relative_x = (ball.x + 15) - (self.paddle.x + self.paddle.width / 2)
                max_bounce = 5
                ball.vx = (relative_x / (self.paddle.width / 2)) * max_bounce
                if ball.super_bounce:
                    ball.vy = abs(ball.vy) * 1.3
                else:
                    ball.vy = abs(ball.vy) * 1.1
                self.total_bounces += 1
                self.combo += 1
                self.combo_timer = 30
                self.max_combo = max(self.max_combo, self.combo)
                if self.combo > 5:
                    self.paddle.bounce_boost = True

            for brick in self.bricks[:]:
                if ball.collide_widget(brick):
                    overlap_left = ball.x + ball.width - brick.x
                    overlap_right = brick.x + brick.width - ball.x
                    overlap_top = ball.y + ball.height - brick.y
                    overlap_bottom = brick.y + brick.height - ball.y
                    min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
                    if min_overlap == overlap_left or min_overlap == overlap_right:
                        ball.vx = -ball.vx
                    else:
                        ball.vy = -ball.vy
                    play_target_hit()
                    if brick.hit():
                        self.bricks.remove(brick)
                        points = brick.points * (1 + self.combo * 0.1)
                        if ball.super_bounce:
                            points *= 2
                        self.score += int(points)
                        self.power_up_counter += 1
                        if self.power_up_counter % 7 == 0:
                            ptype = (self.power_up_counter % 7) + 1
                            self.power_ups.append(PowerUp(brick.x + brick.width / 2 - 10,
                                                          brick.y + brick.height / 2 - 10,
                                                          ptype))
                    break

        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer <= 0:
                self.combo = 0
                self.paddle.bounce_boost = False

        for pu in self.power_ups[:]:
            pu.update()
            if pu.collide_widget(self.paddle):
                self.activate_power_up(pu.type)
                self.power_ups.remove(pu)
                self.score += 500
            if pu.y < 0:
                self.power_ups.remove(pu)

        if len(self.bricks) == 0:
            self.state = GameState.LEVEL_COMPLETE
            bonus = self.lives * 1000 + self.max_combo * 100
            self.score += bonus
            self.user_manager.update_score(self.score, self.current_level, self.max_combo, True)

    def activate_power_up(self, ptype):
        self.power_up_active = ptype
        self.power_up_timer = 300
        if ptype == PowerUpType.MULTI_BALL:
            new_balls = []
            for ball in self.balls:
                if not ball.attached:
                    for i in range(2):
                        new_ball = Ball(pos=(ball.x, ball.y))
                        new_ball.vx = ball.vx + (-4 if i == 0 else 4)
                        new_ball.vy = ball.vy + (-3 if i == 0 else 3)
                        new_ball.attached = False
                        new_balls.append(new_ball)
                else:
                    new_balls.append(ball)
            self.balls.extend(new_balls)
        elif ptype == PowerUpType.SUPER_BOUNCE:
            for ball in self.balls:
                ball.super_bounce = True
        elif ptype == PowerUpType.SHIELD:
            for ball in self.balls:
                ball.shielded = True
        elif ptype == PowerUpType.GIANT_BALL:
            for ball in self.balls:
                if not ball.attached:
                    ball.size = (45, 45)
                    ball.giant = True
                    ball.pos = (ball.x - 7.5, ball.y - 7.5)
        elif ptype == PowerUpType.SLOW_MOTION:
            for ball in self.balls:
                if not ball.attached:
                    ball.vx *= 0.5
                    ball.vy *= 0.5
        elif ptype == PowerUpType.MAGNET:
            pass

    def deactivate_power_up(self):
        if self.power_up_active == PowerUpType.SUPER_BOUNCE:
            for ball in self.balls:
                ball.super_bounce = False
        elif self.power_up_active == PowerUpType.SHIELD:
            for ball in self.balls:
                ball.shielded = False
        elif self.power_up_active == PowerUpType.GIANT_BALL:
            for ball in self.balls:
                if ball.giant:
                    ball.size = (30, 30)
                    ball.giant = False
                    ball.pos = (ball.x + 7.5, ball.y + 7.5)
        elif self.power_up_active == PowerUpType.SLOW_MOTION:
            for ball in self.balls:
                if not ball.attached:
                    ball.vx *= 2
                    ball.vy *= 2
        self.power_up_active = None


class Ball(kivy.uix.widget.Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (30, 30)
        self.vx = 0
        self.vy = 0
        self.color = (1, 1, 1)
        self.attached = True
        self.super_bounce = False
        self.shielded = False
        self.giant = False
        self.trail = []

    def launch(self, speed_x=6, speed_y=10):
        self.attached = False
        self.vx = -speed_x if (id(self) % 2 == 0) else speed_x
        self.vy = -speed_y

    def update_trail(self):
        self.trail.append((self.x + 15, self.y + 15))
        if len(self.trail) > 10:
            self.trail.pop(0)


class Paddle(kivy.uix.widget.Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (180, 20)
        self.x = 0
        self.y = 0
        self.color = (0.2, 0.6, 1)
        self.speed = 8
        self.bounce_boost = False
        self.lasers = []

    def center_paddle(self, game_width):
        self.x = (game_width / 2) - (self.width / 2)

    def move_left(self):
        self.x = max(0, self.x - self.speed)

    def move_right(self, max_width):
        self.x = min(max_width - self.width, self.x + self.speed)

    def shoot_laser(self):
        self.lasers.append({
            'x': self.x + self.width / 2 - 2,
            'y': self.y,
            'width': 4,
            'height': 20
        })


class Brick(kivy.uix.widget.Widget):
    def __init__(self, x, y, color, hp=1, points=100, **kwargs):
        super().__init__(**kwargs)
        self.size = (70, 25)
        self.pos = (x, y)
        self.color = color
        self.hp = hp
        self.max_hp = hp
        self.points = points * hp

    def hit(self):
        self.hp -= 1
        return self.hp <= 0


class PowerUp(kivy.uix.widget.Widget):
    def __init__(self, x, y, ptype, **kwargs):
        super().__init__(**kwargs)
        self.size = (20, 20)
        self.pos = (x, y)
        self.type = ptype
        self.vy = 2
        self.angle = 0
        self.colors = {
            PowerUpType.SLOW_MOTION: (0, 1, 1),
            PowerUpType.GIANT_BALL: (1, 0.5, 0),
            PowerUpType.MULTI_BALL: (0, 1, 0),
            PowerUpType.MAGNET: (0.5, 0, 0.5),
            PowerUpType.LASER: (1, 0, 0),
            PowerUpType.SHIELD: (1, 0.84, 0),
            PowerUpType.SUPER_BOUNCE: (1, 1, 0)
        }
        self.symbols = {
            PowerUpType.SLOW_MOTION: "S",
            PowerUpType.GIANT_BALL: "G",
            PowerUpType.MULTI_BALL: "M",
            PowerUpType.MAGNET: "A",
            PowerUpType.LASER: "L",
            PowerUpType.SHIELD: "H",
            PowerUpType.SUPER_BOUNCE: "B"
        }
        self.color = self.colors[ptype]

    def update(self):
        self.y -= self.vy
        self.angle += 0.05


class LoginScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        title = AnimatedTitle(text='GRAVITY BOUNCE',
                              font_size=72,
                              pos_hint={'center_x': 0.5, 'center_y': 0.82})
        content.add_widget(title)

        subtitle = kivy.uix.label.Label(text='SUPER BOUNCE EDITION',
                                        font_size=28,
                                        color=(1, 0.84, 0, 1),
                                        bold=True,
                                        pos_hint={'center_x': 0.5, 'center_y': 0.72})
        content.add_widget(subtitle)

        card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.4, 0.45),
                                                pos_hint={'center_x': 0.5, 'center_y': 0.45})

        with card.canvas.before:
            kivy.graphics.Color(0.1, 0.1, 0.2, 0.85)
            kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])
            kivy.graphics.Color(1, 1, 1, 0.1)
            kivy.graphics.Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 20, 20, 20, 20),
                               width=2)

        form = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                            size_hint=(0.85, 0.8),
                                            pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                            spacing=15)

        card_title = kivy.uix.label.Label(text='WELCOME BACK',
                                          font_size=24,
                                          color=(0, 1, 1, 1),
                                          bold=True,
                                          size_hint_y=0.2)
        form.add_widget(card_title)

        self.username_input = GlowTextInput(hint_text='USERNAME',
                                            multiline=False,
                                            size_hint_y=0.2)
        form.add_widget(self.username_input)

        self.password_input = GlowTextInput(hint_text='PASSWORD',
                                            password=True,
                                            multiline=False,
                                            size_hint_y=0.2)
        form.add_widget(self.password_input)

        login_btn = IconButton(icon=">", text="LOGIN",
                               background_color=(0.2, 0.6, 0.8, 1),
                               size_hint_y=0.2)
        login_btn.bind(on_press=self.login)
        form.add_widget(login_btn)

        self.message_label = kivy.uix.label.Label(text='',
                                                  color=(1, 0.5, 0.5, 1),
                                                  font_size=14,
                                                  size_hint_y=0.2)
        form.add_widget(self.message_label)

        card.add_widget(form)
        content.add_widget(card)

        register_layout = kivy.uix.boxlayout.BoxLayout(orientation='horizontal',
                                                       size_hint=(0.4, 0.07),
                                                       pos_hint={'x': 0.3, 'y': 0.12},
                                                       spacing=10)

        register_text = kivy.uix.label.Label(text="Don't have an account?",
                                             color=(0.8, 0.8, 0.8, 1),
                                             font_size=16,
                                             size_hint_x=0.6)
        register_btn = kivy.uix.button.Button(text="CREATE ONE",
                                              background_color=(0, 0, 0, 0),
                                              color=(0, 1, 1, 1),
                                              font_size=16,
                                              bold=True,
                                              size_hint_x=0.4)
        register_btn.bind(on_press=lambda *a: play_ui_click())
        register_btn.bind(on_press=self.go_to_register)

        register_layout.add_widget(register_text)
        register_layout.add_widget(register_btn)
        content.add_widget(register_layout)

        guest_btn = IconButton(icon=">", text="PLAY AS GUEST",
                               background_color=(0.4, 0.4, 0.5, 0.8),
                               size_hint=(0.2, 0.06),
                               pos_hint={'center_x': 0.5, 'y': 0.05},
                               font_size=18)
        guest_btn.bind(on_press=self.guest_mode)
        content.add_widget(guest_btn)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def login(self, instance):
        username = self.username_input.text
        password = self.password_input.text
        success, message = self.game.user_manager.login(username, password)
        self.message_label.text = message
        if success:
            self.manager.current = 'menu'

    def go_to_register(self, instance):
        self.manager.current = 'register'

    def guest_mode(self, instance):
        self.game.user_manager.login("guest", "guest")
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class RegisterScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        title = AnimatedTitle(text='CREATE ACCOUNT',
                              font_size=64,
                              pos_hint={'center_x': 0.5, 'center_y': 0.82})
        content.add_widget(title)

        card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.4, 0.55),
                                                pos_hint={'center_x': 0.5, 'center_y': 0.45})

        with card.canvas.before:
            kivy.graphics.Color(0.1, 0.1, 0.2, 0.85)
            kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])
            kivy.graphics.Color(1, 1, 1, 0.1)
            kivy.graphics.Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 20, 20, 20, 20),
                               width=2)

        form = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                            size_hint=(0.85, 0.85),
                                            pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                            spacing=12)

        card_title = kivy.uix.label.Label(text='JOIN THE ADVENTURE',
                                          font_size=22,
                                          color=(0, 1, 1, 1),
                                          bold=True,
                                          size_hint_y=0.15)
        form.add_widget(card_title)

        self.username_input = GlowTextInput(hint_text='USERNAME (min 3 chars)',
                                            multiline=False,
                                            size_hint_y=0.15)
        form.add_widget(self.username_input)

        self.password_input = GlowTextInput(hint_text='PASSWORD (min 4 chars)',
                                            password=True,
                                            multiline=False,
                                            size_hint_y=0.15)
        form.add_widget(self.password_input)

        self.confirm_input = GlowTextInput(hint_text='CONFIRM PASSWORD',
                                           password=True,
                                           multiline=False,
                                           size_hint_y=0.15)
        form.add_widget(self.confirm_input)

        register_btn = IconButton(icon="", text="REGISTER",
                                  background_color=(0.2, 0.7, 0.4, 1),
                                  size_hint_y=0.15)
        register_btn.bind(on_press=self.register)
        form.add_widget(register_btn)

        self.message_label = kivy.uix.label.Label(text='',
                                                  color=(1, 0.5, 0.5, 1),
                                                  font_size=14,
                                                  size_hint_y=0.1)
        form.add_widget(self.message_label)

        card.add_widget(form)
        content.add_widget(card)

        back_btn = kivy.uix.button.Button(text='BACK TO LOGIN',
                                          background_color=(0, 0, 0, 0),
                                          color=(0, 1, 1, 1),
                                          font_size=18,
                                          size_hint=(None, None),
                                          size=(200, 40),
                                          pos_hint={'x': 0.02, 'top': 0.98})
        back_btn.bind(on_press=lambda *a: play_ui_click())
        back_btn.bind(on_press=self.go_back)
        content.add_widget(back_btn)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def register(self, instance):
        username = self.username_input.text
        password = self.password_input.text
        confirm = self.confirm_input.text
        success, message = self.game.user_manager.register(username, password, confirm)
        self.message_label.text = message
        if success:
            self.manager.current = 'login'

    def go_back(self, instance):
        self.manager.current = 'login'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class InstructionsScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        title = AnimatedTitle(text='HOW TO PLAY',
                              font_size=54,
                              pos_hint={'center_x': 0.5, 'center_y': 0.92})
        content.add_widget(title)

        card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.8, 0.75),
                                                pos_hint={'center_x': 0.5, 'center_y': 0.48})

        with card.canvas.before:
            kivy.graphics.Color(0.05, 0.05, 0.1, 0.9)
            kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])
            kivy.graphics.Color(1, 1, 1, 0.15)
            kivy.graphics.Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 20, 20, 20, 20),
                               width=2)

        instructions_text = """
[color=00ff00]* GAME OBJECTIVE[/color]
Break all the bricks using the bouncing ball to complete each level!

[color=00ff00]* CONTROLS[/color]
• [color=ffff00]← →[/color] - Move paddle left/right
• [color=ffff00]SPACE[/color] - Launch ball / Shoot laser (when laser power-up active)
• [color=ffff00]P / ESC[/color] - Pause game
• [color=ffff00]I[/color] - Show instructions (in-game)

[color=00ff00]* POWER-UPS[/color]
• [color=00ffff]SLOW MOTION[/color] - Slows down the ball
• [color=ff6600]GIANT BALL[/color] - Ball grows larger, easier to hit bricks
• [color=00ff00]MULTI BALL[/color] - Creates extra balls!
• [color=aa00aa]MAGNET[/color] - Ball attracted to paddle
• [color=ff0000]LASER[/color] - Paddle shoots lasers!
• [color=ffd700]SHIELD[/color] - Protects ball from one hit
• [color=ffff00]SUPER BOUNCE[/color] - Ball bounces faster and stronger

[color=00ff00]* SCORING[/color]
• Break bricks: Base points × combo multiplier
• Collect power-ups: +500 points
• Level completion bonus: Lives remaining × 1000 + Max combo × 100
• Higher combos = More points!

[color=00ff00]* TIPS[/color]
• Build combos by hitting bricks without missing
• Higher difficulty levels give more points
• Save power-ups for challenging moments
        """

        instructions = kivy.uix.label.Label(text=instructions_text,
                                            font_size=16,
                                            color=(1, 1, 1, 1),
                                            markup=True,
                                            halign='center',
                                            valign='top',
                                            size_hint=(0.95, 0.95),
                                            pos_hint={'center_x': 0.5, 'center_y': 0.5})
        instructions.bind(size=instructions.setter('text_size'))

        card.add_widget(instructions)
        content.add_widget(card)

        back_btn = IconButton(icon=">", text="BACK TO MENU",
                              size_hint=(0.2, 0.06),
                              pos_hint={'center_x': 0.5, 'y': 0.03},
                              background_color=(0.4, 0.4, 0.5, 1),
                              font_size=18)
        back_btn.bind(on_press=self.go_back)
        content.add_widget(back_btn)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def go_back(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class MainMenuScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        username = self.game.user_manager.current_user or "Guest"
        welcome = kivy.uix.label.Label(text=f'WELCOME, {username.upper()}!',
                                       font_size=28,
                                       color=(0.8, 0.8, 1, 1),
                                       pos_hint={'center_x': 0.5, 'center_y': 0.88})
        content.add_widget(welcome)

        title = AnimatedTitle(text='GRAVITY BOUNCE',
                              font_size=72,
                              pos_hint={'center_x': 0.5, 'center_y': 0.78})
        content.add_widget(title)

        subtitle = kivy.uix.label.Label(text='SUPER BOUNCE EDITION',
                                        font_size=32,
                                        color=(1, 0.84, 0, 1),
                                        bold=True,
                                        pos_hint={'center_x': 0.5, 'center_y': 0.68})
        content.add_widget(subtitle)

        app = kivy.app.App.get_running_app()
        music = getattr(app, "music", None)
        is_muted = music.bgm_muted if music else False
        mute_btn = IconButton(icon="", text="mute" if is_muted else "unmute",
                              background_color=(0.25, 0.35, 0.5, 0.95),
                              size_hint=(0.1, 0.055),
                              pos_hint={'right': 0.98, 'top': 0.97},
                              font_size=26)
        mute_btn.bind(on_press=self.toggle_bgm)
        content.add_widget(mute_btn)

        card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.35, 0.45),
                                                pos_hint={'center_x': 0.5, 'center_y': 0.42})

        with card.canvas.before:
            kivy.graphics.Color(0.1, 0.1, 0.2, 0.85)
            kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])
            kivy.graphics.Color(1, 1, 1, 0.1)
            kivy.graphics.Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 20, 20, 20, 20),
                               width=2)

        menu_layout = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                   size_hint=(0.8, 0.85),
                                                   pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                                   spacing=12)

        play_btn = IconButton(icon=">", text="PLAY",
                              background_color=(0.2, 0.6, 0.8, 1),
                              size_hint_y=0.18)
        play_btn.bind(on_press=self.start_game)
        menu_layout.add_widget(play_btn)

        level_select_btn = IconButton(icon=">", text="SELECT LEVEL",
                                      background_color=(0.6, 0.4, 0.8, 1),
                                      size_hint_y=0.18)
        level_select_btn.bind(on_press=self.go_to_level_select)
        menu_layout.add_widget(level_select_btn)

        instructions_btn = IconButton(icon=">", text="INSTRUCTIONS",
                                      background_color=(0.8, 0.5, 0.2, 1),
                                      size_hint_y=0.18)
        instructions_btn.bind(on_press=self.go_to_instructions)
        menu_layout.add_widget(instructions_btn)

        stats_btn = IconButton(icon=">", text="STATISTICS",
                               background_color=(0.5, 0.3, 0.7, 1),
                               size_hint_y=0.18)
        stats_btn.bind(on_press=self.show_stats)
        menu_layout.add_widget(stats_btn)

        logout_btn = IconButton(icon=">", text="LOGOUT",
                                background_color=(0.8, 0.3, 0.3, 1),
                                size_hint_y=0.18)
        logout_btn.bind(on_press=self.logout)
        menu_layout.add_widget(logout_btn)

        card.add_widget(menu_layout)
        content.add_widget(card)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def toggle_bgm(self, instance):
        app = kivy.app.App.get_running_app()
        music = getattr(app, "music", None)
        if not music:
            return
        music.bgm_muted = not music.bgm_muted
        music.apply_bgm_mute()
        instance.text = "unmute" if music.bgm_muted else "mute"

    def start_game(self, instance):
        if self.game:
            self.game.start_level(0)
        self.manager.current = 'game'

    def go_to_level_select(self, instance):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.manager.current = 'level_select'

    def go_to_instructions(self, instance):
        if self.game:
            self.game.state = GameState.INSTRUCTIONS
        self.manager.current = 'instructions'

    def show_stats(self, instance):
        stats = self.game.user_manager.get_stats()
        if stats:
            levels_completed = []
            if stats["levels_completed"][0]:
                levels_completed.append("Easy")
            if stats["levels_completed"][1]:
                levels_completed.append("Medium")
            if stats["levels_completed"][2]:
                levels_completed.append("Hard")

            stats_text = f"""
[color=00ff00] PLAYER STATISTICS [/color]

[color=ffff00] - High Score:[/color] {stats['high_score']}
[color=ffff00] - Total Games:[/color] {stats['total_games']}
[color=ffff00]- Average Score:[/color] {stats['avg_score']}
[color=ffff00]- Win Rate:[/color] {stats['win_rate']:.1f}%
[color=ffff00]- Best Combo:[/color] {stats['best_combo']}
[color=ffff00]- Levels Completed:[/color] {', '.join(levels_completed) if levels_completed else 'None'}
            """

            content = kivy.uix.boxlayout.BoxLayout(orientation='vertical', spacing=15, padding=20)
            label = kivy.uix.label.Label(text=stats_text,
                                         markup=True,
                                         halign='center',
                                         valign='middle',
                                         font_size=20)
            label.bind(size=label.setter('text_size'))
            content.add_widget(label)

            close_btn = IconButton(icon="", text="CLOSE", size_hint=(0.5, 0.2),
                                   pos_hint={'center_x': 0.5}, font_size=18)
            content.add_widget(close_btn)

            popup = kivy.uix.popup.Popup(title=' PLAYER STATISTICS',
                                         content=content,
                                         size_hint=(0.6, 0.6),
                                         background_color=(0.05, 0.05, 0.1, 1))
            close_btn.bind(on_press=popup.dismiss)
            popup.open()
        else:
            content = kivy.uix.label.Label(text='No statistics available yet.\nPlay some games to see your stats!',
                                           font_size=18)
            popup = kivy.uix.popup.Popup(title='Statistics',
                                         content=content,
                                         size_hint=(0.5, 0.3))
            popup.open()

    def logout(self, instance):
        self.game.user_manager.logout()
        self.manager.current = 'login'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class LevelSelectScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        title = AnimatedTitle(text='SELECT DIFFICULTY',
                              font_size=54,
                              pos_hint={'center_x': 0.5, 'center_y': 0.88})
        content.add_widget(title)

        grid = kivy.uix.gridlayout.GridLayout(cols=3,
                                              spacing=25,
                                              padding=40,
                                              size_hint=(0.9, 0.55),
                                              pos_hint={'center_x': 0.5, 'center_y': 0.48})

        if self.game:
            stats = self.game.user_manager.get_stats()
            difficulties = [
                {"id": 0, "name": "EASY", "color": (0.2, 0.7, 0.2, 1), "bg_color": (0.1, 0.4, 0.1, 0.8),
                 "desc": "3 rows • 6 cols • 1 HP", "icon": ""},
                {"id": 1, "name": "MEDIUM", "color": (0.8, 0.7, 0.2, 1), "bg_color": (0.4, 0.3, 0.1, 0.8),
                 "desc": "4 rows • 8 cols • 2 HP", "icon": "⚡"},
                {"id": 2, "name": "HARD", "color": (0.8, 0.2, 0.2, 1), "bg_color": (0.4, 0.1, 0.1, 0.8),
                 "desc": "5 rows • 10 cols • 3 HP", "icon": ""}
            ]

            for diff in difficulties:
                card = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                    spacing=12,
                                                    padding=[20, 20, 20, 20])

                with card.canvas.before:
                    kivy.graphics.Color(*diff["bg_color"])
                    kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])
                    kivy.graphics.Color(1, 1, 1, 0.2)
                    kivy.graphics.Line(rounded_rectangle=(card.x, card.y, card.width, card.height, 20, 20, 20, 20),
                                       width=2)

                is_completed = stats and stats["levels_completed"][diff["id"]] if stats else False
                completed_mark = " ✓" if is_completed else ""

                icon_label = kivy.uix.label.Label(text=diff["icon"],
                                                  font_size=48,
                                                  size_hint_y=0.3)
                card.add_widget(icon_label)

                name_btn = IconButton(icon=diff["icon"], text=diff["name"] + completed_mark,
                                      background_color=diff["color"],
                                      font_size=28,
                                      size_hint_y=0.35)
                name_btn.bind(on_press=lambda x, lvl_id=diff["id"]: self.start_level(lvl_id))
                card.add_widget(name_btn)

                desc_label = kivy.uix.label.Label(text=diff["desc"],
                                                  halign='center',
                                                  font_size=16,
                                                  color=(0.9, 0.9, 0.9, 1),
                                                  size_hint_y=0.2)
                desc_label.bind(size=desc_label.setter('text_size'))
                card.add_widget(desc_label)

                grid.add_widget(card)

        content.add_widget(grid)

        back_btn = IconButton(icon="", text="BACK TO MENU",
                              size_hint=(0.2, 0.06),
                              pos_hint={'center_x': 0.5, 'y': 0.05},
                              background_color=(0.4, 0.4, 0.5, 1),
                              font_size=18)
        back_btn.bind(on_press=self.go_back)
        content.add_widget(back_btn)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def start_level(self, level_id):
        if self.game:
            self.game.start_level(level_id)
        self.manager.current = 'game'

    def go_back(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class GameScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game_widget = None
        self.game = None

    def set_game(self, game):
        self.game = game
        if not self.game_widget:
            self.game_widget = GameWidget(size_hint=(1, 1))
            self.game_widget.game = game
            self.add_widget(self.game_widget)

            top_bar = kivy.uix.boxlayout.BoxLayout(orientation='horizontal',
                                                   size_hint=(1, None),
                                                   height=65,
                                                   pos_hint={'top': 1},
                                                   padding=[15, 8, 15, 8],
                                                   spacing=15)

            with top_bar.canvas.before:
                kivy.graphics.Color(0, 0, 0, 0.7)
                kivy.graphics.Rectangle(pos=top_bar.pos, size=top_bar.size)

            left_panel = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                      size_hint=(0.3, 1),
                                                      spacing=2)

            self.score_label = kivy.uix.label.Label(text=' SCORE: 0',
                                                    color=(1, 1, 1, 1),
                                                    font_size=22,
                                                    bold=True,
                                                    halign='left',
                                                    size_hint=(1, 0.5))
            self.score_label.bind(size=self.score_label.setter('text_size'))

            self.lives_label = kivy.uix.label.Label(text='LIVES x 3',
                                                    color=(1, 0.4, 0.4, 1),
                                                    font_size=22,
                                                    bold=True,
                                                    halign='left',
                                                    size_hint=(1, 0.5))
            self.lives_label.bind(size=self.lives_label.setter('text_size'))

            left_panel.add_widget(self.score_label)
            left_panel.add_widget(self.lives_label)

            self.level_label = kivy.uix.label.Label(text='MEDIUM',
                                                    color=(0, 1, 1, 1),
                                                    font_size=26,
                                                    bold=True,
                                                    halign='center',
                                                    size_hint=(0.4, 1))
            self.level_label.bind(size=self.level_label.setter('text_size'))

            right_panel = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                       size_hint=(0.3, 1),
                                                       spacing=2)

            self.combo_label = kivy.uix.label.Label(text='',
                                                    color=(1, 0.84, 0, 1),
                                                    font_size=22,
                                                    bold=True,
                                                    halign='right',
                                                    size_hint=(1, 0.5))
            self.combo_label.bind(size=self.combo_label.setter('text_size'))

            self.power_label = kivy.uix.label.Label(text='',
                                                    color=(1, 0.5, 0, 1),
                                                    font_size=18,
                                                    halign='right',
                                                    size_hint=(1, 0.5))
            self.power_label.bind(size=self.power_label.setter('text_size'))

            right_panel.add_widget(self.combo_label)
            right_panel.add_widget(self.power_label)

            top_bar.add_widget(left_panel)
            top_bar.add_widget(self.level_label)
            top_bar.add_widget(right_panel)

            self.add_widget(top_bar)

            button_panel = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                        size_hint=(None, 0.3),
                                                        width=100,
                                                        pos_hint={'right': 0.98, 'top': 0.96},
                                                        spacing=8)

            exit_btn = IconButton(icon="X", text="EXIT",
                                  size_hint=(1, 0.25),
                                  background_color=(0.7, 0.2, 0.2, 0.9),
                                  font_size=14)
            exit_btn.bind(on_press=self.exit_game)

            help_btn = IconButton(icon=">", text="HELP",
                                  size_hint=(1, 0.25),
                                  background_color=(0.7, 0.5, 0.2, 0.9),
                                  font_size=14)
            help_btn.bind(on_press=self.show_instructions)

            levels_btn = IconButton(icon=">", text="LEVELS",
                                    size_hint=(1, 0.25),
                                    background_color=(0.6, 0.3, 0.7, 0.9),
                                    font_size=14)
            levels_btn.bind(on_press=self.show_level_select)

            menu_btn = IconButton(icon=">", text="MENU",
                                  size_hint=(1, 0.25),
                                  background_color=(0.3, 0.3, 0.7, 0.9),
                                  font_size=14)
            menu_btn.bind(on_press=self.show_menu)

            button_panel.add_widget(exit_btn)
            button_panel.add_widget(help_btn)
            button_panel.add_widget(levels_btn)
            button_panel.add_widget(menu_btn)

            self.add_widget(button_panel)

            kivy.clock.Clock.schedule_interval(self.update_ui, 1.0 / 30.0)

    def on_enter(self):
        if self.game_widget:
            self.game_widget.ensure_keyboard()

    def update_ui(self, dt):
        if self.game:
            self.score_label.text = f' SCORE: {self.game.score}'
            self.lives_label.text = f'LIVES x {self.game.lives}'

            level_names = ["EASY", "MEDIUM", "HARD"]
            if self.game.current_level < len(level_names):
                self.level_label.text = level_names[self.game.current_level]

            if self.game.combo > 1:
                self.combo_label.text = f'⚡ x{self.game.combo} COMBO!'
            else:
                self.combo_label.text = ''

            if self.game.power_up_active:
                time_left = self.game.power_up_timer // 60
                power_name = PowerUpType.get_name(self.game.power_up_active)
                self.power_label.text = f' {power_name} {time_left}s'
            else:
                self.power_label.text = ''

    def show_menu(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def show_level_select(self, instance):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.manager.current = 'level_select'

    def show_instructions(self, instance):
        if self.game:
            self.game.state = GameState.INSTRUCTIONS
        self.manager.current = 'instructions'

    def exit_game(self, instance):
        kivy.app.App.get_running_app().stop()


class GameOverScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        game_over = kivy.uix.label.Label(text='GAME OVER',
                                         font_size=72,
                                         color=(1, 0.3, 0.3, 1),
                                         bold=True,
                                         pos_hint={'center_x': 0.5, 'center_y': 0.72})
        content.add_widget(game_over)

        if self.game:
            level_names = ["EASY", "MEDIUM", "HARD"]
            current_level_name = level_names[self.game.current_level] if self.game.current_level < len(
                level_names) else "UNKNOWN"

            card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.5, 0.4),
                                                    pos_hint={'center_x': 0.5, 'center_y': 0.45})

            with card.canvas.before:
                kivy.graphics.Color(0.1, 0.1, 0.2, 0.85)
                kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])

            stats_layout = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                        size_hint=(0.8, 0.7),
                                                        pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                                        spacing=12)

            stats = [
                f' Final Score: {self.game.score}',
                f' Max Combo: {self.game.max_combo}',
                f' Total Bounces: {self.game.total_bounces}',
                f' Level: {current_level_name}'
            ]

            for stat in stats:
                label = kivy.uix.label.Label(text=stat,
                                             font_size=24,
                                             color=(1, 1, 1, 1),
                                             size_hint_y=0.25)
                stats_layout.add_widget(label)

            card.add_widget(stats_layout)
            content.add_widget(card)

        btn_layout = kivy.uix.boxlayout.BoxLayout(orientation='horizontal',
                                                  size_hint=(0.5, 0.08),
                                                  pos_hint={'center_x': 0.5, 'y': 0.15},
                                                  spacing=15)

        retry_btn = IconButton(icon="", text="RETRY",
                               background_color=(0.2, 0.7, 0.2, 1),
                               font_size=20)
        retry_btn.bind(on_press=self.retry_level)

        levels_btn = IconButton(icon="", text="LEVELS",
                                background_color=(0.5, 0.3, 0.8, 1),
                                font_size=20)
        levels_btn.bind(on_press=self.go_to_levels)

        menu_btn = IconButton(icon="", text="MENU",
                              background_color=(0.4, 0.4, 0.5, 1),
                              font_size=20)
        menu_btn.bind(on_press=self.go_to_menu)

        btn_layout.add_widget(retry_btn)
        btn_layout.add_widget(levels_btn)
        btn_layout.add_widget(menu_btn)

        content.add_widget(btn_layout)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def retry_level(self, instance):
        if self.game:
            self.game.start_level(self.game.current_level)
        self.manager.current = 'game'

    def go_to_levels(self, instance):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.manager.current = 'level_select'

    def go_to_menu(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class LevelCompleteScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        complete = kivy.uix.label.Label(text='LEVEL COMPLETE!',
                                        font_size=72,
                                        color=(0.3, 1, 0.3, 1),
                                        bold=True,
                                        pos_hint={'center_x': 0.5, 'center_y': 0.72})
        content.add_widget(complete)

        if self.game:
            level_names = ["EASY", "MEDIUM", "HARD"]
            current_level_name = level_names[self.game.current_level] if self.game.current_level < len(
                level_names) else "UNKNOWN"

            card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.5, 0.45),
                                                    pos_hint={'center_x': 0.5, 'center_y': 0.45})

            with card.canvas.before:
                kivy.graphics.Color(0.1, 0.1, 0.2, 0.85)
                kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])

            stats_layout = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                        size_hint=(0.8, 0.75),
                                                        pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                                        spacing=10)

            stats = [
                f' Score: {self.game.score}',
                f' Max Combo: {self.game.max_combo}',
                f' Total Bounces: {self.game.total_bounces}',
                f' Lives Bonus: +{self.game.lives * 1000}'
            ]

            for stat in stats:
                label = kivy.uix.label.Label(text=stat,
                                             font_size=22,
                                             color=(1, 1, 1, 1),
                                             size_hint_y=0.25)
                stats_layout.add_widget(label)

            if self.game.current_level + 1 < len(level_names):
                next_text = f' Next: {level_names[self.game.current_level + 1]} '
                next_label = kivy.uix.label.Label(text=next_text,
                                                  font_size=20,
                                                  color=(0, 1, 1, 1),
                                                  size_hint_y=0.25)
                stats_layout.add_widget(next_label)

            card.add_widget(stats_layout)
            content.add_widget(card)

        btn_layout = kivy.uix.boxlayout.BoxLayout(orientation='horizontal',
                                                  size_hint=(0.5, 0.08),
                                                  pos_hint={'center_x': 0.5, 'y': 0.12},
                                                  spacing=15)

        next_btn = IconButton(icon="➡", text="NEXT LEVEL",
                              background_color=(0.2, 0.7, 0.2, 1),
                              font_size=20)
        next_btn.bind(on_press=self.next_level)

        levels_btn = IconButton(icon="", text="LEVELS",
                                background_color=(0.5, 0.3, 0.8, 1),
                                font_size=20)
        levels_btn.bind(on_press=self.go_to_levels)

        menu_btn = IconButton(icon="", text="MENU",
                              background_color=(0.4, 0.4, 0.5, 1),
                              font_size=20)
        menu_btn.bind(on_press=self.go_to_menu)

        btn_layout.add_widget(next_btn)
        btn_layout.add_widget(levels_btn)
        btn_layout.add_widget(menu_btn)

        content.add_widget(btn_layout)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def next_level(self, instance):
        if self.game:
            self.game.next_level()
        self.manager.current = 'game'

    def go_to_levels(self, instance):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.manager.current = 'level_select'

    def go_to_menu(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class PauseScreen(kivy.uix.screenmanager.Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.bg = None

    def set_game(self, game):
        self.game = game

    def on_enter(self):
        self.clear_widgets()

        self.bg = GradientBackground()
        self.add_widget(self.bg)

        content = kivy.uix.floatlayout.FloatLayout()

        with content.canvas.before:
            kivy.graphics.Color(0, 0, 0, 0.7)
            kivy.graphics.Rectangle(pos=content.pos, size=content.size)

        pause = kivy.uix.label.Label(text='⏸ PAUSED',
                                     font_size=72,
                                     color=(1, 1, 0, 1),
                                     bold=True,
                                     pos_hint={'center_x': 0.5, 'center_y': 0.7})
        content.add_widget(pause)

        card = kivy.uix.floatlayout.FloatLayout(size_hint=(0.35, 0.4),
                                                pos_hint={'center_x': 0.5, 'center_y': 0.45})

        with card.canvas.before:
            kivy.graphics.Color(0.1, 0.1, 0.2, 0.9)
            kivy.graphics.RoundedRectangle(pos=card.pos, size=card.size, radius=[20])

        btn_layout = kivy.uix.boxlayout.BoxLayout(orientation='vertical',
                                                  size_hint=(0.8, 0.8),
                                                  pos_hint={'center_x': 0.5, 'center_y': 0.5},
                                                  spacing=12)

        resume_btn = IconButton(icon="-", text="RESUME",
                                background_color=(0.2, 0.7, 0.2, 1),
                                size_hint_y=0.25)
        resume_btn.bind(on_press=self.resume_game)

        instructions_btn = IconButton(icon="-", text="INSTRUCTIONS",
                                      background_color=(0.7, 0.5, 0.2, 1),
                                      size_hint_y=0.25)
        instructions_btn.bind(on_press=self.go_to_instructions)

        levels_btn = IconButton(icon="-", text="LEVELS",
                                background_color=(0.5, 0.3, 0.8, 1),
                                size_hint_y=0.25)
        levels_btn.bind(on_press=self.go_to_levels)

        menu_btn = IconButton(icon="-", text="MENU",
                              background_color=(0.4, 0.4, 0.5, 1),
                              size_hint_y=0.25)
        menu_btn.bind(on_press=self.go_to_menu)

        btn_layout.add_widget(resume_btn)
        btn_layout.add_widget(instructions_btn)
        btn_layout.add_widget(levels_btn)
        btn_layout.add_widget(menu_btn)

        card.add_widget(btn_layout)
        content.add_widget(card)

        exit_btn = IconButton(icon="X", text="EXIT",
                              background_color=(0.7, 0.2, 0.2, 0.9),
                              size_hint=(0.08, 0.04),
                              pos_hint={'x': 0.02, 'y': 0.02},
                              font_size=12)
        exit_btn.bind(on_press=self.exit_app)
        content.add_widget(exit_btn)

        self.add_widget(content)

    def resume_game(self, instance):
        if self.manager.current == 'pause':
            self.manager.current = 'game'

    def go_to_instructions(self, instance):
        if self.game:
            self.game.state = GameState.INSTRUCTIONS
        self.manager.current = 'instructions'

    def go_to_levels(self, instance):
        if self.game:
            self.game.state = GameState.LEVEL_SELECT
        self.manager.current = 'level_select'

    def go_to_menu(self, instance):
        if self.game:
            self.game.state = GameState.MENU
        self.manager.current = 'menu'

    def exit_app(self, instance):
        kivy.app.App.get_running_app().stop()


class GravityBounceApp(kivy.app.App):
    def build(self):
        ensure_bgm_wav_files(self)
        self.game = Game()
        self.music = BackgroundMusic()
        self.music.load()

        sm = kivy.uix.screenmanager.ScreenManager()

        login_screen = LoginScreen(name='login')
        register_screen = RegisterScreen(name='register')
        menu_screen = MainMenuScreen(name='menu')
        instructions_screen = InstructionsScreen(name='instructions')
        level_select_screen = LevelSelectScreen(name='level_select')
        game_screen = GameScreen(name='game')
        game_over_screen = GameOverScreen(name='game_over')
        level_complete_screen = LevelCompleteScreen(name='level_complete')
        pause_screen = PauseScreen(name='pause')

        login_screen.set_game(self.game)
        register_screen.set_game(self.game)
        menu_screen.set_game(self.game)
        instructions_screen.set_game(self.game)
        level_select_screen.set_game(self.game)
        game_screen.set_game(self.game)
        game_over_screen.set_game(self.game)
        level_complete_screen.set_game(self.game)
        pause_screen.set_game(self.game)

        sm.add_widget(login_screen)
        sm.add_widget(register_screen)
        sm.add_widget(menu_screen)
        sm.add_widget(instructions_screen)
        sm.add_widget(level_select_screen)
        sm.add_widget(game_screen)
        sm.add_widget(game_over_screen)
        sm.add_widget(level_complete_screen)
        sm.add_widget(pause_screen)

        kivy.clock.Clock.schedule_interval(lambda dt: self.check_game_state(sm), 1.0 / 10.0)
        kivy.clock.Clock.schedule_once(
            lambda dt: self.music.sync(sm.current, self.game.state), 0
        )

        return sm

    def check_game_state(self, sm):
        if getattr(self, "music", None):
            self.music.sync(sm.current, self.game.state)
        state_to_screen = {
            GameState.MENU: 'menu',
            GameState.LEVEL_SELECT: 'level_select',
            GameState.PLAYING: 'game',
            GameState.GAME_OVER: 'game_over',
            GameState.LEVEL_COMPLETE: 'level_complete',
            GameState.PAUSED: 'pause',
            GameState.INSTRUCTIONS: 'instructions',
        }
        target = state_to_screen.get(self.game.state)
        if target and sm.current != target and sm.current not in ['login', 'register']:
            sm.current = target

    def on_stop(self):
        if getattr(self, "music", None):
            self.music.stop_all()
        if kivy.utils.platform not in ("ios", "android"):
            kivy.core.window.Window.close()


if __name__ == '__main__':
    GravityBounceApp().run()