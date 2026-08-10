"""
地图编辑器界面。

四文件架构：
- EditorModel：数据模型（节点/边/HQ/撤销重做/序列化）
- EditorCanvas：画布组件（平移/缩放/鼠标交互/绘制）
- EditorToolbar：工具栏（地形拖拽+操作按钮）
- EditorScreen：主界面（集成 canvas+toolbar+事件分发+快捷键）
"""

import logging

import pygame

from .base_screen import BaseScreen
from .editor_model import EditorModel
from .editor_canvas import EditorCanvas
from .editor_toolbar import EditorToolbar, SIDEBAR_W
from .widgets import TOY_COLORS, get_font
from mapgen.map_generator import MapGenerator
from mapgen.map_evaluator import MapEvaluator

logger = logging.getLogger(__name__)

# 画布区域常量
TOP_BAR_H = 50  # 顶部按钮栏高度


class EditorScreen(BaseScreen):
    """地图编辑器主界面。

    集成 EditorModel + EditorCanvas + EditorToolbar，
    负责事件分发、快捷键、状态提示、文件操作。
    """

    def __init__(self, manager):
        super().__init__(manager)

        # 数据模型
        self.model = EditorModel()

        # 画布组件
        self.canvas = EditorCanvas(self.model)
        self._update_canvas_area()

        # 工具栏
        self.toolbar = EditorToolbar(
            sidebar_w=SIDEBAR_W,
            win_w=manager.WIN_W,
            win_h=manager.WIN_H,
        )

        # 连接回调
        self._connect_callbacks()

        # 将工具栏按钮注册到 widgets（供 BaseScreen 事件分发和绘制）
        self.widgets = self.toolbar.all_widgets

        # 拖拽目标检测函数
        self.toolbar.drag_mgr.find_target_func = self._find_editor_node

        # 状态
        self.evaluation = {}
        self.status_msg = ""
        self.status_timer = 0

    def _update_canvas_area(self) -> None:
        """根据窗口尺寸更新画布区域。"""
        w = self.manager.WIN_W
        h = self.manager.WIN_H
        self.canvas.update_area(
            x=SIDEBAR_W,
            y=TOP_BAR_H,
            w=w - SIDEBAR_W,
            h=h - TOP_BAR_H,
        )

    def _connect_callbacks(self) -> None:
        """连接工具栏和画布回调。"""
        # 工具栏回调
        self.toolbar.on_new_map = self._new_map
        self.toolbar.on_save = self._save_map
        self.toolbar.on_load = self._load_map
        self.toolbar.on_eval = self._evaluate_map
        self.toolbar.on_undo = self._undo
        self.toolbar.on_redo = self._redo
        self.toolbar.on_back = self._go_back
        self.toolbar.on_fit_view = self._fit_view
        self.toolbar.on_clear = self._clear_map
        self.toolbar.on_toggle_wiring = self._toggle_wiring_mode
        self.toolbar.on_toggle_star_mode = self._toggle_star_mode
        # 地形选中回调：点击地形工具时，若有选中节点则修改其地形
        self.toolbar.on_terrain_select = self._on_terrain_select

        # 画布回调
        self.canvas.on_edge_added = self._on_edge_added
        self.canvas.on_node_drag_start = self._on_node_drag_start
        # 画布空白点击回调：用当前地形创建节点
        self.canvas.on_empty_click = self._on_canvas_empty_click
        # 画布连线模式变更回调
        self.canvas.on_wiring_mode_changed = self._on_wiring_mode_changed
        # 画布星星模式回调
        self.canvas.on_star_mode_changed = self._on_star_mode_changed
        self.canvas.on_star_place = self._on_star_place
        self.canvas.on_star_remove = self._on_star_remove

    # ─── 操作回调 ────────────────────────────────────────────

    def _new_map(self) -> None:
        """生成新随机地图。"""
        gen = MapGenerator()
        data = gen.generate()
        self.model.load_from_dict(data)
        self.canvas.fit_to_view()
        self._set_status("已生成新地图")

    def _save_map(self) -> None:
        """保存地图到 JSON。"""
        path = self.model.save_json()
        self._set_status(f"已保存到 {path}")

    def _load_map(self) -> None:
        """从 JSON 加载地图。"""
        if self.model.load_json():
            self.canvas.fit_to_view()
            self._set_status("已加载 custom_map.json")
        else:
            self._set_status("未找到 custom_map.json")

    def _evaluate_map(self) -> None:
        """评估地图公平性。"""
        if self.model.hq_red is None or self.model.hq_blue is None:
            self._set_status("请先设置 HQ（选中节点后按 H/J）")
            self.status_timer = 180
            return
        G = self.model.to_graph()
        evaluator = MapEvaluator(G, self.model.hq_red, self.model.hq_blue)
        self.evaluation = evaluator.evaluate()
        total = self.evaluation.get("total", 0)
        self._set_status(f"公平性评分: {total}")
        self.status_timer = 180

    def _undo(self) -> None:
        """撤销。"""
        if self.model.undo():
            self._set_status("已撤销")

    def _redo(self) -> None:
        """重做。"""
        if self.model.redo():
            self._set_status("已重做")

    def _go_back(self) -> None:
        """返回主菜单。"""
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def _fit_view(self) -> None:
        """适配视图。"""
        self.canvas.fit_to_view()
        self._set_status("已适配视图")

    def _clear_map(self) -> None:
        """清空地图。"""
        self.model.push_state()
        self.model.clear()
        self._set_status("已清空地图")

    def _on_edge_added(self, u: int, v: int) -> None:
        """画布连线完成回调。"""
        if self.model.has_edge(u, v):
            self._set_status("道路已存在")
            return
        self.model.push_state()
        self.model.add_edge(u, v)
        self._set_status(f"连接节点{u} ↔ {v}")

    def _on_node_drag_start(self) -> None:
        """节点拖拽开始回调（保存撤销状态）。"""
        self.model.push_state()

    def _on_terrain_select(self, terrain_key: str) -> None:
        """地形工具选中回调：若有选中节点则修改其地形。"""
        nid = self.canvas.selected_node
        if nid is not None and nid in self.model.nodes:
            self.model.push_state()
            self.model.set_terrain(nid, terrain_key)
            self._set_status(f"节点{nid} → {terrain_key}")

    def _on_canvas_empty_click(self, wx: float, wy: float) -> None:
        """画布空白处左键点击回调：用当前地形创建新节点。"""
        # 连线模式或星星模式下空白点击不创建节点
        if self.canvas.wiring_mode or self.canvas.star_mode:
            return
        terrain = self.toolbar.current_terrain
        self.model.push_state()
        new_nid = self.model.add_node(wx, wy, terrain)
        self.canvas.selected_node = new_nid
        self._set_status(f"创建节点{new_nid}({terrain})")

    def _toggle_wiring_mode(self) -> None:
        """切换连线模式。"""
        self.canvas.toggle_wiring_mode()

    def _on_wiring_mode_changed(self, enabled: bool) -> None:
        """连线模式变更回调：同步工具栏状态。"""
        self.toolbar.wiring_mode = enabled
        if enabled:
            self._set_status("连线模式：左键连线，W/ESC退出", 90)
        else:
            self._set_status("退出连线模式")

    # ─── 星星模式 ────────────────────────────────────────────

    def _toggle_star_mode(self) -> None:
        """切换星星放置模式。"""
        self.canvas.toggle_star_mode()

    def _on_star_mode_changed(self, enabled: bool) -> None:
        """星星模式变更回调：同步工具栏状态。"""
        self.toolbar.star_mode = enabled
        if enabled:
            self._set_status("星星模式：左键放置，右键删除，S/ESC退出", 90)
        else:
            self._set_status("退出星星模式")

    def _on_star_place(self, wx: float, wy: float) -> None:
        """画布星星放置回调。"""
        self.model.push_state()
        idx = self.model.add_star_point(wx, wy)
        self._set_status(f"放置星星#{idx}")

    def _on_star_remove(self, wx: float, wy: float) -> None:
        """画布星星删除回调。"""
        idx = self.model.find_star_at(wx, wy)
        if idx is not None:
            self.model.push_state()
            self.model.remove_star_point(idx)
            self._set_status(f"删除星星#{idx}")
        else:
            self._set_status("未找到星星")

    # ─── 拖拽回调 ────────────────────────────────────────────

    def _find_editor_node(self, mx: int, my: int):
        """拖拽目标检测：返回鼠标位置的节点 ID 或 None。"""
        return self.canvas.find_node_at_screen(mx, my)

    def _on_drop_terrain(self, terrain_key: str, nid) -> None:
        """拖拽释放回调：设置节点地形或创建新节点。

        仅当释放在画布区域内才创建节点，释放在工具栏区域则忽略。
        """
        if terrain_key is None:
            return
        # 检查释放位置是否在画布区域内
        mx, my = pygame.mouse.get_pos()
        if mx <= SIDEBAR_W or my <= TOP_BAR_H:
            # 释放在工具栏/按钮区域 → 忽略
            return
        if nid is not None and nid in self.model.nodes:
            # 释放在已有节点上 → 切换地形
            self.model.push_state()
            self.model.set_terrain(nid, terrain_key)
            self._set_status(f"节点{nid} → {terrain_key}")
        elif nid is None:
            # 释放在空白画布上 → 创建新节点
            wx, wy = self.canvas.screen_to_world(mx, my)
            self.model.push_state()
            new_nid = self.model.add_node(wx, wy, terrain_key)
            self._set_status(f"拖拽创建节点{new_nid}({terrain_key})")

    # ─── 事件处理 ────────────────────────────────────────────

    def handle_event(self, event):
        super().handle_event(event)

        # 1. 拖拽中 → 管理器优先拦截
        if self.toolbar.drag_mgr.handle_event(event):
            # 检查是否释放
            if not self.toolbar.drag_mgr.dragging:
                # 拖拽释放
                target = self.toolbar.drag_mgr.current_target
                drag_obj = self.toolbar.drag_mgr.drag_object
                self._on_drop_terrain(drag_obj, target)
                self.toolbar.terrain_drag_key = None
            return

        # 2. 左侧工具栏地形拖拽
        res = self.toolbar.handle_terrain_drag(event)
        if res is not None:
            if isinstance(res, str):
                # 开始拖拽 → 启动 DragDropManager
                self.toolbar.start_terrain_drag(res)
            elif isinstance(res, tuple) and res[0] == "drop":
                # 释放在工具栏自身 → 忽略
                self.toolbar.terrain_drag_key = None
            return

        # 3. 画布交互
        if self.canvas.handle_event(event):
            return

        # 4. 键盘快捷键
        if event.type == pygame.KEYDOWN:
            self._handle_key(event)

    def _handle_key(self, event) -> None:
        """处理键盘快捷键。"""
        mods = pygame.key.get_mods()
        key = event.key

        # ── Ctrl 组合键 ──
        if key == pygame.K_z and mods & pygame.KMOD_CTRL:
            if mods & pygame.KMOD_SHIFT:
                self._redo()
            else:
                self._undo()
            return
        if key == pygame.K_n and mods & pygame.KMOD_CTRL:
            self._new_map()
            return
        if key == pygame.K_s and mods & pygame.KMOD_CTRL:
            self._save_map()
            return
        if key == pygame.K_l and mods & pygame.KMOD_CTRL:
            self._load_map()
            return

        # ── ESC：取消连线 / 退出连线模式 / 退出星星模式 ──
        if key == pygame.K_ESCAPE:
            if self.canvas.wiring_mode:
                self.canvas.set_wiring_mode(False)
                self._set_status("退出连线模式")
            elif self.canvas.star_mode:
                self.canvas.set_star_mode(False)
                self._set_status("退出星星模式")
            elif self.canvas.is_drawing_line:
                self.canvas.cancel_line()
                self._set_status("取消连线")
            return

        # ── W：切换连线模式 ──
        if key == pygame.K_w:
            self._toggle_wiring_mode()
            return

        # ── S：切换星星放置模式 ──
        if key == pygame.K_s and not (mods & pygame.KMOD_CTRL):
            self._toggle_star_mode()
            return

        # ── F：适配视图 ──
        if key == pygame.K_f:
            self._fit_view()
            return

        # ── D / Delete：删除选中节点 ──
        if key in (pygame.K_d, pygame.K_DELETE):
            nid = self.canvas.selected_node
            if nid is not None:
                self.model.push_state()
                self.model.delete_node(nid)
                self._set_status(f"删除节点{nid}")
                self.canvas.selected_node = None
            return

        # ── H：红方 HQ ──
        if key == pygame.K_h:
            nid = self.canvas.selected_node
            if nid is not None:
                self.model.push_state()
                if self.model.hq_red == nid:
                    self.model.set_hq_red(None)
                    self._set_status(f"取消红方HQ(节点{nid})")
                else:
                    self.model.set_hq_red(nid)
                    self._set_status(f"红方HQ设为节点{nid}")
                self.status_timer = 90
            return

        # ── J：蓝方 HQ ──
        if key == pygame.K_j:
            nid = self.canvas.selected_node
            if nid is not None:
                self.model.push_state()
                if self.model.hq_blue == nid:
                    self.model.set_hq_blue(None)
                    self._set_status(f"取消蓝方HQ(节点{nid})")
                else:
                    self.model.set_hq_blue(nid)
                    self._set_status(f"蓝方HQ设为节点{nid}")
                self.status_timer = 90
            return

        # ── E：评估 ──
        if key == pygame.K_e:
            self._evaluate_map()
            return

        # ── F5/F6：保存/加载 ──
        if key == pygame.K_F5:
            self._save_map()
            return
        if key == pygame.K_F6:
            self._load_map()
            return

        # ── 数字 1~9：切换选中节点地形 ──
        num_keys = {
            pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
            pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5,
            pygame.K_7: 6, pygame.K_8: 7, pygame.K_9: 8,
        }
        if key in num_keys:
            idx = num_keys[key]
            from game.constants import TERRAIN_LIST
            if idx < len(TERRAIN_LIST):
                ter_key = TERRAIN_LIST[idx]
                # 同步更新工具栏当前地形
                self.toolbar.current_terrain = ter_key
                nid = self.canvas.selected_node
                if nid is not None:
                    self.model.push_state()
                    self.model.set_terrain(nid, ter_key)
                    self._set_status(f"节点{nid} → {ter_key}")
                else:
                    self._set_status(f"当前地形: {ter_key}")
            return

    # ─── 更新与绘制 ────────────────────────────────────────

    def update(self, dt):
        if self.status_timer > 0:
            self.status_timer -= 1

    def draw(self, surface):
        super().draw(surface)

        # 画布（边、连线预览、节点、悬停提示）
        self.canvas.draw(surface)

        # 拖拽高亮 + 拖影
        def _editor_node_pos(nid):
            return self.model.node_pos(nid)
        self.toolbar.draw_drag(surface, target_pos_func=_editor_node_pos)

        # 左侧工具栏
        self.toolbar.draw_sidebar(surface)

        # 快捷键提示 + 评估分数
        self.toolbar.draw_hints(surface, evaluation=self.evaluation)
        # 连线模式指示器
        self.toolbar.draw_wire_mode_indicator(surface)

        # 状态提示
        self._draw_status(surface)

    def _draw_status(self, surface) -> None:
        """绘制状态提示。"""
        if self.status_timer > 0 and self.status_msg:
            font = get_font(18, style="chinese")
            surf = font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(surf, (self.manager.WIN_W // 2 - surf.get_width() // 2, 80))

    def _set_status(self, msg: str, duration: int = 60) -> None:
        """设置状态提示。"""
        self.status_msg = msg
        self.status_timer = duration

    # ─── 窗口大小变化 ────────────────────────────────────────

    def on_window_resize(self) -> None:
        """窗口大小变化时更新布局。"""
        self._update_canvas_area()
        self.toolbar.update_size(self.manager.WIN_W, self.manager.WIN_H)