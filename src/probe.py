from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import queue
import secrets
import sys
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal

from model import (
    BOARDS, COMMAND_WORDS, DEFAULT_SAMPLE_HZ, DEFAULT_SWD_KHZ, MAGIC, MAX_DISCOVERY,
    Node, Op, PROTOCOL, READ_SWD_RATES_KHZ, SAMPLE_RATES_HZ, STATUS_WORDS, SWD_RATES_KHZ, State, command,
)
from probe_backend import ProbeBackend


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
BUNDLE = ROOT / "bundle"
FLASH_BASE = 0x08000000
FLASH_END = FLASH_BASE + 1024 * 1024
HEARTBEAT_INTERVAL = 0.08


@dataclass(frozen=True)
class Manifest:
    board: int
    abi: int
    build: int
    sha256: str
    identity: int
    command: int
    heartbeat: int
    status: int
    discovery: int

    @classmethod
    def load(cls, board):
        manifest = cls(**json.loads((BUNDLE / f"{board.key}.json").read_text(encoding="utf-8")))
        if (manifest.board, manifest.abi) != (board.number, PROTOCOL):
            raise ValueError("测试固件清单的板型或接口版本不匹配")
        if not FLASH_BASE <= manifest.identity <= FLASH_END - 16:
            raise ValueError("固件标识地址超出 Flash")
        spans = sorted((address, address + size) for address, size in (
            (manifest.command, COMMAND_WORDS * 4), (manifest.heartbeat, 4),
            (manifest.status, STATUS_WORDS * 4), (manifest.discovery, MAX_DISCOVERY * 20),
        ))
        end = board.sram
        for start, stop in spans:
            if start % 4 or start < end or stop > board.sram + board.ram_size:
                raise ValueError("固件接口地址超出范围或重叠")
            end = stop
        return manifest


def image_segments(path):
    from elftools.elf.elffile import ELFFile
    from intelhex import IntelHex

    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("固件文件过大")
    if path.suffix.lower() == ".hex":
        image = IntelHex(str(path))
        segments = [(start, bytes(image.tobinarray(start=start, size=end - start)))
                    for start, end in image.segments()]
    elif path.suffix.lower() in (".elf", ".axf"):
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            if elf.header.e_machine != "EM_ARM" or not elf.little_endian:
                raise ValueError("请选择 STM32 ARM 小端固件")
            segments = [(seg["p_paddr"], seg.data()) for seg in elf.iter_segments()
                        if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]]
    else:
        raise ValueError("支持 HEX、ELF 或 AXF")
    if not segments:
        raise ValueError("固件没有可编程的内容")
    end = FLASH_BASE
    for start, data in sorted(segments):
        if start < end or start + len(data) > FLASH_END:
            raise ValueError("固件段重叠或地址超出目标 1 MB Flash")
        end = start + len(data)
    return sorted(segments)


class Signals(QObject):
    probes = pyqtSignal(list)
    link = pyqtSignal(bool, bool, str)
    notice = pyqtSignal(str, bool)
    status = pyqtSignal(object)
    discovery = pyqtSignal(list)
    reply = pyqtSignal(int, int, object)
    progress = pyqtSignal(int)


class ProbeWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.signals = Signals()
        self.requests = queue.Queue()
        self.widget_pulse = 0.0
        self.backend = ProbeBackend(BUNDLE / "motor-bench-probe.exe")
        self.attached = False
        self.probe_index = None
        self.read_swd_khz = DEFAULT_SWD_KHZ
        self.sample_interval = 1 / DEFAULT_SAMPLE_HZ
        self.board = None
        self.manifest = None
        self.compatible = False
        self.seq = 0
        self.inflight = None
        self.heartbeat = secrets.randbits(30)
        self.last_heartbeat = 0.0
        self.last_status = 0.0
        self.last_discovery = 0.0
        self.discovery_revision = None
        self.status_cache = None
        self.last_snapshot = 0.0
        self.last_tick_change = time.monotonic()

    def send(self, action, *data):
        self.requests.put((action, data))

    def pulse(self):
        self.widget_pulse = time.monotonic()

    def poll_wait(self):
        if not self.compatible:
            return None
        now = time.monotonic()
        heartbeat_wait = HEARTBEAT_INTERVAL
        if now - self.widget_pulse < 0.24:
            heartbeat_wait -= now - self.last_heartbeat
        return max(0, min(heartbeat_wait, self.last_status + self.sample_interval - now))

    def set_sample_rate(self, hz):
        if hz not in SAMPLE_RATES_HZ:
            raise ValueError("无效的上位机读取频率")
        self.sample_interval = 1 / hz

    def run(self):
        while True:
            action = None
            try:
                action, data = self.requests.get(timeout=self.poll_wait())
            except queue.Empty:
                pass
            except Exception as error:
                self.signals.notice.emit(str(error), True)
            try:
                if action == "quit":
                    try:
                        self.shutdown()
                    finally:
                        self.backend.stop()
                    return
                if action == "list":
                    self.list_probes()
                elif action == "connect":
                    self.connect(*data)
                elif action == "disconnect":
                    self.shutdown()
                elif action == "flash":
                    self.flash(*data)
                elif action == "sample_rate":
                    self.set_sample_rate(*data)
                elif action == "command":
                    self.command(*data)
                if self.compatible:
                    self.poll()
            except Exception as error:
                self.signals.notice.emit(str(error), True)
                if action == "flash" and not self.compatible:
                    if self.attached and self.backend.process is not None:
                        self.signals.link.emit(True, False, "烧录操作失败")
                    else:
                        self.disconnect()
                elif action == "connect" or action is None:
                    self.disconnect()
                elif action == "quit":
                    return
                elif action == "command" and self.compatible:
                    self.disconnect()

    def list_probes(self):
        self.backend.start()
        self.signals.probes.emit(self.backend.request("list", timeout=10))

    def connect(self, board_index, probe_index, read_swd_khz=DEFAULT_SWD_KHZ, sample_hz=DEFAULT_SAMPLE_HZ):
        if read_swd_khz not in READ_SWD_RATES_KHZ:
            raise ValueError("无效的读取 SWD 频率")
        if self.attached:
            self.shutdown()
        self.board = BOARDS[board_index]
        self.probe_index = probe_index
        self.read_swd_khz = read_swd_khz
        self.set_sample_rate(sample_hz)
        try:
            actual_speed = self.open_probe(read_swd_khz)
        except RuntimeError as error:
            raise RuntimeError(f"已找到探针，连接 {self.board.name} 失败。{error}") from error
        self.check_chip()
        self.manifest = Manifest.load(self.board)
        self.last_tick_change = time.monotonic()
        self.prepare_link()
        self.signals.notice.emit(f"读取 SWD 已连接，实际频率 {actual_speed} kHz。", False)

    def open_probe(self, speed_khz):
        if speed_khz not in SWD_RATES_KHZ:
            raise ValueError("无效的 SWD 频率")
        self.attached = False
        info = self.backend.request("open", timeout=15, index=self.probe_index, chip=self.board.target, speed=speed_khz)
        self.attached = True
        return info["speed"]

    @property
    def target(self):
        if not self.attached:
            raise RuntimeError("请先连接探针")
        return self.backend

    def check_chip(self):
        try:
            actual = self.target.read32(self.board.id_register) & 0xfff
        except RuntimeError as error:
            raise RuntimeError(f"无法读取 {self.board.name} 的芯片 ID，请核对板型和 SWD 接线。{error}") from error
        if actual != self.board.device_id:
            raise RuntimeError(f"目标芯片 ID 0x{actual:03X} 与 {self.board.name} 不匹配")

    def matches(self):
        expected = [MAGIC, PROTOCOL, self.board.number, self.manifest.build]
        return list(self.target.read_memory_block32(self.manifest.identity, 4)) == expected

    def prepare_link(self):
        self.compatible = self.matches()
        self.status_cache = None
        self.inflight = None
        self.discovery_revision = None
        self.signals.discovery.emit([])
        if self.compatible:
            deadline = time.monotonic() + 3
            snapshot = None
            while time.monotonic() < deadline:
                snapshot = self.snapshot()
                if snapshot is not None and snapshot[21] & 16:
                    break
                time.sleep(0.03)
            else:
                self.compatible = False
                raise RuntimeError("测试固件标识匹配，但板上程序没有进入运行状态")
            self.seq = int(self.target.read32(self.manifest.command))
            self.heartbeat = (int(self.target.read32(self.manifest.heartbeat)) + 1) & 0xffffffff
            self.last_heartbeat = 0
            self.last_snapshot = time.monotonic()
            self.status_cache = snapshot
            if snapshot[2] in (State.RUNNING, State.STARTING, State.SCANNING, State.STOPPING):
                self.stop_sync()
        self.signals.link.emit(True, self.compatible, "测试固件已就绪" if self.compatible else "已连接 · 待烧录测试固件")

    def disconnect(self):
        self.compatible = False
        self.inflight = None
        self.status_cache = None
        self.last_tick_change = time.monotonic()
        if self.attached:
            try:
                if self.backend.process is not None:
                    self.backend.request("close")
            except RuntimeError:
                self.backend.stop()
            finally:
                self.attached = False
        self.signals.link.emit(False, False, "未连接")

    def shutdown(self):
        try:
            if self.compatible:
                self.stop_sync()
        finally:
            self.disconnect()

    def snapshot(self):
        values = list(self.target.read_memory_block32(self.manifest.status, STATUS_WORDS))
        end = self.target.read32(self.manifest.status)
        if values[0] != end or values[0] & 1:
            return None
        return values

    def write_command(self, words):
        self.seq = (self.seq + 1) & 0xffffffff or 1
        self.target.write_memory_block32(self.manifest.command + 4, words[1:])
        self.target.write32(self.manifest.command, self.seq)
        return self.seq

    def stop_sync(self):
        seq = self.write_command(command(Op.STOP))
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            snapshot = self.snapshot()
            if snapshot is not None and snapshot[3] == seq and snapshot[2] in (State.IDLE, State.FAULT):
                return
            time.sleep(0.015)
        raise RuntimeError("固件未确认停止，取消当前操作。请检查 CAN 连接和电机状态")

    def command(self, words):
        if not self.compatible:
            raise RuntimeError("请连接已烧录匹配测试固件的板子")
        op = Op(words[1])
        if self.inflight and op != Op.STOP:
            raise RuntimeError("等待上一条命令完成")
        self.send_heartbeat(time.monotonic(), force=True)
        seq = self.write_command(words)
        timeout = max(2.0, (words[9] - words[8] + 1) * 0.03 + 2) if op == Op.SCAN else 2.5
        self.inflight = (seq, op, time.monotonic() + timeout)

    def send_heartbeat(self, now, force=False):
        if (force or now - self.last_heartbeat >= HEARTBEAT_INTERVAL) and now - self.widget_pulse < 0.24:
            self.heartbeat = (self.heartbeat + 1) & 0xffffffff
            self.target.write32(self.manifest.heartbeat, self.heartbeat)
            self.last_heartbeat = now

    def poll(self):
        now = time.monotonic()
        self.send_heartbeat(now)
        if now < self.last_status + self.sample_interval:
            return
        self.last_status = now
        snapshot = self.snapshot()
        if snapshot is None:
            if now - self.last_snapshot > 1:
                raise RuntimeError("固件状态快照持续不同步")
            return
        self.last_snapshot = now
        old_tick = None if self.status_cache is None else self.status_cache[1]
        if old_tick != snapshot[1]:
            self.last_tick_change = now
        elif now - self.last_tick_change > 1.0:
            raise RuntimeError("固件计时停滞，请重连")
        self.status_cache = snapshot
        self.signals.status.emit(snapshot)
        if self.inflight:
            seq, op, deadline = self.inflight
            if snapshot[3] == seq:
                if op == Op.SCAN:
                    self.read_discovery(snapshot)
                self.inflight = None
                self.signals.reply.emit(int(op), snapshot[4], snapshot[15:15 + snapshot[14]])
            elif now > deadline:
                self.inflight = None
                if op != Op.STOP:
                    self.write_command(command(Op.STOP))
                self.signals.reply.emit(int(op), 4, [])
        if snapshot[2] == State.SCANNING and now - self.last_discovery >= 0.20:
            if snapshot[23] != self.discovery_revision:
                self.read_discovery(snapshot)

    def read_discovery(self, snapshot):
        count = min(MAX_DISCOVERY, snapshot[13])
        words = list(self.target.read_memory_block32(self.manifest.discovery, count * 5)) if count else []
        nodes = [Node(snapshot[25], *words[i:i + 5]) for i in range(0, len(words), 5)]
        self.last_discovery = time.monotonic()
        self.discovery_revision = snapshot[23]
        self.signals.discovery.emit(nodes)

    def flash(self, external, flash_swd_khz=DEFAULT_SWD_KHZ):
        if flash_swd_khz not in SWD_RATES_KHZ:
            raise ValueError("无效的烧录 SWD 频率")
        self.check_chip()
        path = Path(external) if external else BUNDLE / f"{self.board.key}.hex"
        if not external and hashlib.sha256(path.read_bytes()).hexdigest() != self.manifest.sha256:
            raise RuntimeError("内置固件文件校验失败")
        image_segments(path)
        if self.compatible:
            self.stop_sync()
        self.compatible = False
        self.inflight = None
        self.signals.link.emit(True, False, "正在烧录")
        self.signals.progress.emit(0)
        switch_speed = flash_swd_khz != self.read_swd_khz
        try:
            if switch_speed:
                actual_speed = self.open_probe(flash_swd_khz)
                self.check_chip()
                self.signals.notice.emit(f"烧录 SWD 实际频率 {actual_speed} kHz，正在写入和校验。", False)
            self.backend.request("flash", timeout=180 * max(1, DEFAULT_SWD_KHZ / flash_swd_khz), file=str(path.resolve()))
        except RuntimeError as error:
            if switch_speed and self.backend.process is not None:
                try:
                    self.open_probe(self.read_swd_khz)
                except RuntimeError as restore_error:
                    raise RuntimeError(f"{error}。读取连接也未能恢复：{restore_error}") from error
            raise
        try:
            if switch_speed:
                self.open_probe(self.read_swd_khz)
                self.check_chip()
            self.last_tick_change = time.monotonic()
            self.prepare_link()
        except RuntimeError as error:
            self.disconnect()
            raise RuntimeError(f"烧录校验已完成，读取连接未能恢复。{error}") from error
        self.signals.progress.emit(100)
        self.signals.notice.emit("烧录与逐字节校验完成", False)
