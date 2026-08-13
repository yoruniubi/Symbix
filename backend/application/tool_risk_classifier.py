from typing import Dict, Any, Literal, Tuple

RiskLevel = Literal["safe", "medium", "high"]


class ToolRiskClassifier:
    """工具调用风险分类器"""
    
    # 系统关键路径
    CRITICAL_PATHS = [
        "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/boot", "/sys", "/proc",
        "C:\\Windows", "C:\\Program Files", "C:\\ProgramData",
        "/System", "/Library",  # macOS
    ]
    
    # 危险命令关键词
    DANGEROUS_COMMANDS = [
        "rm -rf", "del /f", "format", "mkfs", "dd if=", 
        "chmod 777", "chown root",
        "> /dev/", "curl", "wget", "nc ", "netcat",
        "sudo ", "su ", "eval", "exec",
    ]
    
    # 安全的只读工具
    SAFE_TOOLS = {
        "read_file", "list_files", "search_files", "read_multiple_files",
        "java_class_scanner", "file_structure_scanner", "code_quality_scanner",
        # 桌宠动画工具：仅触发 UI 动画/表情，无文件或命令副作用
        "emit_pet_action", "check_agent_status", "play_status_animation",
    }
    
    # 需要审批的中等风险工具
    MEDIUM_RISK_TOOLS = {
        "create_file", "write_file", "batch_code_modifier",
    }
    
    # 高危工具
    HIGH_RISK_TOOLS = {
        "delete_file", "execute_command",
    }
    
    def classify_tool_call(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Tuple[RiskLevel, str]:
        """
        分类工具调用的风险等级
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            (risk_level, reason) 风险等级和原因
        """
        # 1. 检查是否为安全工具
        if tool_name in self.SAFE_TOOLS:
            return "safe", "只读操作，无风险"
        
        # 2. 检查是否为高危工具
        if tool_name in self.HIGH_RISK_TOOLS:
            # 进一步检查参数
            if tool_name == "delete_file":
                path = arguments.get("path", "")
                if self._is_critical_path(path):
                    return "high", f"删除系统关键文件：{path}"
                return "high", f"删除文件：{path}"
            
            elif tool_name == "execute_command":
                command = arguments.get("command", "")
                if self._is_dangerous_command(command):
                    return "high", f"执行危险命令：{command}"
                return "high", f"执行系统命令：{command}"
        
        # 3. 检查是否为中等风险工具
        if tool_name in self.MEDIUM_RISK_TOOLS:
            # 检查是否涉及系统路径
            if tool_name in ("create_file", "write_file", "batch_code_modifier"):
                path = arguments.get("path", "")
                if self._is_critical_path(path):
                    return "high", f"修改系统关键文件：{path}"
                return "medium", f"修改文件：{path}"
        
        # 4. 未知工具，默认中等风险
        return "medium", f"未知工具需要审批：{tool_name}"
    
    def _is_critical_path(self, path: str) -> bool:
        """检查是否为系统关键路径"""
        path_lower = path.lower()
        return any(
            path_lower.startswith(critical.lower()) 
            for critical in self.CRITICAL_PATHS
        )
    
    def _is_dangerous_command(self, command: str) -> bool:
        """检查是否为危险命令"""
        command_lower = command.lower()
        return any(
            dangerous in command_lower 
            for dangerous in self.DANGEROUS_COMMANDS
        )
