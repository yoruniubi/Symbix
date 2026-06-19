class toolkit:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name: str, func):
        """注册工具函数"""
        self.tools[name] = func
    
    def edit_file_tool(self, file_path: str, new_content: str):
        """编辑文件工具函数"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            print(f"Error editing file {file_path}: {e}")

    def read_file_tool(self, file_path: str) -> str:
        """读取文件工具函数"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return ""

if __name__ == "__main__":
    tk = toolkit()

    # 示例工具函数
    def example_tool(input_text: str) -> str:
        return f"Processed: {input_text}"

    # 注册工具函数
    tk.register_tool("example_tool", example_tool)

    # 使用注册的工具函数
    result = tk.tools["example_tool"]("Hello, World!")
    print(result)  # 输出: Processed: Hello, World!