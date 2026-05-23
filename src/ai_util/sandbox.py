from datetime import datetime
import os
from pathlib import Path
import subprocess
import requests
import stat
from ai_util.tools import Tools


class Sandbox:
    def __init__(
        self,
        sandbox_dir: str,
        allow_file_access: bool = True,
        allow_network_access: bool = True,
        allow_raw_network_data: bool = True,
        allow_syscmd_access: bool = False,
        file_access_mode: int = 1,  # 0: only sandbox, 1: progressive, 2: full
        file_progressive_access_mode: int = 0,  # 0: white list, 1: black list
        file_progressive_access_list: list[str] | None = None,
    ) -> None:
        self.sandbox_dir = sandbox_dir
        self.p_sandbox_dir = Path(sandbox_dir)

        self.allow_file_access = allow_file_access
        self.allow_network_access = allow_network_access
        self.allow_raw_network_data = allow_raw_network_data
        self.allow_syscmd_access = allow_syscmd_access

        self.file_access_mode = file_access_mode

        self.file_progressive_access_mode = file_progressive_access_mode
        self.file_progressive_access_list = file_progressive_access_list or []

        self.sandbox_tools = [
            self.read_file,
            self.readlines,
            self.write_file,
            self.write_lines,
            self.insert_lines,
            self.run_syscmd,
            self.get_request,
            self.head_request,
            self.post_request,
            self.put_request,
            self.delete_request,
            self.options_request,
            self.listdir,
            self.get_sandbox_dir,
        ]

    def check_can_access_file(self, file_path: str) -> int:
        """
        检查文件访问权限。

        :return: 0 = 无权限, 1 = 只读, 2 = 完全访问
        """
        if not self.allow_file_access:
            return 0

        if self.file_access_mode == 0:
            if self.is_child_dir(file_path):
                return 2
            return 0

        elif self.file_access_mode == 1:
            if self.is_child_dir(file_path):
                return 2
            if self.file_progressive_access_mode == 0:
                if file_path in self.file_progressive_access_list:
                    return 1
            elif self.file_progressive_access_mode == 1:
                if file_path not in self.file_progressive_access_list:
                    return 1
            return 0

        elif self.file_access_mode == 2:
            return 2

        else:
            raise ValueError(f"Invalid file access mode: {self.file_access_mode}")
    
    def is_child_dir(self, path: str) -> bool:
        """判断是否为沙箱目录下的子目录"""
        child = Path(os.path.abspath(path))
        try:
            child.relative_to(self.p_sandbox_dir)
            return True
        except (ValueError, OSError):
            return False

    def can_access(self, path: str, expect: int) -> bool:
        """判断是否拥有 >= expect 级的访问权限"""
        access_mode = self.check_can_access_file(path)
        return access_mode >= expect

    def _read_lines(self, path: str) -> list[str]:
        """读取文件，返回不含行尾换行符的行列表"""
        with open(path, "r") as f:
            return f.read().splitlines()

    def _write_lines(self, path: str, lines: list[str]) -> None:
        """将行列表写入文件，自动补换行"""
        with open(path, "w") as f:
            f.write("\n".join(lines))

    def add_line_num(self, lines: list[str]) -> list[str]:
        """
        在每行前添加行号。

        :param lines: 输入的行列表（不含行尾换行符）
        :return: 添加行号后的行列表
        """
        last_line_num_digit = len(str(len(lines)))
        return [f"{i:>{last_line_num_digit}}| {line}" for i, line in enumerate(lines, 1)]

    def read_file(self, path: str, add_line_num: bool = False) -> str:
        """
        读取文件内容，返回字符串。
        如果 add_line_num 为 True，则在每行前添加行号。

        :param path: 文件路径
        :param add_line_num: 是否添加行号
        :return: 文件内容
        """
        if not self.can_access(path, 1):
            return "错误：访问被拒绝"

        lines = self._read_lines(path)

        if add_line_num:
            lines = self.add_line_num(lines)

        return "\n".join(lines)

    def readlines(self, path: str, start_line: int, length: int, add_line_num: bool = False) -> str:
        """
        读取文件指定行范围的内容，返回字符串。
        如果 add_line_num 为 True，则在每行前添加行号。

        :param path: 文件路径
        :param start_line: 开始行号（1-based）
        :param length: 读取的行数
        :param add_line_num: 是否添加行号
        :return: 读取的内容
        """
        if not self.can_access(path, 1):
            return "错误：访问被拒绝"

        lines = self._read_lines(path)

        selected = lines[start_line - 1 : start_line + length - 1]

        if add_line_num:
            selected = self.add_line_num(selected)

        return "\n".join(selected)

    def write_file(self, path: str, content: str) -> str:
        """
        写入文件（覆盖）。若父目录不存在则自动创建。

        :param path: 文件路径
        :param content: 要写入的内容
        :return: 操作结果
        """
        if not self.can_access(path, 2):
            return "错误：访问被拒绝"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            f.write(content)

        return "成功"

    def write_lines(self, path: str, start_line: int, content: str) -> str:
        """
        写入文件指定行范围的内容，覆盖目标行。

        :param path: 文件路径
        :param start_line: 开始行号（1-based）
        :param content: 要写入的内容（可包含多行）
        :return: 操作结果
        """
        if not self.can_access(path, 2):
            return "错误：访问被拒绝"

        origin = self._read_lines(path)
        new_lines = content.splitlines()

        origin[start_line - 1 : start_line] = new_lines
        self._write_lines(path, origin)

        return "成功"

    def insert_lines(self, path: str, start_line: int, content: str) -> str:
        """
        在文件指定行之前插入内容。

        :param path: 文件路径
        :param start_line: 插入行号（1-based）
        :param content: 要插入的内容（可包含多行）
        :return: 操作结果
        """
        if not self.can_access(path, 2):
            return "错误：访问被拒绝"

        origin = self._read_lines(path)
        new_lines = content.splitlines()

        origin[start_line - 1 : start_line - 1] = new_lines
        self._write_lines(path, origin)

        return "成功"

    def run_syscmd(self, cmd: str, timeout: int = 60, cmdinput: str = "") -> dict[str, str] | str:
        """
        运行系统命令，返回结果。
        ⚠️ 默认使用 shell=True，请确保 cmd 来源可信，避免命令注入。

        :param cmd: 要运行的系统命令
        :param timeout: 命令执行超时时间（秒）
        :param cmdinput: 命令的输入数据
        :return: 命令执行结果（包含标准输出、标准错误、退出码）
        """
        if not self.allow_syscmd_access:
            return "系统命令访问被拒绝"

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                input=cmdinput,
                timeout=timeout,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exitcode": str(result.returncode),
            }

        except Exception as e:
            return str(e)

    def listdir(self, path: str) -> str:
        """
        列出目录下的所有文件和子目录。

        :param path: 目录路径
        :return: 目录下的所有文件和子目录
        """
        if not self.can_access(path, 1):
            return "错误：访问被拒绝"

        files = os.listdir(path)
        output = "文件类型|权限|修改时间|文件名\n|--|------|------|------\n"

        for file in files:
            p = Path(os.path.join(path, file))
            info = p.stat()

            permission = stat.filemode(info.st_mode)
            mtime_ts = info.st_mtime
            mtime = datetime.fromtimestamp(mtime_ts).strftime("%Y-%m-%d %H:%M:%S")
            dir_or_file = "目录" if p.is_dir() else "文件"

            line = f"{dir_or_file}|{permission}|{mtime}|{file}\n"
            output += line

        return output
    
    def get_request(self, url: str) -> str:
        """
        发送 GET 请求，返回响应内容。

        :param url: 请求 URL
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.get(url)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)

    def head_request(self, url: str) -> str:
        """
        发送 HEAD 请求，返回响应内容。

        :param url: 请求 URL
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.head(url)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)

    def post_request(self, url: str, data: dict[str, str]) -> str:
        """
        发送 POST 请求，返回响应内容。

        :param url: 请求 URL
        :param data: 请求数据（键值对）
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.post(url, data=data)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)

    def put_request(self, url: str, data: dict[str, str]) -> str:
        """
        发送 PUT 请求，返回响应内容。

        :param url: 请求 URL
        :param data: 请求数据（键值对）
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.put(url, data=data)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)

    def delete_request(self, url: str) -> str:
        """
        发送 DELETE 请求，返回响应内容。

        :param url: 请求 URL
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.delete(url)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)

    def options_request(self, url: str) -> str:
        """
        发送 OPTIONS 请求，返回响应内容。

        :param url: 请求 URL
        :return: 响应内容
        """
        if not self.allow_network_access or not self.allow_raw_network_data:
            return "网络数据访问被拒绝"

        try:
            response = requests.options(url)
            return response.text
        except requests.exceptions.RequestException as e:
            return str(e)
        
    def get_sandbox_dir(self) -> str:
        """
        获取沙箱目录。

        :return: 沙箱目录
        """
        return f"沙箱目录：{self.sandbox_dir}，请不要在沙箱外操作"

    def register_tools(self, tools: Tools) -> None:
        for tool in self.sandbox_tools:
            tools.add(tool)