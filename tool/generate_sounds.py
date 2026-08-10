"""
音效生成脚本 — 一键生成全套游戏音效 WAV 文件。

运行方式:
    cd troop_war_game
    py tool/generate_sounds.py

输出目录: assets/sounds/
生成 13 个 WAV 文件: click, place, draw, win, turn, undo, error,
    seal, recall, move, destroy, star, hover
"""

import os
import wave
import math

import numpy as np
import pygame

# ---------- 参数配置 ----------
SAMPLE_RATE = 22050          # 采样率
BIT_DEPTH = -16              # 16位有符号
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sounds")
OUT_DIR = os.path.normpath(OUT_DIR)

# 确保输出目录存在
os.makedirs(OUT_DIR, exist_ok=True)


# ---------- WAV 写入 ----------
def write_wav(filename, samples):
    """将 numpy int16 数组写为单声道 WAV 文件。"""
    path = os.path.join(OUT_DIR, filename)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)          # 单声道
        wf.setsampwidth(2)          # 16位 = 2字节
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.astype(np.int16).tobytes())
    print(f"  -> {filename}")


# ---------- 波形生成 ----------
def sine_wave(freq, duration, volume=0.3):
    """生成正弦波。"""
    t = np.arange(0, duration, 1 / SAMPLE_RATE)
    w = np.sin(2 * np.pi * freq * t)
    return (w * volume * 32767).astype(np.int16)


def square_wave(freq, duration, volume=0.3):
    """生成方波（复古游戏感）。"""
    t = np.arange(0, duration, 1 / SAMPLE_RATE)
    w = np.sign(np.sin(2 * np.pi * freq * t))
    return (w * volume * 32767).astype(np.int16)


def noise(duration, volume=0.2):
    """白噪声。"""
    samples = np.random.randn(int(SAMPLE_RATE * duration))
    return (samples * volume * 32767).astype(np.int16)


def apply_envelope(samples, attack=0.02, decay=0.05, sustain=0.6, release=0.1):
    """简单 ADSR 包络。"""
    total = len(samples)
    attack_len = int(attack * SAMPLE_RATE)
    decay_len = int(decay * SAMPLE_RATE)
    release_len = int(release * SAMPLE_RATE)
    sustain_len = max(0, total - attack_len - decay_len - release_len)

    env = np.zeros(total)
    env[:attack_len] = np.linspace(0, 1, attack_len)
    env[attack_len:attack_len + decay_len] = np.linspace(1, sustain, decay_len)
    env[attack_len + decay_len:attack_len + decay_len + sustain_len] = sustain
    env[-release_len:] = np.linspace(sustain, 0, release_len)
    return (samples * env).astype(np.int16)


# ---------- 音效生成函数 ----------
def gen_click():
    """按钮点击：短促高频滴声"""
    s = square_wave(800, 0.08, 0.2)
    s = apply_envelope(s, attack=0.005, decay=0.03, sustain=0.1, release=0.02)
    write_wav("click.wav", s)


def gen_place():
    """放置棋子：清脆桌面音"""
    s1 = sine_wave(600, 0.08, 0.4)
    s2 = sine_wave(900, 0.06, 0.3)
    pad_len = max(len(s1), len(s2))
    s1 = np.pad(s1, (0, pad_len - len(s1)))
    s2 = np.pad(s2, (0, pad_len - len(s2)))
    mix = ((s1 + s2) / 2).astype(np.int16)
    mix = apply_envelope(mix, attack=0.005, decay=0.04, sustain=0.5, release=0.04)
    write_wav("place.wav", mix)


def gen_draw():
    """抽卡：轻微滑动声（噪声短促）"""
    s = noise(0.12, 0.15)
    s = apply_envelope(s, attack=0.01, decay=0.05, sustain=0.0, release=0.05)
    write_wav("draw.wav", s)


def gen_win():
    """胜利：上升旋律"""
    notes = [523, 659, 784, 1047]  # C5 E5 G5 C6
    parts = []
    dur = 0.12
    for freq in notes:
        s = sine_wave(freq, dur, 0.5)
        parts.append(s)
    full = np.concatenate(parts)
    full = apply_envelope(full, attack=0.01, decay=0.1, sustain=0.7, release=0.15)
    write_wav("win.wav", full)


def gen_turn():
    """回合切换：短促双音"""
    s1 = sine_wave(440, 0.08, 0.4)
    s2 = sine_wave(660, 0.08, 0.4)
    s = np.concatenate([s1, s2])
    s = apply_envelope(s, attack=0.005, decay=0.05, sustain=0.5, release=0.05)
    write_wav("turn.wav", s)


def gen_undo():
    """撤销：倒带感（降频短音）"""
    s = sine_wave(500, 0.1, 0.3)
    s = apply_envelope(s, attack=0.005, decay=0.04, sustain=0.2, release=0.05)
    write_wav("undo.wav", s)


def gen_error():
    """错误：低沉短促"""
    s = square_wave(200, 0.15, 0.25)
    s = apply_envelope(s, attack=0.01, decay=0.05, sustain=0.1, release=0.05)
    write_wav("error.wav", s)


def gen_seal():
    """封印手牌：沉闷封印音"""
    s = sine_wave(150, 0.12, 0.4)
    s = apply_envelope(s, attack=0.01, decay=0.06, sustain=0.2, release=0.05)
    write_wav("seal.wav", s)


def gen_recall():
    """召回：上升音阶小片段"""
    s = sine_wave(400, 0.08, 0.35)
    s2 = sine_wave(600, 0.08, 0.35)
    s = np.concatenate([s, s2])
    s = apply_envelope(s, attack=0.01, decay=0.04, sustain=0.5, release=0.05)
    write_wav("recall.wav", s)


def gen_move():
    """移动：短滑音"""
    freq_start, freq_end = 300, 500
    dur = 0.15
    t = np.arange(0, dur, 1 / SAMPLE_RATE)
    freq = freq_start + (freq_end - freq_start) * (t / dur)
    w = np.sin(2 * np.pi * freq * t) * 0.3
    w = apply_envelope(w.astype(np.int16), attack=0.005, decay=0.04, sustain=0.5, release=0.05)
    write_wav("move.wav", w)


def gen_destroy():
    """摧毁：短噪声爆炸"""
    s = noise(0.15, 0.2)
    s = apply_envelope(s, attack=0.005, decay=0.05, sustain=0.0, release=0.05)
    write_wav("destroy.wav", s)


def gen_star():
    """占领星星：晶莹叮咚"""
    s = sine_wave(1200, 0.1, 0.5)
    s = apply_envelope(s, attack=0.005, decay=0.05, sustain=0.3, release=0.05)
    write_wav("star.wav", s)


def gen_hover():
    """按钮悬停：极轻微滴声"""
    s = sine_wave(1000, 0.03, 0.1)
    s = apply_envelope(s, attack=0.002, decay=0.01, sustain=0.1, release=0.01)
    write_wav("hover.wav", s)


# ---------- 主入口 ----------
if __name__ == "__main__":
    pygame.mixer.init(frequency=SAMPLE_RATE, size=BIT_DEPTH, channels=1)
    print("生成音效中...")
    gen_click()
    gen_place()
    gen_draw()
    gen_win()
    gen_turn()
    gen_undo()
    gen_error()
    gen_seal()
    gen_recall()
    gen_move()
    gen_destroy()
    gen_star()
    gen_hover()
    print(f"全部音效已生成到 {OUT_DIR} 目录下。")
    pygame.quit()