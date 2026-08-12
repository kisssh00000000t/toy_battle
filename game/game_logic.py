"""
核心游戏状态、校验、效果执行。

修复清单：
- FIX: _run_troop_effect 中 opp = self.turn_msg → opp = self.opponent
- FIX: _destroy → _destroy_troop 方法名修正
- FIX: place_troop 中 cp.upper() → cp.color.upper()
- FIX: place_troop 中 old.owner → old_top.owner
- FIX: opponent 属性逻辑错误（原来始终返回 blue）
- FIX: draw 返回值现在被正确使用于日志
"""

import random
from .commands import DeterministicRNG
from .board import GameBoard
from .player import Player
from .troop import Troop
from .constants import HAND_MAX, TERRAIN_DATA, STAR_WIN_GOAL


class GameState:
    """游戏状态机，管理完整游戏流程。

    Attributes:
        board: 棋盘实例
        red/blue: 红蓝双方玩家
        current_player_color: 当前行动方颜色
        winner: 胜者颜色（None 表示未结束）
        game_over: 游戏是否结束
        star_win_goal: 星星胜利目标数
        extra_place_pending: 玩具队长额外放置标记
        turn_msg: 当前回合消息
        action_log: 操作日志（用于回放）
    """

    def __init__(self):
        self.board = GameBoard()
        self.red = Player("red")
        self.blue = Player("blue")
        self.current_player_color = "red"
        self.winner: str | None = None
        self.game_over = False
        self.star_win_goal = STAR_WIN_GOAL
        self.extra_place_pending = False
        self.turn_place_count = 0
        self.turn_msg = ""
        self.action_log: list[dict] = []
        # 确定性回放支持：记录初始牌堆顺序与先手方
        self.initial_decks: dict = {}   # {"red": [key, ...], "blue": [key, ...]}
        self.first_player: str | None = None
        # 拓展包二段技能挂起状态（推土/磁铁/魔方/弩手等需要二次选目标）
        self.pending_skill: dict | None = None
        # 确定性随机数生成器
        self.rng: DeterministicRNG | None = None
        self.rng_seed: int | None = None
        # pending_selection: 玩家选择挂起（回收/召回/封印/回旋等）
        self.pending_selection: dict | None = None
        # _placement_ctx: 放置效果链上下文
        self._placement_ctx: dict | None = None

    @property
    def current_player(self) -> Player:
        """当前行动玩家。"""
        return self.red if self.current_player_color == "red" else self.blue

    @property
    def opponent(self) -> Player:
        """当前行动方的对手。

        FIX: 原代码始终返回 blue，现修正为正确切换。
        """
        return self.blue if self.current_player_color == "red" else self.red

    def setup(self, seed=None) -> None:
        """初始化游戏：洗牌、决定先手、抽初始手牌。

        拓展包增强：根据设置界面的开关决定是否将 8~17 号兵种加入牌池。
        """
        from .config import is_expansion_enabled
        if seed is None:
            import random as _random
            seed = _random.randint(0, 2 ** 31 - 1)
        self.rng_seed = seed
        self.rng = DeterministicRNG(seed)

        self.red.reset()
        self.blue.reset()

        pool_keys = ["joker", 1, 2, 3, 4, 5, 6, 7]
        if is_expansion_enabled():
            pool_keys.extend([8, 9, 10, 11, 12, 13, 14, 15, 16, 17])

        self.red.setup_troops(troop_keys=pool_keys, rng=self.rng)
        self.blue.setup_troops(troop_keys=pool_keys, rng=self.rng)

        self.initial_decks = {
            "red": [t.troop_key for t in self.red.reserve],
            "blue": [t.troop_key for t in self.blue.reserve],
        }

        if self.rng.random() > 0.5:
            self.current_player_color = "red"
            self.red.init_draw(True)
            self.blue.init_draw(False)
        else:
            self.current_player_color = "blue"
            self.blue.init_draw(True)
            self.red.init_draw(False)

        self.first_player = self.current_player_color
        self.game_over = False
        self.winner = None
        self.turn_count = 0
        self.action_log = []
        self.turn_msg = "对局开始！"

    def draw_cards_action(self) -> tuple[bool, str]:
        """抽卡动作。

        手牌≤6抽2，手牌7仅抽1；抽卡后直接结束回合。

        Returns:
            (是否成功, 错误消息)
        """
        if self.game_over:
            return False, "游戏已结束"
        cp = self.current_player
        if len(cp.hand) >= HAND_MAX:
            return False, "手牌已满，无法抽卡"
        if not cp.reserve:
            return False, "备用牌堆已空"
        draw_num = 2 if len(cp.hand) <= 6 else 1
        got = cp.draw(draw_num)
        # FIX: 原代码 draw 返回值未使用，现在记录实际抽取数
        self.turn_msg = f"抽取{got}张卡牌"
        self.end_turn()
        return True, ""

    # ========== 完整放置合法性校验 ==========

    def can_place_troop(self, troop: Troop, node) -> tuple[bool, str]:
        """校验兵种是否可放置到目标节点。

        规则出处：TroopWar 完整玩法手册 - 放置前置校验
        拓展包新增：胶水地形禁放、空位限定兵种、装甲车覆灭门槛、啦啦队光环战力

        Args:
            troop: 待放置兵种
            node: 目标节点

        Returns:
            (是否合法, 错误消息)
        """
        if self.game_over:
            return False, "游戏已结束"
        # 单回合放置限制：已放置1次且无额外放置buff时拒绝
        if self.turn_place_count >= 1 and not self.extra_place_pending:
            return False, "本回合已放置一名士兵"
        if troop not in self.current_player.hand:
            return False, "手牌无该兵种"
        if node is None:
            return False, "选中节点无效"
        # 拓展包：禁锢胶水地形不可放置任何兵种
        if node.terrain_key == "mud":
            return False, "泥沼地形不可放置兵种"
        # 飞钩船长(4)禁止直接放置在敌方HQ（可通过连通推进占领）
        if troop.troop_key == 4:
            if node.is_hq and node.hq_owner is not None and node.hq_owner != self.current_player.color:
                return False, "飞钩船长不能直接放置敌方基地，可以通过移动占领！"
        # 禁止在己方HQ放置棋子
        if node.is_hq and node.hq_owner == self.current_player.color:
            return False, "不能在己方总部放置棋子"
        # 热带泳池偶数限制
        if node.terrain_key == "tropical_pool":
            num = troop.number
            if num is None or num % 2 != 0:
                return False, "热带泳池仅允许偶数兵种放置"
        # 飞钩船长跳过连通校验
        if troop.troop_key != 4:
            if not self.board.is_connected_to_hq(node.nid, self.current_player.color):
                return False, "节点未连通己方总部"
        top = node.top_troop
        # 拓展包：推土机(8)/魔方刺客(10)/爆竹车(16) 只能下在空位
        if troop.troop_key in (8, 10, 16):
            if top is not None:
                return False, "该兵种只能放置在空节点"
            return True, ""
        # 拓展包：越野车(17) 飞跃放置校验（空位 + 可隔子跳跃，无跳板时退化为普通连通放置）
        if troop.troop_key == 17:
            if top is not None:
                return False, "越野车只能飞跃到空节点"
            if self._can_rc_car_jump(node, self.current_player.color):
                return True, ""
            # 无跳板时退化为普通连通校验（越野车无视相邻规则，可直接空投）
            if self.board.is_connected_to_hq(node.nid, self.current_player.color):
                return True, ""
            return False, "越野车无法到达该位置"
        if top is None:
            return True, ""
        # 己方堆叠允许
        if top.owner == self.current_player.color:
            return True, ""
        # 拓展包：使用 _can_cover 统一判定（含装甲车门槛 + 啦啦队光环）
        if self._can_cover(troop, top, node):
            return True, ""
        return False, f"敌方防御数值{top.number}，你的兵种数值不足"

    # ========== 执行放置、兵种、地形效果链 ==========

    def place_troop(self, troop: Troop, node) -> bool:
        """执行兵种放置，包含覆盖处理、效果执行、胜利判定。

        拓展包增强：
        - 黏土怪(14)亡语：被覆盖消灭时地形变为禁锢胶水
        - 爆竹车(16)自毁：放置后消灭所有相邻敌军并自毁
        - 溜溜球(12)回旋：消灭敌军后返回手牌
        - 推土(8)/磁铁(9)/魔方(10)/弩手(11)：挂起二段技能

        Args:
            troop: 待放置兵种
            node: 目标节点

        Returns:
            是否放置成功
        """
        ok, err = self.can_place_troop(troop, node)
        if not ok:
            self.turn_msg = err
            return False
        # 放置计数递增
        self.turn_place_count += 1
        cp = self.current_player
        opp = self.opponent
        old_top = node.top_troop
        # 处理被覆盖敌方单位
        if old_top and old_top.owner != cp.color:
            # 拓展包：黏土怪(14)亡语 — 被消灭时地形永久变为禁锢胶水
            if old_top.troop_key == 14:
                node.terrain_key = "mud"
                self.turn_msg += "(黏土怪化为泥沼) "
            self._destroy_troop(old_top, node)
        # 放入节点堆叠
        node.stack.append(troop)
        cp.hand.remove(troop)
        # 即时胜利：占领敌方HQ
        if node.is_hq and node.hq_owner != cp.color:
            self.winner = cp.color
            self.game_over = True
            if old_top and old_top.owner != cp.color:
                self.turn_msg = f"{cp.color.upper()}夺取敌方总部，直接胜利！"
            else:
                self.turn_msg = f"{cp.color.upper()}占领敌方总部获胜！"
            return True

        t_key = troop.troop_key

        # ── 拓展包瞬发技能 ──
        # ── 16号爆弹邦邦：自毁（金属X站不触发兵效）──
        if t_key == 16 and node.terrain_key != "station_metalx":
            destroyed = 0
            for nb_nid in self.board.get_neighbors(node.nid):
                nb = self.board.get_node(nb_nid)
                if nb and nb.top_troop and nb.top_troop.owner != cp.color:
                    self._destroy_troop(nb.top_troop, nb)
                    destroyed += 1
            node.stack.remove(troop)
            cp.discard.append(troop)
            troop.is_facedown = True
            self.turn_msg = f"爆弹邦邦自毁，带走了周边 {destroyed} 个敌军！"

        # ── 12号回旋闪回：选择相邻敌军消灭后回手 ──
        if t_key == 12:
            adj_enemies = []
            for nb_nid in self.board.get_neighbors(node.nid):
                nb = self.board.get_node(nb_nid)
                if nb and nb.top_troop and nb.top_troop.owner != cp.color:
                    adj_enemies.append(nb)
            if adj_enemies:
                self._placement_ctx = {"troop": troop, "node": node, "phase": "yoyo"}
                self.pending_selection = {
                    "type": "yoyo_target",
                    "options": [{"id": nb.nid, "label": f"节点{nb.nid}"} for nb in adj_enemies],
                    "cancellable": False,
                }
                self.turn_msg = "回旋闪回：选择要消灭的相邻敌军"
                return True

        # ── 二阶段技能兵种 ──
        if t_key in (8, 9, 10, 11):
            self.pending_skill = {"troop_key": t_key, "source_nid": node.nid}
            if self.extra_place_pending:
                self.extra_place_pending = False
            self.turn_msg = f"请选择 {troop.name} 的技能目标（右键跳过）"
            return True

        # ── 正常流程：兵效 → 地效 → 结算 ──
        self._placement_ctx = {"troop": troop, "node": node, "phase": "troop_effect"}
        self._run_troop_effect(troop, node)
        if self.pending_selection:
            return True
        self._continue_placement()
        return True

    def _destroy_troop(self, troop: Troop, node) -> None:
        """销毁节点上的兵种单位，进入对应所有者的弃牌堆。

        Args:
            troop: 要销毁的兵种
            node: 所在节点
        """
        if troop not in node.stack:
            return
        node.stack.remove(troop)
        owner = self.red if troop.owner == "red" else self.blue
        troop.is_facedown = True
        owner.discard.append(troop)

    def _continue_placement(self):
        """选择完成后继续放置效果链。"""
        ctx = self._placement_ctx
        if not ctx or self.pending_selection:
            return
        troop = ctx["troop"]
        node = ctx["node"]
        phase = ctx["phase"]

        if phase in ("troop_effect", "yoyo"):
            ctx["phase"] = "terrain_effect"
            self._run_terrain_effect(troop, node)
            if self.pending_selection:
                return
            self._finalize_placement(troop, node)
        elif phase == "terrain_effect":
            self._finalize_placement(troop, node)

    def _finalize_placement(self, troop, node):
        """星数检查 + 队长额外放置（支持链式）。"""
        cp = self.current_player
        self._placement_ctx = None

        if self._check_star_score():
            return
        if cp.star_points >= self.star_win_goal:
            self.winner = cp.color
            self.game_over = True
            self.turn_msg = f"{cp.color.upper()} 方集齐 {self.star_win_goal} 颗星星，获胜！"
            return

        # 队长链：每次放队长都获得extra；非队长且extra为True时清除
        if troop.troop_key == 2:
            if len(cp.hand) > 0:
                self.extra_place_pending = True
                self.turn_msg += "｜玩具队长：可再放置一张"
            else:
                self.extra_place_pending = False
        elif self.extra_place_pending:
            self.extra_place_pending = False

    # ========== 拓展包：动态战力与覆灭判定 ==========

    def _get_combat_power(self, troop, node) -> int:
        """获取带光环加成的动态最终战力。

        啦啦队手办 (ID:15) 存活时，相邻己方兵种战力临时 +3。
        """
        base_power = troop.number if troop.number else 0
        bonus = 0
        if node:
            for nb_nid in self.board.get_neighbors(node.nid):
                nb = self.board.get_node(nb_nid)
                if nb and nb.top_troop and nb.top_troop.owner == troop.owner:
                    if nb.top_troop.troop_key == 15:
                        bonus += 3
        return base_power + bonus

    def _can_cover(self, attacker_troop, defender_troop, def_node) -> bool:
        """判定攻击方能否覆盖防守方。

        合金装甲车 (ID:13) 只能被基础战力 >7 的单位正面覆盖，
        且免疫推拉类位移技能。
        """
        # Joker 互覆规则（优先于装甲车判定）
        if attacker_troop.troop_key == "joker" or defender_troop.troop_key == "joker":
            return True
        # 合金装甲车叹息之墙特判
        if defender_troop.troop_key == 13:
            return (attacker_troop.number if attacker_troop.number else 0) > 7
        att_power = self._get_combat_power(attacker_troop, def_node)
        def_power = self._get_combat_power(defender_troop, def_node)
        return att_power > def_power

    def _is_node_reachable(self, node, color: str) -> bool:
        """判断节点是否对指定颜色玩家连通可达（飞钩船长跳过此校验）。"""
        return self.board.is_connected_to_hq(node.nid, color)

    def _can_rc_car_jump(self, target_node, color: str) -> bool:
        """判定目标空节点是否是一次合法的越野车(17)'隔子飞跃'。

        条件：目标节点的某个邻居上有棋子（跳板），且跳板另一端
        （起点）是己方连通可达的节点。
        """
        for nb_nid in self.board.get_neighbors(target_node.nid):
            mid_node = self.board.get_node(nb_nid)
            if mid_node and mid_node.top_troop:
                # 跳板存在，检查跳板背后是否有己方可及起点
                behind = self._get_node_in_line(target_node, mid_node)
                if behind and self._is_node_reachable(behind, color):
                    return True
        return False

    def _get_node_in_line(self, node_start, node_dir):
        """几何工具：获取 start→dir 射线方向上的下一个节点。

        依靠叉积共线判断：若 node_dir 的某个邻居与 node_start→node_dir
        方向一致（叉积极小且点积为正），则视为同一直线延伸。
        """
        for nid in self.board.get_neighbors(node_dir.nid):
            if nid == node_start.nid:
                continue
            cand = self.board.get_node(nid)
            if cand is None:
                continue
            dx1 = node_dir.x - node_start.x
            dy1 = node_dir.y - node_start.y
            dx2 = cand.x - node_dir.x
            dy2 = cand.y - node_dir.y
            dot = dx1 * dx2 + dy1 * dy2
            cross = abs(dx1 * dy2 - dy1 * dx2)
            len1 = (dx1 * dx1 + dy1 * dy1) ** 0.5
            len2 = (dx2 * dx2 + dy2 * dy2) ** 0.5
            if dot > 0 and len1 > 0 and len2 > 0 and cross < 0.05 * len1 * len2:
                return cand
        return None

    def _run_troop_effect(self, troop: Troop, node) -> None:
        """执行兵种特殊效果。

        Args:
            troop: 刚放置的兵种
            node: 放置目标节点
        """
        if node.terrain_key == "station_metalx":
            return
        cp = self.current_player
        opp = self.opponent
        key = troop.troop_key
        if key == 1:
            n = 2 if len(cp.hand) < 7 else 1
            drawn = 0
            for _ in range(n):
                if cp.draw(1):
                    drawn += 1
            if drawn > 0:
                self.turn_msg += f"｜小骷髅：抽了{drawn}张牌"
        elif key == 3:
            destroyed = 0
            for nb_nid in self.board.get_neighbors(node.nid):
                nb = self.board.get_node(nb_nid)
                if nb and nb.top_troop and nb.top_troop.owner != cp.color:
                    self._destroy_troop(nb.top_troop, nb)
                    destroyed += 1
            if destroyed > 0:
                self.turn_msg += f"｜重装骑士：清除了{destroyed}个相邻敌军"
        elif key == 5:
            if opp.hand:
                t = self.rng.choice(opp.hand) if self.rng else random.choice(opp.hand)
                opp.discard_troop(t)
                self.turn_msg += f"｜XB-42：弃掉了对手一张手牌"
        elif key == 6:
            if cp.discard and len(cp.hand) < HAND_MAX:
                self.pending_selection = {
                    "type": "recover_discard",
                    "options": [{"id": t.roster_id, "label": t.alias} for t in cp.discard],
                    "cancellable": True,
                }
                self.turn_msg += "｜选择要从弃牌堆回收的兵种"
            elif cp.discard:
                self.turn_msg += "｜手牌已满，无法回收"

    def _get_adjacent_nodes(self, node):
        """返回与给定节点通过单条路径相连的所有节点ID。"""
        return self.board.get_neighbors(node.nid)

    def _remove_troop_from_node(self, troop, node):
        """将指定单位从节点堆叠中安全移除，保持堆叠顺序。"""
        if troop in node.stack:
            node.stack.remove(troop)

    def _run_terrain_effect(self, troop: Troop, node) -> None:
        """执行地形效果（原版规则）。

        特殊基地的地形效果仅对可见兵种（堆叠最上方）生效。

        Args:
            troop: 刚放置的兵种
            node: 放置目标节点
        """
        cp = self.current_player
        opp = self.opponent
        ter = node.terrain_key

        # --- 城堡原野：召回己方任意1枚可见兵种 ---
        if ter == "castle_field":
            candidates = []
            for nd in self.board.nodes.values():
                top = nd.top_troop
                if top and top.owner == cp.color and nd.nid != node.nid:
                    candidates.append(nd)
            if candidates and len(cp.hand) < HAND_MAX:
                self.pending_selection = {
                    "type": "recall",
                    "options": [{"id": nd.nid, "label": f"节点{nd.nid}"} for nd in candidates],
                    "cancellable": True,
                }
                self.turn_msg += "｜选择要召回的己方兵种"
            elif candidates:
                self.turn_msg += "｜手牌已满，无法召回"

        # --- 云之城：从备用牌堆抽1张 ---
        elif ter == "city_of_clouds":
            drawn = cp.draw(1)
            if drawn > 0:
                self.turn_msg += "｜云之城额外抽1张"

        # --- 火山丛林：移动相邻敌方兵种到其相邻基地（忽略放置规则）---
        elif ter == "volcanic_jungle":
            adj_nodes = self._get_adjacent_nodes(node)
            enemy_targets = []
            for nid in adj_nodes:
                nd = self.board.get_node(nid)
                if nd is None:
                    continue
                top = nd.top_troop
                if top and top.owner != cp.color:
                    enemy_targets.append((top, nd))
            if enemy_targets:
                chosen_troop, chosen_node = random.choice(enemy_targets)
                dest_candidates = []
                for nid in self._get_adjacent_nodes(chosen_node):
                    dest = self.board.get_node(nid)
                    if dest is not None and dest.nid != node.nid:
                        dest_candidates.append(dest)
                if dest_candidates:
                    dest = random.choice(dest_candidates)
                    self._remove_troop_from_node(chosen_troop, chosen_node)
                    dest.stack.append(chosen_troop)
                    self.turn_msg += f"｜火山丛林将{chosen_troop.alias}移动到节点{dest.nid}"

        # --- 诅咒墓地：从己方弃牌堆回收1枚兵种 ---
        elif ter == "cursed_cemetery":
            if cp.discard and len(cp.hand) < HAND_MAX:
                self.pending_selection = {
                    "type": "recover_discard",
                    "options": [{"id": t.roster_id, "label": t.alias} for t in cp.discard],
                    "cancellable": True,
                }
                self.turn_msg += "｜选择要从弃牌堆回收的兵种"
            elif cp.discard:
                self.turn_msg += "｜手牌已满，无法回收"

        # --- 战场：封印敌方1张手牌 ---
        elif ter == "battlefield":
            if opp.hand and opp.sealed_troop is None:
                self.pending_selection = {
                    "type": "seal",
                    "options": [{"id": i, "label": f"手牌{i+1}"} for i in range(len(opp.hand))],
                    "cancellable": False,
                }
                self.turn_msg += "｜选择要封印的敌方手牌"

        # 热带泳池：放置限制已在 can_place_troop 中处理
        # 金属X站：兵种效果跳过已在 place_troop 中处理
        # 加勒比海：非对称HQ在地图生成时处理，无放置/触发效果

    def _check_star_score(self) -> bool:
        """检查当前玩家是否完全占领某个区块，是则加星。

        规则出处：完整占领一个区域的所有节点即可获得一颗星星，不重复领取。
        达到星星目标数立即获胜。

        Returns:
            是否触发胜利
        """
        area_map: dict[int, list] = {}
        for nid, nd in self.board.nodes.items():
            aid = nd.area_id
            if aid is None:
                continue
            area_map.setdefault(aid, []).append(nd)
        cp = self.current_player
        for aid, nodes in area_map.items():
            if aid in cp.captured_areas:
                continue
            if all(nd.is_controlled_by(cp.color) for nd in nodes):
                cp.star_points += 1
                cp.captured_areas.add(aid)
                self.turn_msg += f"｜占领区块{aid}，获得一颗星星"
                if cp.star_points >= self.star_win_goal:
                    self.winner = cp.color
                    self.game_over = True
                    self.turn_msg = f"{cp.color.upper()}集齐{self.star_win_goal}颗星星，获胜！"
                    return True
        return False

    def resolve_selection(self, option_id) -> tuple:
        """处理玩家选择，继续效果链。"""
        if not self.pending_selection:
            return False, "当前无待选择项目"
        sel = self.pending_selection
        sel_type = sel["type"]
        cp = self.current_player

        # 取消/跳过
        if option_id is None:
            if not sel.get("cancellable", False):
                return False, "此选择必须执行"
            self.pending_selection = None
            self.turn_msg += "｜已跳过"
            self._continue_placement()
            return True, "已跳过"

        if sel_type == "yoyo_target":
            nid = int(option_id)
            tgt = self.board.get_node(nid)
            if not tgt or not tgt.top_troop or tgt.top_troop.owner == cp.color:
                return False, "无效目标"
            enemy = tgt.top_troop
            self._destroy_troop(enemy, tgt)
            ctx = self._placement_ctx
            troop12 = ctx["troop"]
            src_node = ctx["node"]
            src_node.stack.remove(troop12)
            cp.hand.append(troop12)
            troop12.is_facedown = False
            self.turn_msg = f"回旋闪回消灭了{enemy.alias}，已回到手牌！"
            self.pending_selection = None
            self._continue_placement()
            return True, self.turn_msg

        elif sel_type == "recover_discard":
            target = None
            for t in cp.discard:
                if t.roster_id == option_id:
                    target = t
                    break
            if not target:
                return False, "弃牌堆中无此兵种"
            if len(cp.hand) >= HAND_MAX:
                return False, "手牌已满"
            cp.return_to_hand(target)
            self.turn_msg += f"｜回收了{target.alias}"
            self.pending_selection = None
            self._continue_placement()
            return True, self.turn_msg

        elif sel_type == "recall":
            nid = int(option_id)
            src = self.board.get_node(nid)
            if not src or not src.top_troop or src.top_troop.owner != cp.color:
                return False, "无效目标"
            if len(cp.hand) >= HAND_MAX:
                return False, "手牌已满"
            recalled = src.top_troop
            self._remove_troop_from_node(recalled, src)
            cp.hand.append(recalled)
            recalled.is_facedown = False
            self.turn_msg += f"｜召回了{recalled.alias}"
            self.pending_selection = None
            self._continue_placement()
            return True, self.turn_msg

        elif sel_type == "seal":
            opp = self.opponent
            idx = int(option_id)
            if idx < 0 or idx >= len(opp.hand):
                return False, "无效手牌位置"
            sealed = opp.hand[idx]
            opp.seal_troop(sealed)
            self.turn_msg += f"｜战场封印了对手一张手牌"
            self.pending_selection = None
            self._continue_placement()
            return True, self.turn_msg

        return False, "未知选择类型"

    def execute_pending_skill(self, target_nid: int | None = None) -> tuple[bool, str]:
        """结算二段指向性技能（推土、磁铁、魔方、弩手）。

        由 UI/Dispatcher 在玩家点击目标节点后调用。

        Args:
            target_nid: 玩家选择的目标节点ID；若为 None 则表示主动跳过技能

        Returns:
            (是否成功, 消息)
        """
        if not self.pending_skill:
            return False, "当前无挂起的技能"

        # 【核心修复】：原生支持主动跳过或因无目标自动跳过
        if target_nid is None:
            self.pending_skill = None
            self.turn_msg = "已跳过技能"
            self.end_turn()
            return True, "已跳过技能"

        t_key = self.pending_skill["troop_key"]
        src_node = self.board.get_node(self.pending_skill["source_nid"])
        tgt_node = self.board.get_node(target_nid)
        enemy = tgt_node.top_troop if tgt_node else None
        cp = self.current_player

        if not tgt_node or not enemy or enemy.owner == cp.color:
            return False, "无效目标，必须选择敌方战棋"

        # 免疫判定：合金装甲车(13) 免疫推拉位移
        if enemy.troop_key == 13 and t_key in (8, 9):
            self.turn_msg = "敌方合金装甲车太重了，技能无效！"
            self.pending_skill = None
            self.end_turn()
            return True, "技能被免疫"

        # 免疫判定：泥沼(mud) 地形上的兵种免疫位移效果
        if tgt_node.terrain_key == "mud" and t_key in (8, 9, 10):
            self.turn_msg = "泥沼地形牢牢吸附，位移技能无效！"
            self.pending_skill = None
            self.end_turn()
            return True, "技能被泥沼免疫"

        if t_key == 8:  # 推土机 — 推挤
            behind_node = self._get_node_in_line(src_node, tgt_node)
            tgt_node.stack.remove(enemy)
            if behind_node and behind_node.top_troop is None:
                behind_node.stack.append(enemy)
                self.turn_msg = "推土机将敌方推退了一格！"
            else:
                # 无路可退，秒杀
                self._destroy_troop(enemy, tgt_node)
                self.turn_msg = "后方已无退路，敌方被推土机碾碎！"

        elif t_key == 9:  # 磁钩麦格：牵引到中间节点
            if enemy.troop_key == 13:
                return False, "铁甲布鲁特免疫牵引"
            mid = self._find_pull_mid_node(src_node, tgt_node)
            if mid is None:
                return False, "目标不在2格牵引范围内"
            if mid.top_troop is not None:
                return False, "中间节点被占据，无法牵引"
            tgt_node.stack.remove(enemy)
            mid.stack.append(enemy)
            self.turn_msg = f"磁钩麦格将{enemy.alias}牵引到节点{mid.nid}！"

        elif t_key == 10:  # 魔方刺客 — 换位
            assassin = src_node.top_troop
            if assassin:
                src_node.stack.remove(assassin)
                tgt_node.stack.remove(enemy)
                src_node.stack.append(enemy)     # 敌军被换过来
                tgt_node.stack.append(assassin)  # 刺客切入
                self.turn_msg = "神出鬼没！魔方刺客完成换位！"
            else:
                self.turn_msg = "魔方刺客已不在源节点！"

        elif t_key == 11:  # 弹弩班迪：隔山打牛
            if not self._is_in_line_of_sight(src_node, tgt_node):
                return False, "目标不在直线射界内"
            self._destroy_troop(enemy, tgt_node)
            self.turn_msg = f"弹弩班迪隔山打牛，消灭了{enemy.alias}！"

        self.pending_skill = None
        if self._check_star_score():
            return True, "技能结算完毕"
        self.end_turn()
        return True, "技能结算完毕"

    def end_turn(self) -> None:
        """结束当前回合，切换玩家。"""
        if self.game_over:
            return
        self.extra_place_pending = False
        self.turn_place_count = 0
        # 归还封存手牌
        self.opponent.unseal_troop()
        # 切换玩家
        self.current_player_color = "blue" if self.current_player_color == "red" else "red"
        self.turn_msg = f"当前回合：{self.current_player_color.upper()}"
        self._check_game_end()

    def _check_game_end(self) -> None:
        """检查游戏是否因无操作可行而结束。"""
        if self.game_over:
            return
        cp = self.current_player
        no_draw = not cp.can_draw()
        no_place = True
        for t in cp.hand:
            for nd in self.board.nodes.values():
                ok, _ = self.can_place_troop(t, nd)
                if ok:
                    no_place = False
                    break
            if not no_place:
                break

        both_reserves_empty = not self.red.reserve and not self.blue.reserve

        if (no_draw and no_place) or both_reserves_empty:
            self._settle_game()

    def _settle_game(self):
        """终局结算：比勋章 → 比剩余牌数 → 比场上兵力。"""
        self.game_over = True
        if self.red.star_points != self.blue.star_points:
            self.winner = "red" if self.red.star_points > self.blue.star_points else "blue"
            self.turn_msg = f"双方无牌可出，{self.winner.upper()}方勋章更多，获胜！"
            return
        red_cards = len(self.red.reserve) + len(self.red.hand)
        blue_cards = len(self.blue.reserve) + len(self.blue.hand)
        if red_cards != blue_cards:
            self.winner = "red" if red_cards > blue_cards else "blue"
            self.turn_msg = f"勋章相同，{self.winner.upper()}方剩余牌更多，获胜！"
            return
        red_board = sum(1 for nd in self.board.nodes.values()
                        if nd.top_troop and nd.top_troop.owner == "red")
        blue_board = sum(1 for nd in self.board.nodes.values()
                         if nd.top_troop and nd.top_troop.owner == "blue")
        if red_board != blue_board:
            self.winner = "red" if red_board > blue_board else "blue"
            self.turn_msg = f"牌数相同，{self.winner.upper()}方场上兵力更多，获胜！"
            return
        self.winner = None
        self.turn_msg = "双方势均力敌，平局！"

    def _log_action(self, action_type: str, data: dict) -> None:
        """记录操作日志（用于回放功能）。"""
        self.action_log.append({
            "type": action_type,
            "player": data.get("player", self.current_player_color),
            "data": data
        })

    def get_valid_nodes(self, troop: Troop) -> list:
        """获取指定兵种可放置的所有节点（用于UI高亮）。

        拓展包增强：已通过 can_place_troop 集成新兵种放置规则
        （越野车飞跃、推土/魔方/爆竹空位限定、装甲车覆灭门槛等）。

        Args:
            troop: 待放置兵种

        Returns:
            可放置节点列表
        """
        valid = []
        for nd in self.board.nodes.values():
            ok, _ = self.can_place_troop(troop, nd)
            if ok:
                valid.append(nd)
        return valid

    def get_skill_target_nodes(self) -> list:
        """获取当前挂起二段技能的合法目标节点（用于UI准星高亮）。

        Returns:
            可选目标节点列表；无挂起技能时返回空列表
        """
        if not self.pending_skill:
            return []
        t_key = self.pending_skill["troop_key"]
        src_nid = self.pending_skill["source_nid"]
        cp_color = self.current_player_color
        targets = []

        for nid, nd in self.board.nodes.items():
            enemy = nd.top_troop
            if not enemy or enemy.owner == cp_color:
                continue
            # 装甲车(13)免疫推拉
            if enemy.troop_key == 13 and t_key in (8, 9):
                continue
            # 泥沼(mud)地形上的兵种免疫位移
            if nd.terrain_key == "mud" and t_key in (8, 9, 10):
                continue
            # 推土机(8)：目标必须与源节点相邻
            if t_key == 8:
                if nid in self.board.get_neighbors(src_nid):
                    targets.append(nd)
            # 磁钩麦格(9)：目标距离恰好2（中间节点须空）
            elif t_key == 9:
                if nd.top_troop.troop_key == 13:
                    continue
                src_node = self.board.get_node(src_nid)
                mid = self._find_pull_mid_node(src_node, nd)
                if mid is not None:
                    targets.append(nd)
            # 魔方刺客(10)：目标必须与源节点相邻
            elif t_key == 10:
                if nid in self.board.get_neighbors(src_nid):
                    targets.append(nd)
            # 弹弩班迪(11)：直线射界（中间须有棋子）
            elif t_key == 11:
                src_node = self.board.get_node(src_nid)
                if self._is_in_line_of_sight(src_node, nd):
                    targets.append(nd)
        return targets

    def _is_within_range(self, src_nid: int, tgt_nid: int, max_dist: int = 2) -> bool:
        """BFS判断两节点间最短路径是否在 max_dist 步以内。"""
        from collections import deque
        visited = {src_nid}
        queue = deque([(src_nid, 0)])
        while queue:
            cur, dist = queue.popleft()
            if cur == tgt_nid:
                return True
            if dist >= max_dist:
                continue
            for nb in self.board.get_neighbors(cur):
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, dist + 1))
        return False

    def _is_in_line_of_sight(self, src_node, tgt_node) -> bool:
        """判断目标是否在源节点的直线射程内（中间恰好隔1个子）。"""
        for nb_nid in self.board.get_neighbors(src_node.nid):
            mid = self.board.get_node(nb_nid)
            if mid and mid.top_troop:
                # 中间有子，检查是否与目标共线
                behind = self._get_node_in_line(src_node, mid)
                if behind and behind.nid == tgt_node.nid:
                    return True
        return False

    def _find_pull_mid_node(self, src_node, tgt_node):
        """BFS找src→tgt最短路径上的中间节点（距离恰好2）。"""
        from collections import deque
        parents = {src_node.nid: None}
        q = deque([(src_node.nid, 0)])
        while q:
            cur, dist = q.popleft()
            if cur == tgt_node.nid:
                if dist == 2:
                    return self.board.get_node(parents[tgt_node.nid])
                return None
            if dist >= 2:
                continue
            for nb in self.board.get_neighbors(cur):
                if nb not in parents:
                    parents[nb] = cur
                    q.append((nb, dist + 1))
        return None

    # ─── 序列化与网络 ────────────────────────────────────────

    def to_dict(self) -> dict:
        """完整序列化对局状态（断线重连、存档、网战校验）。"""
        nodes_stack = {}
        for nid, node in self.board.nodes.items():
            nodes_stack[nid] = [t.to_dict() for t in node.stack]
        return {
            "board": self.board.to_dict(),
            "nodes_stack": nodes_stack,
            "current_player_color": self.current_player_color,
            "first_player": getattr(self, "first_player", "red"),
            "turn_count": getattr(self, "turn_count", 0),
            "game_over": self.game_over,
            "winner": self.winner,
            "extra_place_pending": self.extra_place_pending,
            "turn_place_count": self.turn_place_count,
            "pending_skill": self.pending_skill,
            "pending_selection": self.pending_selection,
            "red": self.red.to_dict(),
            "blue": self.blue.to_dict(),
            "rng_seed": self.rng_seed,
            "rng_state": self.rng.to_dict() if self.rng else None,
            "initial_decks": getattr(self, "initial_decks", {}),
        }

    def from_dict(self, data: dict) -> None:
        """从快照反序列化重建对局状态。"""
        from .troop import Troop
        if "board" in data:
            self.board.load_from_dict(data["board"])
        else:
            self.board.load_stack_from_dict(data.get("nodes_stack", {}))
        # 恢复运行时地形变更（泥沼化）
        for nid_str, stack_data in data.get("nodes_stack", {}).items():
            nid = int(nid_str)
            node = self.board.get_node(nid)
            if node:
                node.stack = [Troop.from_dict(d) for d in stack_data]
        self.red.from_dict(data["red"])
        self.blue.from_dict(data["blue"])
        self.current_player_color = data["current_player_color"]
        self.first_player = data.get("first_player", "red")
        self.turn_count = data.get("turn_count", 0)
        self.game_over = data.get("game_over", False)
        self.winner = data.get("winner")
        self.extra_place_pending = data.get("extra_place_pending", False)
        self.turn_place_count = data.get("turn_place_count", 0)
        self.pending_skill = data.get("pending_skill")
        self.pending_selection = data.get("pending_selection")
        self.initial_decks = data.get("initial_decks", {})
        rng_state = data.get("rng_state")
        if rng_state:
            self.rng = DeterministicRNG.from_dict(rng_state)
            self.rng_seed = data.get("rng_seed")

    def apply_net_action(self, action: dict) -> tuple[bool, str]:
        """接收网络对手的操作 JSON 并执行。

        Args:
            action: 动作字典，含 type/player 等字段

        Returns:
            (成功, 消息)
        """
        act_type = action.get("type")
        player_col = action.get("player")
        if player_col != self.current_player_color:
            return False, "非该玩家回合"

        if act_type == "draw":
            ok, err = self.draw_cards_action()
            return ok, err
        elif act_type == "place":
            t_key = action.get("troop_key")
            target_nid = action.get("target_nid")
            node = self.board.get_node(target_nid)
            target_troop = next(
                (t for t in self.current_player.hand if t.troop_key == t_key), None
            )
            if not target_troop or not node:
                return False, "无效的卡牌或目的节点"
            return self.place_troop(target_troop, node), ""
        elif act_type == "end_turn":
            self.end_turn()
            return True, ""
        elif act_type == "cast_skill":
            # 拓展包：二段指向性技能结算
            target_nid = action.get("target_nid")
            if target_nid is None:
                return False, "缺少目标节点"
            ok, msg = self.execute_pending_skill(target_nid)
            return ok, msg
        return False, "未知操作类型"