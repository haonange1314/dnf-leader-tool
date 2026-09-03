from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDefinition:
    code: str
    name: str
    module: str
    description: str


PERMISSIONS = (
    PermissionDefinition("DUNGEON_READ", "查看副本", "副本管理", "查看副本及版本规则"),
    PermissionDefinition("DUNGEON_WRITE", "维护副本", "副本管理", "创建、编辑和发布副本版本"),
    PermissionDefinition("ROSTER_READ", "查看人员", "人员管理", "查看玩家和角色资料"),
    PermissionDefinition("ROSTER_WRITE", "维护人员", "人员管理", "新增、编辑、排序和停用人员"),
    PermissionDefinition(
        "ROSTER_IMPORT", "导入人员", "人员管理", "预览、确认人员导入并下载错误明细"
    ),
    PermissionDefinition("SCHEDULE_READ", "查看排表", "排表管理", "查看排表、版本及生成记录"),
    PermissionDefinition("SCHEDULE_WRITE", "编辑排表", "排表管理", "创建、复制和人工编辑排表"),
    PermissionDefinition(
        "SCHEDULE_GENERATE", "智能排表", "排表管理", "执行自动排表和自然语言规则操作"
    ),
    PermissionDefinition("SCHEDULE_PUBLISH", "发布排表", "排表管理", "发布、恢复和归档排表"),
    PermissionDefinition("SCHEDULE_EXPORT", "导出排表", "排表管理", "下载排表图片、Excel 和文本"),
    PermissionDefinition("SHARE_MANAGE", "管理分享", "排表管理", "创建、查看和撤销分享链接"),
    PermissionDefinition("USER_READ", "查看用户", "系统管理", "查看用户账号和会话摘要"),
    PermissionDefinition("USER_WRITE", "管理用户", "系统管理", "创建、编辑、停用用户并撤销会话"),
    PermissionDefinition("ROLE_READ", "查看角色权限", "系统管理", "查看角色和权限矩阵"),
    PermissionDefinition("ROLE_WRITE", "管理角色权限", "系统管理", "创建角色并调整权限"),
    PermissionDefinition("AUDIT_READ", "查看操作日志", "系统管理", "检索和查看操作审计记录"),
)

ALL_PERMISSION_CODES = frozenset(permission.code for permission in PERMISSIONS)
EDITOR_PERMISSION_CODES = frozenset(
    code
    for code in ALL_PERMISSION_CODES
    if code not in {"USER_READ", "USER_WRITE", "ROLE_READ", "ROLE_WRITE", "AUDIT_READ"}
)
VIEWER_PERMISSION_CODES = frozenset(
    {"DUNGEON_READ", "ROSTER_READ", "SCHEDULE_READ", "SCHEDULE_EXPORT"}
)
