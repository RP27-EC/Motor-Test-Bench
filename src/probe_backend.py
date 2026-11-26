from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import threading


class ProbeBackend:
    def __init__(self, executable: Path):
        self.executable = executable
        self.process = None
        self.responses = None

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.stop()
        if not self.executable.is_file():
            raise RuntimeError("缺少探针后端，请重新解压完整的电机测试台便携包。")
        self.process = subprocess.Popen(
            [str(self.executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.responses = queue.Queue()
        threading.Thread(target=self._read, args=(self.process, self.responses), daemon=True).start()

    @staticmethod
    def _read(process, responses):
        try:
            for line in process.stdout:
                responses.put(line)
        finally:
            responses.put(None)

    def stop(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait()
            process.stdin.close()
            process.stdout.close()

    def request(self, op, timeout=4, **fields):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("探针后端已退出。请刷新探针后重新连接。")
        try:
            self.process.stdin.write(json.dumps({"op": op, **fields}) + "\n")
            self.process.stdin.flush()
            response = self.responses.get(timeout=timeout)
            if response is None:
                raise EOFError
            reply = json.loads(response)
        except (OSError, EOFError, queue.Empty, ValueError) as error:
            self.stop()
            raise RuntimeError(f"探针后端在 {op} 阶段未正常应答，请刷新探针。") from error
        if not reply["ok"]:
            raise RuntimeError(reply["error"])
        return reply["data"]

    def read32(self, address):
        return self.read_memory_block32(address, 1)[0]

    def read_memory_block32(self, address, count):
        return self.request("read", address=address, count=count)

    def write32(self, address, value):
        self.write_memory_block32(address, [value])

    def write_memory_block32(self, address, words):
        self.request("write", address=address, words=words)
