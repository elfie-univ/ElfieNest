"""身体层设计目标验证测试

验证关节安全限位、脑干反射避险/抚慰、信号过滤等设计目标。
"""

from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.nervous_system.signal_filter import SensoryDamSignalFilter

# =============================================================================
# 关节安全限制测试
# =============================================================================


class TestJointSafetyLimits:
    """验证数字孪生关节的旋转弧度安全限位"""

    def test_joint_above_max_clamped(self):
        """head_yaw最大1.57，set_angle(3.14)返回1.57（被截断）"""
        anatomy = BipedAnatomy()

        actual = anatomy.joints["head_yaw"].set_angle(3.14)

        assert actual == 1.57, f"head_yaw 超出上限 1.57 应被截断，实际返回 {actual}"

    def test_joint_below_min_clamped(self):
        """left_knee最小0.0，set_angle(-1.0)返回0.0（被截断）"""
        anatomy = BipedAnatomy()

        actual = anatomy.joints["left_knee"].set_angle(-1.0)

        assert actual == 0.0, (
            f"left_knee 低于下限 0.0 应被截断到 0.0，实际返回 {actual}"
        )


# =============================================================================
# 信号过滤测试
# =============================================================================


class TestSignalFilter:
    """验证感知大坝对重复信号的过滤"""

    def test_signal_filter_blocks_no_change(self):
        """构造连续相同输入→signal_filter.filter_noise第二次相同输入返回False（被过滤）"""
        flt = SensoryDamSignalFilter()

        # 首次输入（温度 24.0）：last_temperature 为 None，应返回 True
        first = flt.filter_noise({"temperature": 24.0})
        assert first is True, "首次输入相同温度应返回 True（初始化）"

        # 第二次相同输入（温度 24.0）：diff=0 < 0.5，应被过滤
        second = flt.filter_noise({"temperature": 24.0})
        assert second is False, "连续相同温度输入应被过滤返回 False"
