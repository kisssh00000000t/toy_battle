"""
玩具趣味音效系统。

优先从 assets/sounds/ 加载预生成 WAV 文件，
若文件不存在则回退到合成音效（方波/噪声/扫频）。
所有音效在首次调用时延迟初始化，避免 pygame.mixer 未就绪时崩溃。
"""

import math
import os

import pygame
import numpy as np

# ─── 音效文件目录 ────────────────────────────────────────────────
_SOUND_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sounds")
_SOUND_DIR = os.path.normpath(_SOUND_DIR)

# ─── 音效名称常量 ────────────────────────────────────────────────
SND_CLICK = "click"
SND_PLACE = "place"
SND_DRAW = "draw"
SND_WIN = "win"
SND_TURN = "turn"
SND_UNDO = "undo"
SND_ERROR = "error"
SND_SEAL = "seal"
SND_RECALL = "recall"
SND_MOVE = "move"
SND_DESTROY = "destroy"
SND_STAR = "star"
SND_HOVER = "hover"

# ─── 音效事件 → 文件路径映射 ─────────────────────────────────────
SOUND_EVENTS = {
    SND_CLICK:   "click.wav",
    SND_PLACE:   "place.wav",
    SND_DRAW:    "draw.wav",
    SND_WIN:     "win.wav",
    SND_TURN:    "turn.wav",
    SND_UNDO:    "undo.wav",
    SND_ERROR:   "error.wav",
    SND_SEAL:    "seal.wav",
    SND_RECALL:  "recall.wav",
    SND_MOVE:    "move.wav",
    SND_DESTROY: "destroy.wav",
    SND_STAR:    "star.wav",
    SND_HOVER:   "hover.wav",
}

# ─── 内部状态 ─────────────────────────────────────────────────────
_sounds = {}
_initialized = False


# ─── 初始化 ───────────────────────────────────────────────────────
def _init_mixer():
    """延迟初始化 pygame.mixer。"""
    global _initialized
    if not _initialized:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            _initialized = True
        except pygame.error:
            _initialized = False


# ─── 合成音效（WAV 文件缺失时的回退方案）──────────────────────────
def _generate_square_wave(freq, duration, volume=0.3):
    """生成指定频率和时长的方波音效。"""
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    buf = np.zeros((n_samples, 2), dtype=np.int16)
    for i in range(n_samples):
        t = i / sample_rate
        value = int(volume * 32767 * (1 if int(t * freq * 2) % 2 == 0 else -1))
        buf[i] = [value, value]
    return pygame.sndarray.make_sound(buf)


def _generate_noise(duration, volume=0.2):
    """生成白噪声（用于点击或提示）。"""
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    buf = np.random.randint(
        -int(volume * 32767), int(volume * 32767),
        (n_samples, 2), dtype=np.int16,
    )
    return pygame.sndarray.make_sound(buf)


def _generate_sweep(start_freq, end_freq, duration, volume=0.3):
    """生成频率扫描音效（用于胜利或回合切换）。"""
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    buf = np.zeros((n_samples, 2), dtype=np.int16)
    for i in range(n_samples):
        t = i / sample_rate
        progress = i / n_samples
        freq = start_freq + (end_freq - start_freq) * progress
        value = int(volume * 32767 * math.sin(2 * math.pi * freq * t))
        buf[i] = [value, value]
    return pygame.sndarray.make_sound(buf)


def _generate_chime(base_freq, duration, volume=0.25):
    """生成和弦音效（用于放置成功）。"""
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    buf = np.zeros((n_samples, 2), dtype=np.int16)
    harmonics = [1.0, 1.5, 2.0]
    for i in range(n_samples):
        t = i / sample_rate
        envelope = max(0, 1.0 - t / duration)
        value = 0
        for h in harmonics:
            value += math.sin(2 * math.pi * base_freq * h * t)
        value = int(volume * 32767 * envelope * value / len(harmonics))
        buf[i] = [value, value]
    return pygame.sndarray.make_sound(buf)


# ─── 合成音效回退表 ───────────────────────────────────────────────
_SYNTH_TABLE = {
    SND_CLICK:   lambda: _generate_noise(0.05, volume=0.15),
    SND_PLACE:   lambda: _generate_chime(523, 0.2, volume=0.25),
    SND_DRAW:    lambda: _generate_square_wave(880, 0.1, volume=0.2),
    SND_WIN:     lambda: _generate_sweep(400, 1200, 0.5, volume=0.3),
    SND_TURN:    lambda: _generate_sweep(300, 600, 0.2, volume=0.2),
    SND_UNDO:    lambda: _generate_sweep(600, 300, 0.15, volume=0.2),
    SND_ERROR:   lambda: _generate_square_wave(200, 0.15, volume=0.2),
    SND_SEAL:    lambda: _generate_square_wave(150, 0.12, volume=0.25),
    SND_RECALL:  lambda: _generate_sweep(400, 800, 0.15, volume=0.2),
    SND_MOVE:    lambda: _generate_sweep(300, 500, 0.15, volume=0.2),
    SND_DESTROY: lambda: _generate_noise(0.15, volume=0.2),
    SND_STAR:    lambda: _generate_chime(1200, 0.15, volume=0.35),
    SND_HOVER:   lambda: _generate_noise(0.02, volume=0.08),
}


# ─── 加载 / 回退 ──────────────────────────────────────────────────
def _ensure_sounds():
    """确保所有音效已加载（优先 WAV，回退合成）。"""
    global _sounds
    if _sounds:
        return
    _init_mixer()
    if not _initialized:
        return
    try:
        for name, filename in SOUND_EVENTS.items():
            path = os.path.join(_SOUND_DIR, filename)
            if os.path.exists(path):
                _sounds[name] = pygame.mixer.Sound(path)
            elif name in _SYNTH_TABLE:
                _sounds[name] = _SYNTH_TABLE[name]()
    except Exception:
        # 音效加载/生成失败时静默降级
        _sounds = {}


# ─── 公共 API ──────────────────────────────────────────────────────
def play(sound_name, volume=0.5):
    """播放指定音效。

    Args:
        sound_name: 音效名称常量（如 SND_CLICK）
        volume: 音量 0.0~1.0
    """
    _ensure_sounds()
    snd = _sounds.get(sound_name)
    if snd is None:
        return
    try:
        snd.set_volume(volume)
        snd.play()
    except Exception:
        pass


def preload():
    """预加载所有音效（可在游戏启动时调用）。"""
    _ensure_sounds()