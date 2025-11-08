"""
Console Printer - 统一的控制台输出美化工具
提供美观的表格、面板、边框等输出功能
"""

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # 如果没有rich，使用colorama作为fallback
    try:
        from colorama import Fore, Style, init
        init(autoreset=True)
        COLORAMA_AVAILABLE = True
    except ImportError:
        COLORAMA_AVAILABLE = False


class ConsolePrinter:
    """
    统一的控制台输出美化工具类
    
    支持：
    - 表格（Table）
    - 面板（Panel）
    - 边框和分隔线
    - 彩色文本
    - 对齐文本
    """
    
    # 全局颜色主题配置
    THEME = {
        # 状态颜色（使用dim使颜色更柔和）
        "status_active": "dim",
        "status_faulty": "dim",
        "status_disconnected": "dim",
        "status_charging": "dim",
        "status_stopped": "dim",
        
        # 消息类型颜色
        "success": "dim",
        "error": "dim",
        "warning": "dim",
        "info": "dim",
        
        # 面板和边框
        "panel_border": "dim",
        "panel_title": "bold",
        
        # 表格
        "table_header": "cyan",
        "table_border": "dim",
        
        # 分隔线和装饰
        "separator": "dim",
        "section_title": "bold",
    }
    
    def __init__(self):
        """初始化ConsolePrinter"""
        if RICH_AVAILABLE:
            self.console = Console()
            self.use_rich = True
        elif COLORAMA_AVAILABLE:
            self.use_rich = False
            self.use_colorama = True
        else:
            self.use_rich = False
            self.use_colorama = False
    
    @classmethod
    def set_theme(cls, theme_updates: dict):
        """
        更新全局颜色主题
        
        Args:
            theme_updates: 要更新的主题配置字典
        """
        cls.THEME.update(theme_updates)
    
    @classmethod
    def get_theme(cls) -> dict:
        """获取当前主题配置"""
        return cls.THEME.copy()
    
    def print_table(self, title: str, headers: list, rows: list, show_header=True):
        """
        打印表格
        
        Args:
            title: 表格标题
            headers: 表头列表
            rows: 数据行列表（每行是一个列表）
            show_header: 是否显示表头
        """
        if self.use_rich:
            header_style = self.THEME["table_header"]
            border_style = self.THEME["table_border"]
            table = Table(title=title, show_header=show_header, box=box.ROUNDED, border_style=border_style)
            for header in headers:
                table.add_column(header, style=header_style, no_wrap=False)
            
            for row in rows:
                table.add_row(*[str(item) for item in row])
            
            self.console.print(table)
        else:
            # Fallback: 使用简单格式
            print(f"\n{title}")
            print("=" * 80)
            if show_header:
                print(" | ".join(headers))
                print("-" * 80)
            for row in rows:
                print(" | ".join(str(item) for item in row))
            print("=" * 80)
    
    def print_panel(self, content: str, title: str = "", style: str = None):
        """
        打印面板（带边框的文本块）
        
        Args:
            content: 面板内容
            title: 面板标题
            style: 样式（rich支持的颜色），如果为None则使用主题默认样式
        """
        if style is None:
            style = self.THEME["panel_border"]
        
        if self.use_rich:
            # 如果有标题，使用主题中的标题样式
            if title and self.THEME["panel_title"]:
                title_style = self.THEME["panel_title"]
                # Rich的Panel title会自动应用样式，这里我们直接传标题
                panel = Panel(content, title=title, box=box.ROUNDED, border_style=style)
            else:
                panel = Panel(content, title=title, box=box.ROUNDED, border_style=style)
            self.console.print(panel)
        else:
            # Fallback: 使用简单格式
            if title:
                print(f"\n[{title}]")
            print("-" * 80)
            print(content)
            print("-" * 80)
    
    def print_section(self, title: str, char: str = "=", width: int = 80):
        """
        打印章节标题（带分隔线）
        
        Args:
            title: 章节标题
            char: 分隔字符
            width: 宽度
        """
        if self.use_rich:
            section_style = self.THEME["section_title"]
            separator_style = self.THEME["separator"]
            self.console.print(f"\n[{separator_style}]{char * width}[/{separator_style}]")
            self.console.print(f"[{section_style}]{title.center(width)}[/{section_style}]")
            self.console.print(f"[{separator_style}]{char * width}[/{separator_style}]\n")
        else:
            print(f"\n{char * width}")
            print(f"{title.center(width)}")
            print(f"{char * width}\n")
    
    def print_menu(self, title: str, items: dict, width: int = 60):
        """
        打印菜单
        
        Args:
            title: 菜单标题
            items: 菜单项字典 {category: [items]}
            width: 菜单宽度
        """
        if self.use_rich:
            menu_content = f"[{self.THEME['panel_title']}]{title}[/{self.THEME['panel_title']}]\n"
            separator_style = self.THEME["separator"]
            menu_content += f"[{separator_style}]{'=' * width}[/{separator_style}]\n"
            
            for category, item_list in items.items():
                menu_content += f"\n[{self.THEME['section_title']}]{category}:[/{self.THEME['section_title']}]\n"
                for item in item_list:
                    menu_content += f"  {item}\n"
            
            menu_content += f"\n[{separator_style}]{'=' * width}[/{separator_style}]"
            panel = Panel(menu_content, box=box.ROUNDED, border_style=self.THEME["panel_border"])
            self.console.print(panel)
        else:
            # Fallback: 使用简单格式
            print(f"\n{'=' * width}")
            print(f"  {title}")
            print(f"{'=' * width}")
            for category, item_list in items.items():
                print(f"\n  {category}:")
                for item in item_list:
                    print(f"  {item}")
            print(f"{'=' * width}\n")
    
    def print_info(self, message: str, prefix: str = "ℹ"):
        """打印信息消息"""
        color = self.THEME["info"]
        if self.use_rich:
            self.console.print(f"[{color}]{prefix}[/{color}] {message}")
        elif self.use_colorama:
            print(f"{Fore.BLUE}{prefix}{Style.RESET_ALL} {message}")
        else:
            print(f"{prefix} {message}")
    
    def print_success(self, message: str, prefix: str = "✓"):
        """打印成功消息"""
        color = self.THEME["success"]
        if self.use_rich:
            self.console.print(f"[{color}]{prefix}[/{color}] {message}")
        elif self.use_colorama:
            print(f"{Fore.GREEN}{prefix}{Style.RESET_ALL} {message}")
        else:
            print(f"{prefix} {message}")
    
    def print_warning(self, message: str, prefix: str = "⚠"):
        """打印警告消息"""
        color = self.THEME["warning"]
        if self.use_rich:
            self.console.print(f"[{color}]{prefix}[/{color}] {message}")
        elif self.use_colorama:
            print(f"{Fore.YELLOW}{prefix}{Style.RESET_ALL} {message}")
        else:
            print(f"{prefix} {message}")
    
    def print_error(self, message: str, prefix: str = "✗"):
        """打印错误消息"""
        color = self.THEME["error"]
        if self.use_rich:
            self.console.print(f"[{color}]{prefix}[/{color}] {message}")
        elif self.use_colorama:
            print(f"{Fore.RED}{prefix}{Style.RESET_ALL} {message}")
        else:
            print(f"{prefix} {message}")
    
    def print_list(self, items: list, title: str = "", numbered: bool = True):
        """
        打印列表
        
        Args:
            items: 项目列表
            title: 列表标题
            numbered: 是否显示编号
        """
        if self.use_rich:
            title_style = self.THEME["section_title"]
            number_style = self.THEME["table_header"]
            if title:
                self.console.print(f"[{title_style}]{title}[/{title_style}]")
            for i, item in enumerate(items, 1):
                if numbered:
                    self.console.print(f"  [{number_style}][{i}][/{number_style}] {item}")
                else:
                    self.console.print(f"  • {item}")
        else:
            if title:
                print(f"\n{title}")
            for i, item in enumerate(items, 1):
                if numbered:
                    print(f"  [{i}] {item}")
                else:
                    print(f"  • {item}")
    
    def print_key_value(self, key: str, value: str, indent: int = 2):
        """打印键值对"""
        if self.use_rich:
            key_style = self.THEME["table_header"]  # 使用表格标题颜色作为键的颜色
            self.console.print(f"{' ' * indent}[{key_style}]{key}:[/{key_style}] {value}")
        else:
            print(f"{' ' * indent}{key}: {value}")
    
    def print_separator(self, char: str = "-", width: int = 80):
        """打印分隔线"""
        if self.use_rich:
            separator_style = self.THEME["separator"]
            self.console.print(char * width, style=separator_style)
        else:
            print(char * width)
    
    def clear(self):
        """清屏"""
        if self.use_rich:
            self.console.clear()
        else:
            import os
            os.system("cls" if os.name == "nt" else "clear")
    
    def print_tree(self, title: str, tree_data: dict):
        """
        打印树形结构
        
        Args:
            title: 树标题
            tree_data: 树形数据字典 {parent: [children]}
        """
        if self.use_rich:
            from rich.tree import Tree
            tree = Tree(title)
            for parent, children in tree_data.items():
                branch = tree.add(f"[bold]{parent}[/bold]")
                for child in children:
                    branch.add(str(child))
            self.console.print(tree)
        else:
            print(f"\n{title}")
            for parent, children in tree_data.items():
                print(f"  {parent}")
                for child in children:
                    print(f"    ├─ {child}")
    
    def print_charging_ticket(self, session_data: dict):
        """
        打印充电完成票据（Ticket）
        
        Args:
            session_data: 包含充电会话信息的字典，应包含：
                - session_id: 会话ID
                - cp_id: 充电桩ID（可选）
                - driver_id: 司机ID（可选）
                - energy_consumed_kwh: 消耗电量（kWh）
                - total_cost: 总费用（欧元）
                - start_time: 开始时间（可选）
                - end_time: 结束时间（可选）
        """
        from datetime import datetime
        
        # 提取数据，设置默认值
        session_id = session_data.get("session_id", "N/A")
        cp_id = session_data.get("cp_id", "N/A")
        driver_id = session_data.get("driver_id", "N/A")
        energy = session_data.get("energy_consumed_kwh", 0.0)
        cost = session_data.get("total_cost", 0.0)
        start_time = session_data.get("start_time", "")
        end_time = session_data.get("end_time", "")
        
        # 格式化时间
        if start_time:
            try:
                if isinstance(start_time, str):
                    start_str = start_time
                else:
                    start_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
            except:
                start_str = str(start_time)
        else:
            start_str = "N/A"
        
        if end_time:
            try:
                if isinstance(end_time, str):
                    end_str = end_time
                else:
                    end_str = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")
            except:
                end_str = str(end_time)
        else:
            end_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建票据内容（类似真实收据格式）
        ticket_lines = []
        
        # 使用主题颜色
        title_style = self.THEME["panel_title"]
        key_style = self.THEME["table_header"]
        value_style = self.THEME["info"]
        separator_style = self.THEME["separator"]
        
        # 标题部分
        ticket_lines.append(f"[{title_style}]{'EV CHARGING SERVICE':^50}[/{title_style}]")
        ticket_lines.append(f"[{separator_style}]{'─' * 50}[/{separator_style}]")
        ticket_lines.append("")
        
        # 会话信息
        ticket_lines.append(f"[{title_style}]Session Information[/{title_style}]")
        ticket_lines.append(f"  [{key_style}]Session ID:[/{key_style}]     [{value_style}]{session_id}[/{value_style}]")
        if cp_id != "N/A":
            ticket_lines.append(f"  [{key_style}]Charging Point:[/{key_style}]  [{value_style}]{cp_id}[/{value_style}]")
        if driver_id != "N/A":
            ticket_lines.append(f"  [{key_style}]Driver ID:[/{key_style}]     [{value_style}]{driver_id}[/{value_style}]")
        ticket_lines.append("")
        
        # 充电详情
        ticket_lines.append(f"[{title_style}]Charging Details[/{title_style}]")
        ticket_lines.append(f"  [{key_style}]Start Time:[/{key_style}]      [{value_style}]{start_str}[/{value_style}]")
        ticket_lines.append(f"  [{key_style}]End Time:[/{key_style}]        [{value_style}]{end_str}[/{value_style}]")
        ticket_lines.append(f"  [{key_style}]Energy Consumed:[/{key_style}] [{value_style}]{energy:.3f} kWh[/{value_style}]")
        ticket_lines.append("")
        
        # 分隔线
        ticket_lines.append(f"[{separator_style}]{'─' * 50}[/{separator_style}]")
        ticket_lines.append("")
        
        # 支付摘要
        ticket_lines.append(f"[{title_style}]Payment Summary[/{title_style}]")
        ticket_lines.append(f"  [{key_style}]Total Cost:[/{key_style}]      [{value_style}]€{cost:.2f}[/{value_style}]")
        ticket_lines.append("")
        
        # 底部
        ticket_lines.append(f"[{separator_style}]{'─' * 50}[/{separator_style}]")
        
        # 打印票据
        ticket_content = "\n".join(ticket_lines)
        if self.use_rich:
            # 使用Panel显示票据，使其更美观
            panel = Panel(
                ticket_content,
                title="Charging Completed",
                box=box.DOUBLE,
                border_style=self.THEME["panel_border"],
                padding=(1, 2)
            )
            self.console.print(panel)
        else:
            # Fallback: 简单格式
            print("\n" + "=" * 50)
            print("CHARGING RECEIPT".center(50))
            print("=" * 50)
            print(f"Session ID: {session_id}")
            if cp_id != "N/A":
                print(f"Charging Point: {cp_id}")
            if driver_id != "N/A":
                print(f"Driver ID: {driver_id}")
            print(f"Start Time: {start_str}")
            print(f"End Time: {end_str}")
            print(f"Energy Consumed: {energy:.3f} kWh")
            print(f"Total Cost: €{cost:.2f}")
            print("=" * 50)
            


# 全局实例，方便使用
_printer = None

def get_printer() -> ConsolePrinter:
    """获取全局ConsolePrinter实例"""
    global _printer
    if _printer is None:
        _printer = ConsolePrinter()
    return _printer

