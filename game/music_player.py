"""
BGM 背景音乐单例管理器。

基于 pygame.mixer.music 实现，支持：
- 单例全局访问
- 静音/取消静音切换
- 音量调节（0~100 映射到 0.0~1.0）
- 自动扫描 assets/music/ 目录下的 .ogg/.mp3 文件
- 下一曲/指定曲目播放
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 音乐文件目录 ─────────────────────────────────────────────
_MUSIC_DIR = Path(__file__).parent.parent / "assets" / "music"

# ─── 单例实例 ─────────────────────────────────────────────────
_instance: Optional["MusicPlayer"] = None


class MusicPlayer:
    """BGM 背景音乐管理器（单例模式）。

    Attributes:
        muted: 是否静音
        volume: 当前音量（0~100）
        tracks: 可用音乐文件列表
        current_index: 当前播放曲目索引
    """

    def __init__(self):
        self.muted: bool = False
        self._volume: int = 50          # 内部存储 0~100
        self.tracks: list[str] = []     # 可用音乐文件路径列表
        self.current_index: int = -1
        self._initialized: bool = False
        self.current_track: str = ""    # 当前场景曲目标识（"menu"/"battle"/"victory"/""）
        # ── 菜单BGM主题管理 ──
        self.menu_bgm_file: str = "menu_theme.ogg"  # 当前菜单BGM文件名
        self.active_menu_theme: str = "orchestral"   # 当前主题标识: "orchestral" 或 "math_rock"
        self._MENU_THEMES: dict = {
            "orchestral": "menu_theme.ogg",
            "math_rock": "menu_theme2.ogg",
        }
        # ── Pipi 隐藏彩蛋：切换音乐计数 ──
        self.music_switch_count: int = 0       # 累计切换音乐次数
        self._PIPI_PLAY_THRESHOLD: int = 10    # 播放 pipi.mp3 所需切换次数
        self._pipi_played: bool = False         # 是否已播放过 pipi.mp3
        self._scan_tracks()

    # ─── 单例获取 ──────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "MusicPlayer":
        """获取全局单例。"""
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    # ─── 初始化与扫描 ──────────────────────────────────────────

    def _ensure_mixer(self) -> bool:
        """确保 pygame.mixer 已初始化。"""
        if self._initialized:
            return True
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"pygame.mixer 初始化失败: {e}")
            return False

    def _scan_tracks(self):
        """扫描音乐目录，收集可用曲目。"""
        self.tracks = []
        if _MUSIC_DIR.exists():
            for ext in ("*.ogg", "*.mp3", "*.wav"):
                for f in sorted(_MUSIC_DIR.glob(ext)):
                    self.tracks.append(str(f))
        if self.tracks:
            logger.info(f"扫描到 {len(self.tracks)} 首BGM曲目")
        else:
            logger.info("BGM目录为空或不存在，背景音乐不可用")

    # ─── 播放控制 ──────────────────────────────────────────────

    def play(self, track_index: Optional[int] = None, loops: int = -1):
        """播放指定曲目或当前曲目。

        Args:
            track_index: 曲目索引，None 则播放当前/第一首
            loops: 循环次数，-1 为无限循环
        """
        if not self._ensure_mixer():
            return
        if not self.tracks:
            return

        if track_index is not None:
            self.current_index = track_index % len(self.tracks)
        elif self.current_index < 0:
            self.current_index = 0

        track_path = self.tracks[self.current_index]
        try:
            import pygame
            pygame.mixer.music.load(track_path)
            effective_vol = 0.0 if self.muted else self._volume / 100.0
            pygame.mixer.music.set_volume(effective_vol)
            pygame.mixer.music.play(loops)
            logger.info(f"BGM播放: {Path(track_path).name} (音量={self._volume}%)")
        except Exception as e:
            logger.warning(f"BGM播放失败: {e}")

    def stop(self):
        """停止播放。"""
        self.current_track = ""
        if not self._ensure_mixer():
            return
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass

    def next_track(self, loops: int = -1):
        """切换到下一首曲目。"""
        if not self.tracks:
            return
        self.current_index = (self.current_index + 1) % len(self.tracks)
        self.play(loops=loops)

    # ─── 音量控制 ──────────────────────────────────────────────

    @property
    def volume(self) -> int:
        """当前音量（0~100）。"""
        return self._volume

    @volume.setter
    def volume(self, value: int):
        self._volume = max(0, min(100, value))
        self._apply_volume()

    def _apply_volume(self):
        """将音量应用到 pygame mixer。"""
        if not self._ensure_mixer():
            return
        try:
            import pygame
            effective_vol = 0.0 if self.muted else self._volume / 100.0
            pygame.mixer.music.set_volume(effective_vol)
        except Exception:
            pass

    def toggle_mute(self) -> bool:
        """切换静音状态，返回新的静音状态。"""
        self.muted = not self.muted
        self._apply_volume()
        logger.info(f"BGM静音: {'开' if self.muted else '关'}")
        return self.muted

    def volume_up(self, step: int = 10):
        """音量增加。"""
        self.volume = self._volume + step

    def volume_down(self, step: int = 10):
        """音量减少。"""
        self.volume = self._volume - step

    # ─── 状态查询 ──────────────────────────────────────────────

    @property
    def is_playing(self) -> bool:
        """是否正在播放。"""
        if not self._ensure_mixer():
            return False
        try:
            import pygame
            return pygame.mixer.music.get_busy()
        except Exception:
            return False

    @property
    def is_muted(self) -> bool:
        """是否静音（兼容 BGM API）。"""
        return self.muted

    @property
    def bgm_volume(self) -> float:
        """当前音量（0.0~1.0 浮点，兼容 BGM API）。"""
        return self._volume / 100.0

    @property
    def current_track_name(self) -> str:
        """当前曲目文件名。"""
        if 0 <= self.current_index < len(self.tracks):
            return Path(self.tracks[self.current_index]).stem
        return ""

    @property
    def track_count(self) -> int:
        """可用曲目数量。"""
        return len(self.tracks)

    # ─── BGM 兼容 API ─────────────────────────────────────────

    def play_bgm(self, filename: str = None, loops: int = -1):
        """按文件名播放指定BGM，或播放当前/第一首。

        Args:
            filename: 音乐文件名（如 "battle_theme.ogg"），None 则播放当前曲目
            loops: 循环次数，-1 为无限循环
        """
        if not self._ensure_mixer():
            return
        if not self.tracks:
            logger.warning("BGM曲目列表为空，无法播放")
            return

        if filename:
            # 按文件名查找曲目索引
            for i, track_path in enumerate(self.tracks):
                if Path(track_path).name == filename:
                    self.current_track = ""  # 直接调用play_bgm时重置场景标记
                    self.play(track_index=i, loops=loops)
                    return
            # 未找到精确匹配，尝试模糊匹配
            for i, track_path in enumerate(self.tracks):
                if filename in Path(track_path).name:
                    self.current_track = ""
                    self.play(track_index=i, loops=loops)
                    return
            logger.warning(f"未找到BGM文件: {filename}，播放第一首")
            self.current_track = ""
            self.play(track_index=0, loops=loops)
        else:
            self.current_track = ""
            self.play(loops=loops)

    def set_volume(self, vol: float):
        """设置音量（0.0~1.0 浮点，兼容 BGM API）。"""
        self.volume = int(max(0.0, min(1.0, vol)) * 100)

    # ─── 场景 BGM 方法 ────────────────────────────────────────

    def play_menu_bgm(self, loops: int = -1):
        """播放主菜单背景音乐（menu_theme）。

        如果当前已在播放 menu 主题曲，则不重复重启。
        支持 menu_theme.ogg (交响版) 和 menu_theme2.ogg (数摇版) 切换。
        """
        if self.current_track == "menu" and self.is_playing:
            return
        self.current_track = "menu"
        self.play_bgm(self.menu_bgm_file, loops=loops)

    def switch_menu_bgm(self) -> str:
        """切换菜单BGM主题（交响版 ↔ 数摇版循环切换）。

        Returns:
            切换后的主题标识 ("orchestral" 或 "math_rock")
        """
        theme_keys = list(self._MENU_THEMES.keys())
        current_idx = theme_keys.index(self.active_menu_theme) if self.active_menu_theme in theme_keys else 0
        next_idx = (current_idx + 1) % len(theme_keys)
        self.active_menu_theme = theme_keys[next_idx]
        self.menu_bgm_file = self._MENU_THEMES[self.active_menu_theme]

        # 如果当前正在播放菜单BGM，立即切换到新曲目
        if self.current_track == "menu" and self.is_playing:
            self.play_bgm(self.menu_bgm_file)

        # ── Pipi 隐藏彩蛋：累计切换次数，达到阈值后播放 pipi.mp3 ──
        self.music_switch_count += 1
        if (self.music_switch_count >= self._PIPI_PLAY_THRESHOLD
                and not self._pipi_played):
            self._pipi_played = True
            self._play_pipi_easter_egg()

        logger.info(f"菜单BGM切换为: {self.active_menu_theme} ({self.menu_bgm_file})")
        return self.active_menu_theme

    def get_current_bgm_name(self) -> str:
        """获取当前菜单BGM主题的显示名称。

        Returns:
            中文显示名称，如 "交响版" 或 "数摇版"
        """
        _DISPLAY_NAMES = {
            "orchestral": "交响版",
            "math_rock": "数摇版",
        }
        return _DISPLAY_NAMES.get(self.active_menu_theme, "交响版")

    def _play_pipi_easter_egg(self) -> None:
        """播放 Pipi 隐藏彩蛋音效（pipi.mp3）。

        切换菜单BGM累计达到阈值后自动触发，仅播放一次。
        播放完毕后自动恢复之前的菜单BGM。
        """
        pipi_path = _MUSIC_DIR / "pipi.mp3"
        if not pipi_path.exists():
            logger.warning(f"Pipi 彩蛋音频不存在: {pipi_path}")
            return
        try:
            import pygame
            if not self._ensure_mixer():
                return
            logger.info(f"🎵 Pipi 隐藏彩蛋触发！播放 {pipi_path.name}")
            # 暂停当前BGM
            pygame.mixer.music.pause()
            # 播放 pipi.mp3（播放一次，不循环）
            pygame.mixer.music.load(str(pipi_path))
            effective_vol = 0.0 if self.muted else self._volume / 100.0
            pygame.mixer.music.set_volume(effective_vol)
            pygame.mixer.music.play(0)  # loops=0，播放一次
            # 设置回调：播放完毕后恢复菜单BGM
            def _restore_bgm():
                try:
                    if self.current_track == "menu":
                        self.play_bgm(self.menu_bgm_file)
                except Exception:
                    pass
            # 使用 pygame 事件回调恢复BGM（设置 MUSIC_END 事件）
            try:
                pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
            except Exception:
                pass
            logger.info("🎵 Pipi 彩蛋音频播放完成，将恢复菜单BGM")
        except Exception as e:
            logger.warning(f"Pipi 彩蛋播放失败: {e}")

    def play_battle_bgm(self, loops: int = -1):
        """播放战斗对局背景音乐（battle_theme）。

        如果当前已在播放 battle 主题曲，则不重复重启。
        """
        if self.current_track == "battle" and self.is_playing:
            return
        self.current_track = "battle"
        self.play_bgm("battle_theme.ogg", loops=loops)

    def play_victory_bgm(self, loops: int = -1):
        """播放胜利凯旋背景音乐（victory_theme）。

        如果当前已在播放 victory 主题曲，则不重复重启。
        """
        if self.current_track == "victory" and self.is_playing:
            return
        self.current_track = "victory"
        self.play_bgm("victory_theme.ogg", loops=loops)


# ─── 模块级便捷函数与 BGM 单例 ──────────────────────────────

def get_music_player() -> MusicPlayer:
    """获取全局 MusicPlayer 单例。"""
    return MusicPlayer.get_instance()


# BGM 全局单例 — 供 UI 层直接 from game.music_player import BGM 使用
BGM = MusicPlayer.get_instance()