"""
全局 UI 管理器 — ESC 逐级关闭 + Space 一键居中 + 弹窗栈。

统一管理 UI 层级优先级，确保按键响应符合直觉：
  ESC:  弹窗 > 悬浮面板 > 选中状态
  Space: 一键居中到当前玩家基地

零侵入原则：仅被 ui/ 目录引用，不依赖 game/ 层具体实现。
"""

import pygame


class UIManager:
    """全局 UI 事件管理器。

    管理弹窗栈、悬浮提示、选中状态，提供 ESC 逐级关闭和 Space 居中功能。
    通过回调接口与 GameScreen 解耦，不直接引用游戏逻辑层。

    Attributes:
        camera: Camera 实例，用于 Space 居中
        active_modals: 弹窗栈（后进先出）
        active_tooltips: 悬浮提示列表
    """

    def __init__(self, camera):
        self.camera = camera

        # UI 层级栈
        self.active_modals = []       # 弹窗栈 (如模式选择、确认框)
        self.active_tooltips = []     # 信息面板/悬浮提示

        # 回调接口（由 GameScreen 注入）
        self._on_deselect = None      # 取消选中回调
        self._on_clear_tooltips = None  # 清除提示回调
        self._on_get_base_pos = None  # 获取基地坐标回调

    # ═══════════════════════════════════════════════════════════
    #  回调注册
    # ═══════════════════════════════════════════════════════════

    def set_callbacks(self, on_deselect=None, on_clear_tooltips=None,
                      on_get_base_pos=None):
        """注册回调接口，实现与 GameScreen 的解耦。

        Args:
            on_deselect: 取消选中回调（无参数），返回是否成功
            on_clear_tooltips: 清除提示回调（无参数），返回是否成功
            on_get_base_pos: 获取基地坐标回调（无参数），返回 (wx, wy)
        """
        self._on_deselect = on_deselect
        self._on_clear_tooltips = on_clear_tooltips
        self._on_get_base_pos = on_get_base_pos

    # ═══════════════════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════════════════

    def handle_event(self, event):
        """统一事件入口：顶层 Modal 强制独占所有鼠标与键盘事件。

        优先级：Modal > 键盘快捷键 > Camera > 默认传递

        Args:
            event: pygame 事件

        Returns:
            bool: True 表示事件已被消费，不再传递
        """
        # 1. 如果存在二级弹窗，所有键盘和鼠标事件全部直接交给顶层 Modal，
        #    并 return True 阻断穿透！
        if self.active_modals and event.type in (
            pygame.KEYDOWN, pygame.KEYUP,
            pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION, pygame.MOUSEWHEEL
        ):
            top_modal = self.active_modals[-1]
            if hasattr(top_modal, 'handle_event'):
                top_modal.handle_event(event)
            return True  # 核心：直接阻断，禁止传给底层的一级菜单或相机！

        # 2. 正常场景键盘快捷键
        if event.type == pygame.KEYDOWN:
            # Space: 一键居中到玩家基地
            if event.key == pygame.K_SPACE:
                return self._handle_space()

            # ESC: 逐级关闭
            if event.key == pygame.K_ESCAPE:
                return self.handle_esc()

        # 3. 相机事件（拖拽/缩放）
        if self.camera.handle_event(event):
            return True

        return False

    def handle_esc(self):
        """ESC 逐级关闭链条。

        优先级：弹窗 > 悬浮面板 > 选中状态

        Returns:
            bool: True 表示有内容被关闭
        """
        # 第一优先级：关闭最顶层 Modal 弹窗
        if self.active_modals:
            modal = self.active_modals.pop()
            if hasattr(modal, 'close'):
                modal.close()
            return True

        # 第二优先级：关闭所有悬浮提示/信息面板
        if self.active_tooltips:
            self.active_tooltips.clear()
            if self._on_clear_tooltips:
                self._on_clear_tooltips()
            return True

        # 第三优先级：取消手牌/地块选择
        if self._on_deselect:
            result = self._on_deselect()
            if result:
                return True

        return False

    def _handle_space(self):
        """Space 一键居中到当前玩家基地。"""
        if self._on_get_base_pos:
            base_pos = self._on_get_base_pos()
            if base_pos:
                wx, wy = base_pos
                self.camera.center_on_world_pos(wx, wy, smooth=True)
                return True
        return False

    # ═══════════════════════════════════════════════════════════
    #  弹窗绘制
    # ═══════════════════════════════════════════════════════════

    def draw_modals(self, surface):
        """绘制所有弹窗（从底到顶）。"""
        for modal in self.active_modals:
            if hasattr(modal, 'draw'):
                modal.draw(surface)

    # ═══════════════════════════════════════════════════════════
    #  弹窗管理
    # ═══════════════════════════════════════════════════════════

    def push_modal(self, modal):
        """压入弹窗到栈顶。

        Args:
            modal: 弹窗对象，需实现 handle_event(event) 和 close() 方法
        """
        self.active_modals.append(modal)

    def pop_modal(self):
        """弹出栈顶弹窗。

        Returns:
            弹窗对象，或 None（栈为空时）
        """
        if self.active_modals:
            return self.active_modals.pop()
        return None

    def clear_modals(self):
        """关闭所有弹窗。"""
        for modal in reversed(self.active_modals):
            if hasattr(modal, 'close'):
                modal.close()
        self.active_modals.clear()

    # ═══════════════════════════════════════════════════════════
    #  悬浮提示管理
    # ═══════════════════════════════════════════════════════════

    def push_tooltip(self, tooltip):
        """添加悬浮提示。

        Args:
            tooltip: 提示对象
        """
        self.active_tooltips.append(tooltip)

    def clear_tooltips(self):
        """清除所有悬浮提示。"""
        self.active_tooltips.clear()
        if self._on_clear_tooltips:
            self._on_clear_tooltips()

    # ═══════════════════════════════════════════════════════════
    #  状态查询
    # ═══════════════════════════════════════════════════════════

    @property
    def has_modal(self):
        """是否有弹窗打开。"""
        return len(self.active_modals) > 0

    @property
    def has_tooltip(self):
        """是否有悬浮提示。"""
        return len(self.active_tooltips) > 0