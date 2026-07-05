"""CompressGuard - 压缩守卫

防止递归压缩和状态污染：
- 守卫 1: 压缩过程中禁止再次触发压缩（防递归）
- 守卫 2a: 工具执行中禁止触发压缩（防状态污染）
- 守卫 2b: 流式响应中禁止触发压缩（防状态污染）
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CompressGuard:
    """压缩守卫：防止递归压缩和状态污染

    状态机：
        空闲 ──用户请求──→ 处理中
          ↑                   │
          │                   ├──工具调用──→ 工具执行中
          │                   │                │
          │                   │                └──工具返回──→ 处理中
          │                   │
          │                   ├──流式响应──→ 流式写入中
          │                   │                │
          │                   │                └──流式结束──→ 空闲
          │                   │
          │                   └──达到阈值──→ 检查守卫
          │                                   │
          │                              can_compress()?
          │                               │          │
          │                              是         否
          │                               │          │
          │                               ▼          └──→ 跳过本轮
          └──────压缩完成──────────── 压缩中
    """

    def __init__(self) -> None:
        self._compressing = False       # 是否正在执行压缩
        self._tool_executing = False    # 是否正在执行工具
        self._streaming = False         # 是否正在流式响应

    # === 守卫 1: 防递归 ===

    def enter_compress(self) -> None:
        """进入压缩状态，若已压缩中则抛出异常"""
        if self._compressing:
            raise RuntimeError("检测到递归压缩，已阻止")
        self._compressing = True
        logger.debug("CompressGuard: 进入压缩状态")

    def exit_compress(self) -> None:
        """退出压缩状态"""
        self._compressing = False
        logger.debug("CompressGuard: 退出压缩状态")

    def is_compressing(self) -> bool:
        """是否正在压缩中"""
        return self._compressing

    # === 守卫 2a: 防状态污染（工具执行） ===

    def enter_tool_execution(self) -> None:
        """进入工具执行状态"""
        self._tool_executing = True
        logger.debug("CompressGuard: 进入工具执行状态")

    def exit_tool_execution(self) -> None:
        """退出工具执行状态"""
        self._tool_executing = False
        logger.debug("CompressGuard: 退出工具执行状态")

    # === 守卫 2b: 防状态污染（流式响应） ===

    def enter_streaming(self) -> None:
        """进入流式响应状态"""
        self._streaming = True
        logger.debug("CompressGuard: 进入流式响应状态")

    def exit_streaming(self) -> None:
        """退出流式响应状态"""
        self._streaming = False
        logger.debug("CompressGuard: 退出流式响应状态")

    # === 综合判断 ===

    def can_compress(self) -> bool:
        """综合判断是否允许触发压缩"""
        if self._compressing:
            return False    # 守卫 1: 正在压缩中，防递归
        if self._tool_executing:
            return False    # 守卫 2a: 工具执行中，防状态污染
        if self._streaming:
            return False    # 守卫 2b: 流式响应中，防状态污染
        return True

    def __repr__(self) -> str:
        return (
            f"CompressGuard(compressing={self._compressing}, "
            f"tool_executing={self._tool_executing}, "
            f"streaming={self._streaming})"
        )
