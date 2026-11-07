"""
安全拦截层（FACP-004 §5 / FACP-007 P0-1）
高危动作默认禁止，路径与命令走黑名单。
"""

import os
import re


BLACKLIST_PATH_PREFIX = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\ProgramData",
]

# 命令黑名单：只做粗筛，不是唯一防线
SHELL_DENY_PATTERNS = [
    r"rm\s+-rf", r"del\s+/[fsq]", r"format\s+[a-z]:",
    r"diskpart", r"reg\s+delete", r"bcdedit",
    r"shutdown\s+/", r"netsh\s+firewall", r"sc\s+delete",
    r"Remove-Item.*-Recurse", r"rd\s+/s",
]

HIGH_RISK_ACTIONS = {"file_write", "shell_run"}


class StepBlocked(Exception):
    """某一步骤被安全层拦截。"""

    def __init__(self, step_idx: int, reason: str):
        self.step_idx = step_idx
        self.reason = reason
        super().__init__(f"step[{step_idx}] blocked: {reason}")


class SecurityHook:
    def __init__(self, allow_high_risk: bool = False, session_authorized: bool = False):
        self.allow_high_risk = allow_high_risk
        self.session_authorized = session_authorized

    def for_session(self, session_authorized: bool) -> "SecurityHook":
        """按单次协作会话派生子 hook：全局开关沿用，会话授权逐次带入。

        FACP-004 §5.2 要求 L2 同时满足全局与会话两级；会话级授权来源是
        Observer 上对 FSID 的授信，Executor 侧只认调用方带来的布尔结论。
        """
        return SecurityHook(self.allow_high_risk, session_authorized)

    def _path_blocked(self, path: str) -> str | None:
        norm = path.replace("/", "\\").lower()
        for prefix in BLACKLIST_PATH_PREFIX:
            if norm.startswith(prefix.lower()):
                return f"路径命中黑名单: {prefix}"
        if "\\..\\" in norm:
            return "路径包含上跳目录，拒绝执行"
        return None

    def _command_blocked(self, command: str) -> str | None:
        for pattern in SHELL_DENY_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"命令命中黑名单规则: {pattern}"
        return None

    def check_step(self, idx: int, step: dict) -> None:
        action = step.get("action")

        # L0 file_read：不拦执行，但仍受路径黑名单与上跳约束（FACP-004 §3.2）
        if action == "file_read":
            reason = self._path_blocked(step.get("path", ""))
            if reason:
                raise StepBlocked(idx, reason)
            return

        # L0/L1：放行
        if action not in HIGH_RISK_ACTIONS:
            return

        # L2：双开关（FACP-004 §5.2）——全局与会话级同时满足才放行
        if not self.allow_high_risk:
            raise StepBlocked(idx, "高危动作被禁止（ALLOW_HIGH_RISK=false），"
                                   "需全局开关 + 会话级授权")
        if not self.session_authorized:
            raise StepBlocked(idx, "会话未授予高危执行权限"
                                   "（session_high_risk_granted=false）")

        if action == "file_write":
            reason = self._path_blocked(step.get("path", ""))
            if reason:
                raise StepBlocked(idx, reason)
            # 覆盖已有文件属于不可逆操作，要求人工确认
            if step.get("mode", "overwrite") == "overwrite":
                if os.path.exists(step.get("path", "")):
                    raise StepBlocked(idx, "覆盖已存在文件需 require_confirm=true")

        if action == "shell_run":
            reason = self._command_blocked(step.get("command", ""))
            if reason:
                raise StepBlocked(idx, reason)

    def precheck_all(self, steps: list[dict]) -> None:
        """执行前整体预检：任何一步被拦，整个任务不开始。"""
        for idx, step in enumerate(steps):
            self.check_step(idx, step)
