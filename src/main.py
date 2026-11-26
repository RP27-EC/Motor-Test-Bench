from __future__ import annotations

from collections import deque
import csv
from pathlib import Path
import re
import sys

from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from model import (
    BOARDS, BRANDS, DEFAULT_SAMPLE_HZ, DEFAULT_SWD_KHZ, DM_PARAMS, LK_PARAMS, LK_PID_NAMES,
    MODELS, READ_SWD_RATES_KHZ, RESULT, SAMPLE_RATES_HZ, STATE, SWD_RATES_KHZ, Node, Op, State, bits, command, real,
)
from probe import ROOT, ProbeWorker
from trend import Trend


ZOOMS = (100, 125, 150, 175, 200)
STYLESHEET = (ROOT / "src" / "style.qss").read_text(encoding="utf-8-sig")
ICON = ROOT / "src" / "motorbench.ico"


def label(value, kind=""):
    widget = QLabel(value)
    widget.setObjectName(kind)
    return widget


def button(value, kind=""):
    widget = QPushButton(value)
    widget.setObjectName(kind)
    return widget


def box(name, layout_type=QVBoxLayout, margin=14):
    widget = QFrame()
    widget.setObjectName(name)
    layout = layout_type(widget)
    layout.setContentsMargins(*[margin] * 4)
    layout.setSpacing(9)
    return widget, layout


def pair(*widgets):
    widget, layout = box("", QHBoxLayout, 0)
    for child in widgets:
        layout.addWidget(child)
    return widget


def combo(items):
    widget = QComboBox()
    widget.addItems(items)
    return widget


def integer(lo, hi, value):
    widget = QSpinBox()
    widget.setRange(lo, hi)
    widget.setValue(value)
    return widget


def number(lo, hi, value, decimals=2):
    widget = QDoubleSpinBox()
    widget.setRange(lo, hi)
    widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


def tabs(names):
    widget, layout = box("nav", QHBoxLayout, 4)
    group = QButtonGroup(widget)
    for index, name in enumerate(names):
        tab = button(name)
        tab.setProperty("tab", True)
        tab.setCheckable(True)
        group.addButton(tab, index)
        layout.addWidget(tab)
    group.button(0).setChecked(True)
    return widget, group


def scroll_panel():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    widget, layout = box("", QVBoxLayout, 2)
    widget.setObjectName("scroll-content")
    scroll.setWidget(widget)
    return scroll, layout


def parse_id(text):
    text = text.strip()
    value = int(text, 16 if text.lower().startswith("0x") else 10)
    if not 0 <= value <= 0x7ff:
        raise ValueError("CAN ID 范围为 0x000–0x7FF")
    return value


class SliderEditor(QWidget):
    def __init__(self, lo, hi, use_float):
        super().__init__()
        self.lo, self.hi = lo, hi
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, min(1000, int(hi - lo)) if not use_float else 1000)
        self.editor = number(lo, hi, lo, 4) if use_float else integer(lo, hi, lo)
        self.editor.setMinimumWidth(97)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.editor)
        self.slider.valueChanged.connect(self.drag)
        self.editor.valueChanged.connect(self.sync)

    def drag(self, value):
        mapped = self.lo + (self.hi - self.lo) * value / self.slider.maximum()
        self.editor.setValue(round(mapped) if isinstance(self.editor, QSpinBox) else mapped)

    def sync(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round((value - self.lo) * self.slider.maximum() / (self.hi - self.lo)))
        self.slider.blockSignals(False)


class BenchWindow(QMainWindow):
    def __init__(self, worker, preferences=None):
        super().__init__()
        self.worker = worker
        self.preferences = preferences if preferences is not None else QSettings("MotorBench", "MotorBench")
        self.flash_swd_khz = self.saved_rate("swd/flashKHz", SWD_RATES_KHZ, DEFAULT_SWD_KHZ)
        self.read_swd_khz = self.saved_rate("swd/readKHz", READ_SWD_RATES_KHZ, DEFAULT_SWD_KHZ)
        self.sample_hz = self.saved_rate("swd/sampleHz", SAMPLE_RATES_HZ, DEFAULT_SAMPLE_HZ)
        self.scale = 1.0
        self.narrow = None
        self.loading_preferences = False
        self.connected = self.ready = self.flashing = self.connecting = False
        self.state = State.IDLE
        self.brand = self.model_index = 0
        self.pending = self.active = self.staged = None
        self.port_scan = None
        self.next_ports = deque()
        self.nodes = {}
        self.online = self.dm_ready = self.was_online = False
        self.fault = 0
        self.needs_reload = False
        self.selected_encoder = 0
        self.param_editors = []
        self.param_readback = None
        self.parameter = None
        self.samples = deque(maxlen=6000)
        self.last_seq = self.start_tick = None
        self.curve_paused = False
        self.setWindowTitle("电机测试台")
        self.brand_icon = QIcon(str(ICON))
        self.setWindowIcon(self.brand_icon)
        self.resize(1440, 890)
        self.setMinimumSize(720, 580)
        self.build()
        self.bind()
        saved_zoom = self.preferences.value("ui/zoom", 200, type=int)
        self.zoom.setCurrentIndex(ZOOMS.index(saved_zoom) if saved_zoom in ZOOMS else ZOOMS.index(200))
        self.set_zoom(self.zoom.currentIndex())
        self.change_board()
        self.change_brand(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(worker.pulse)
        self.timer.start(50)
        worker.pulse()

    def build(self):
        surface, shell = box("surface", QVBoxLayout, 0)
        shell.setSpacing(0)
        self.setCentralWidget(surface)
        header, top = box("header", QHBoxLayout, 17)
        self.header_icon = QLabel()
        top.addWidget(self.header_icon)
        top.addWidget(label("电机测试台", "product"))
        self.subtitle = label("CAN 调试与状态采集", "headnote")
        top.addWidget(self.subtitle)
        top.addStretch()
        self.connection = label("未连接", "connection")
        self.stop = button("停止输出", "stop")
        self.zoom = combo([f"{value}%" for value in ZOOMS])
        self.zoom.setToolTip("界面缩放")
        self.zoom.setAccessibleName("界面缩放")
        top.addWidget(self.connection)
        top.addWidget(self.zoom)
        top.addWidget(self.stop)
        shell.addWidget(header)

        body, layout = box("surface", QVBoxLayout, 15)
        workspace_scroll = QScrollArea()
        workspace_scroll.setWidgetResizable(True)
        workspace_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        workspace_scroll.setWidget(body)
        shell.addWidget(workspace_scroll, 1)
        toolbar, self.toolbar_layout = box("toolbar", QGridLayout, 10)
        toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.board = combo([b.name for b in BOARDS])
        self.probe = combo(["未检测到探针"])
        self.probe.setMinimumWidth(155)
        self.refresh = button("刷新探针")
        self.connect_button = button("连接", "primary")
        self.flash_button = button("烧录测试固件")
        self.import_button = button("导入固件…")
        self.link_fields, fields = box("", QHBoxLayout, 0)
        for widget in (label("测试板", "muted"), self.board, label("SWD", "muted")):
            fields.addWidget(widget)
        fields.addWidget(self.probe, 1)
        self.link_actions = pair(self.refresh, self.connect_button, self.flash_button, self.import_button)
        layout.addWidget(toolbar)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.brand_bar, self.brand_tabs = tabs(BRANDS)
        self.workspace_nav, self.workspace_tabs = tabs(("电机", "控制与设置", "曲线"))
        navigation = QHBoxLayout()
        navigation.addWidget(self.brand_bar)
        navigation.addStretch()
        self.bitrate = label("经典 CAN · 1 Mbps", "muted")
        navigation.addWidget(self.bitrate)
        self.frequency_button = button("频率设置…")
        navigation.addWidget(self.frequency_button)
        layout.addLayout(navigation)
        layout.addWidget(self.workspace_nav)
        columns = QHBoxLayout()
        columns.setSpacing(10)
        self.panels = (self.discovery_panel(), self.control_panel(), self.curve_panel())
        for panel in self.panels:
            columns.addWidget(panel, 1)
        layout.addLayout(columns, 1)
        self.notice = label("连接 J-Link 或 CMSIS-DAP 开始。", "muted")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def set_zoom(self, index):
        if index < 0:
            return
        percent = ZOOMS[index]
        self.preferences.setValue("ui/zoom", percent)
        self.scale = percent / 100
        style = re.sub(r"(\d+(?:\.\d+)?)px", lambda m: f"{round(float(m[1]) * self.scale)}px", STYLESHEET)
        QApplication.instance().setStyleSheet(style)
        icon_size = round(34 * self.scale)
        self.header_icon.setPixmap(self.brand_icon.pixmap(icon_size, icon_size))
        for chart in self.charts:
            chart.set_zoom(self.scale)
        self.table.verticalHeader().setDefaultSectionSize(round(29 * self.scale))
        self.reflow(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "panels"):
            self.reflow()

    def reflow(self, force=False):
        narrow = self.width() < round(1100 * self.scale)
        self.subtitle.setVisible(self.width() >= round(940 * self.scale))
        self.bitrate.setVisible(self.width() >= round(750 * self.scale))
        if self.narrow == narrow and not force:
            return
        self.narrow = narrow
        self.brand_bar.setFixedWidth(round((260 if narrow else 312) * self.scale))
        self.probe.setMinimumWidth(round(115 * self.scale))
        for widget in (self.link_fields, self.link_actions):
            self.toolbar_layout.removeWidget(widget)
        self.toolbar_layout.addWidget(self.link_fields, 0, 0)
        self.toolbar_layout.addWidget(self.link_actions, 1 if narrow else 0, 0 if narrow else 1)
        self.workspace_nav.setVisible(narrow)
        for panel, width in zip(self.panels[:2], (312, 368)):
            if narrow:
                panel.setMinimumWidth(0)
                panel.setMaximumWidth(16777215)
            else:
                panel.setFixedWidth(round(width * self.scale))
        self.show_workspace()

    def show_workspace(self, *_):
        for index, panel in enumerate(self.panels):
            panel.setVisible(not self.narrow or index == self.workspace_tabs.checkedId())

    def discovery_panel(self):
        card, layout = box("card")
        layout.addWidget(label("电机发现", "section"))
        self.model = combo([])
        self.port = combo([])
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("电机型号", self.model)
        form.addRow("扫描接口", self.port)
        layout.addLayout(form)
        self.scan_lo = integer(1, 2046, 1)
        self.scan_hi = integer(1, 2046, 32)
        self.scan_range = pair(self.scan_lo, label("至", "muted"), self.scan_hi)
        layout.addWidget(self.scan_range)
        self.scan = button("扫描电机", "primary")
        layout.addWidget(self.scan)
        self.scan_status = label("请选择型号和 CAN 口", "muted")
        self.scan_status.setWordWrap(True)
        layout.addWidget(self.scan_status)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("接口", "编号", "TX", "RX", "槽"))
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)
        self.encoder = combo(["编码器 16 位", "编码器 14 位", "编码器 15 位"])
        layout.addWidget(self.encoder)
        self.select_button = button("选中并读取")
        self.manual = button("手填 ID…")
        layout.addWidget(pair(self.select_button, self.manual))
        return card

    def control_panel(self):
        card, layout = box("card")
        self.device = label("未选中电机", "section")
        self.route = label("从左侧列表选中一台电机", "muted")
        self.route.setWordWrap(True)
        self.state_label = label("待机", "motorState")
        self.state_label.setProperty("state", "idle")
        layout.addWidget(self.device)
        layout.addWidget(self.route)
        layout.addWidget(self.state_label, 0, Qt.AlignLeft)
        subnav, self.detail_tabs = tabs(("测试控制", "保护与零点", "电机参数"))
        layout.addWidget(subnav)
        self.detail = QStackedWidget()
        self.detail.addWidget(self.motion_panel())
        self.detail.addWidget(self.settings_panel())
        self.detail.addWidget(self.parameter_panel())
        layout.addWidget(self.detail, 1)
        return card

    def motion_panel(self):
        scroll, layout = scroll_panel()
        self.strategy = combo(["软件 PID", "驱动器内置"])
        self.strategy_label = label("控制方式")
        self.mode = combo(["速度", "相对位置"])
        self.target = number(-100, 100, 0)
        self.limit = number(0.01, 16384, 250)
        self.speed_limit = number(0.1, 3000, 100)
        self.ratio = number(0.01, 1000, 1, 3)
        self.reverse = QCheckBox("反向")
        self.kp = number(0, 100, 1, 4)
        self.ki = number(0, 100, 1, 4)
        self.kd = number(0, 100, 0, 4)
        self.position_kp = number(0, 30, 0.5, 4)
        self.position_ki = number(0, 100, 0, 4)
        self.position_kd = number(0, 100, 0, 4)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.target_label = label("目标转速 [rpm]")
        self.limit_label = label("输出上限 [码]")
        for title, widget in ((self.strategy_label, self.strategy), ("目标类型", self.mode), (self.target_label, self.target),
                              ("速度上限 [rpm]", self.speed_limit), (self.limit_label, self.limit),
                              ("减速比", pair(self.ratio, self.reverse))):
            form.addRow(title, widget)
        layout.addLayout(form)
        self.tuning = button("展开 PID 参数")
        self.tuning.setCheckable(True)
        layout.addWidget(self.tuning)
        self.tune_panel, tuning = box("tuneCard", QGridLayout, 6)
        for column, name in enumerate(("Kp", "Ki", "Kd"), 1):
            tuning.addWidget(label(name, "muted"), 0, column, Qt.AlignCenter)
        for row, name, gains in (
            (1, "速度环", (self.kp, self.ki, self.kd)),
            (2, "位置环", (self.position_kp, self.position_ki, self.position_kd)),
        ):
            tuning.addWidget(label(name), row, 0)
            for column, editor in enumerate(gains, 1):
                editor.setButtonSymbols(QAbstractSpinBox.NoButtons)
                editor.setAccessibleName(f"{name} {('Kp', 'Ki', 'Kd')[column - 1]}")
                tuning.addWidget(editor, row, column)
        self.tune_panel.hide()
        layout.addWidget(self.tune_panel)
        self.native_note = label("", "inlineNote")
        self.native_note.setWordWrap(True)
        self.native_note.hide()
        layout.addWidget(self.native_note)
        self.enable = button("使能并运行", "primary")
        self.update_target = button("发送新目标")
        self.zero = button("当前位置置零")
        layout.addWidget(self.enable)
        layout.addWidget(pair(self.update_target, self.zero))
        self.feedback = label("等待实时反馈", "muted")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        layout.addStretch()
        return scroll

    def parameter_panel(self):
        scroll, layout = scroll_panel()
        self.param_tip = label("", "muted")
        self.param_tip.setWordWrap(True)
        self.param_combo = combo([])
        self.param_read = button("读取当前值")
        self.param_value = label("当前值 —", "metric")
        self.param_value.setWordWrap(True)
        self.edit_area = QWidget()
        self.editor_layout = QFormLayout(self.edit_area)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.param_write = button("写入并读回", "primary")
        self.param_save = button("保存到电机…")
        for widget in (self.param_tip, self.param_combo, self.param_read, self.param_value, self.edit_area,
                       self.param_write, self.param_save):
            layout.addWidget(widget)
        layout.addStretch()
        return scroll

    def settings_panel(self):
        scroll, layout = scroll_panel()
        layout.addWidget(label("测试保护", "section"))
        self.temperature = integer(20, 150, 80)
        self.temperature_label = label("过温停机 [°C]")
        self.feedback_timeout = integer(25, 250, 100)
        self.angle_enabled = QCheckBox("使用角度软限位")
        self.angle_min = number(-36000, 36000, -180, 1)
        self.angle_max = number(-36000, 36000, 180, 1)
        form = QFormLayout()
        form.addRow(self.temperature_label, self.temperature)
        form.addRow("反馈超时 [ms]", self.feedback_timeout)
        form.addRow(self.angle_enabled)
        form.addRow("最小角度 [°]", self.angle_min)
        form.addRow("最大角度 [°]", self.angle_max)
        layout.addLayout(form)
        self.protection_note = label("修改后，下次使能时由测试板执行。", "muted")
        self.protection_note.setWordWrap(True)
        layout.addWidget(self.protection_note)

        layout.addWidget(label("位置零点", "section"))
        self.position_reference = number(-36000, 36000, 0, 2)
        self.set_reference = button("设定当前位置")
        reference = QFormLayout()
        reference.addRow("当前位置设为 [°]", self.position_reference)
        layout.addLayout(reference)
        layout.addWidget(self.set_reference)
        self.native_zero = button("写入驱动器零点…")
        layout.addWidget(self.native_zero)
        self.zero_note = label("软件位置以当前轴方向、减速比为准。", "muted")
        self.zero_note.setWordWrap(True)
        layout.addWidget(self.zero_note)
        layout.addStretch()
        return scroll

    def curve_panel(self):
        widget, layout = box("", QVBoxLayout, 0)
        bar = QHBoxLayout()
        bar.addWidget(label("实时曲线", "section"))
        bar.addStretch()
        self.window_range = combo(["最近 10 秒", "最近 30 秒", "最近 60 秒"])
        self.pause = button("暂停绘图")
        self.pause.setCheckable(True)
        self.export = button("导出 CSV")
        for control in (self.window_range, self.pause, self.export):
            bar.addWidget(control)
        layout.addLayout(bar)
        self.speed_chart = Trend("转速", "rpm", "#1472cb", True)
        self.position_chart = Trend("相对位置", "°", "#6850b5", True)
        self.effort_chart = Trend("反馈电流原始码", "码", "#087b72")
        self.charts = (self.speed_chart, self.position_chart, self.effort_chart)
        for chart in self.charts:
            layout.addWidget(chart, 1)
        layout.addWidget(label("实线 · 反馈       虚线 · 目标", "muted"))
        return widget

    def bind(self):
        sig = self.worker.signals
        sig.probes.connect(self.probes)
        sig.link.connect(self.link)
        sig.notice.connect(self.notify)
        sig.discovery.connect(self.discovered)
        sig.status.connect(self.status)
        sig.reply.connect(self.reply)
        sig.progress.connect(self.update_progress)
        self.refresh.clicked.connect(lambda: self.worker.send("list"))
        self.board.currentIndexChanged.connect(self.change_board)
        self.connect_button.clicked.connect(self.connect_probe)
        self.flash_button.clicked.connect(lambda: self.flash(None))
        self.import_button.clicked.connect(self.import_firmware)
        self.frequency_button.clicked.connect(self.frequency_settings)
        self.stop.clicked.connect(self.stop_output)
        self.zoom.currentIndexChanged.connect(self.set_zoom)
        self.workspace_tabs.idClicked.connect(self.show_workspace)
        self.brand_tabs.idClicked.connect(self.change_brand)
        self.detail_tabs.idClicked.connect(self.detail.setCurrentIndex)
        self.model.currentIndexChanged.connect(self.change_model)
        self.table.itemSelectionChanged.connect(self.refresh_enabled)
        self.scan.clicked.connect(self.start_scan)
        self.select_button.clicked.connect(self.select_row)
        self.manual.clicked.connect(self.manual_route)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.strategy.currentIndexChanged.connect(self.change_strategy)
        self.speed_limit.valueChanged.connect(self.change_mode)
        self.tuning.toggled.connect(self.show_tuning)
        self.enable.clicked.connect(self.run_motor)
        self.update_target.clicked.connect(lambda: self.issue(Op.TARGET, (0, bits(self.target.value()))))
        self.zero.clicked.connect(lambda: self.set_position_reference(0))
        self.set_reference.clicked.connect(lambda: self.set_position_reference(self.position_reference.value()))
        self.native_zero.clicked.connect(self.write_native_zero)
        for control in (self.temperature, self.feedback_timeout, self.angle_min, self.angle_max):
            control.valueChanged.connect(self.save_protection)
        self.angle_enabled.toggled.connect(self.save_protection)
        self.param_combo.currentIndexChanged.connect(self.change_param)
        self.param_read.clicked.connect(lambda: self.issue(Op.READ, (self.parameter.addr,)))
        self.param_write.clicked.connect(self.write_param)
        self.param_save.clicked.connect(self.save_param)
        self.window_range.currentIndexChanged.connect(self.set_chart_range)
        self.pause.toggled.connect(self.toggle_pause)
        self.export.clicked.connect(self.export_csv)

    def change_board(self, *_):
        board = BOARDS[self.board.currentIndex()]
        self.port.clear()
        for i in range(1, board.ports + 1):
            self.port.addItem(f"CAN{i}", i)
        self.port.addItem("全部 CAN 口", 0)
        self.reset_view()

    def change_brand(self, brand):
        self.brand = brand
        self.strategy.setCurrentIndex(0)
        self.strategy.setVisible(brand != 0)
        self.strategy_label.setVisible(brand != 0)
        self.change_strategy()
        self.table.setHorizontalHeaderItem(2, QTableWidgetItem("CAN ID" if brand == 1 else "TX"))
        self.table.setColumnHidden(4, brand != 0)
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(MODELS[brand])
        self.model.blockSignals(False)
        self.param_combo.blockSignals(True)
        self.param_combo.clear()
        self.param_combo.addItems(p.name for p in self.parameters())
        self.param_combo.blockSignals(False)
        self.scan_range.setVisible(brand != 0)
        self.encoder.setVisible(brand == 2)
        for widget in (self.param_combo, self.param_read, self.param_value, self.param_write, self.param_save):
            widget.setVisible(brand != 0)
        self.param_tip.setText((
            "软件 PID 和输出限幅在「测试控制」编辑，写入测试板。",
            "读取后可编辑，写入自动读回。测试时会按所选方式确认达妙驱动模式。",
            "读取并编辑电机内部 PID 或加速度。PID 支持掉电保存。",
        )[brand])
        self.change_model(0)
        if self.narrow:
            self.workspace_tabs.button(0).setChecked(True)
            self.show_workspace()

    def change_model(self, index):
        if index < 0:
            return
        self.model_index = index
        self.limit.setMaximum((16384, 10000, 30000)[index] if self.brand == 0 else (20 if self.brand == 1 else 2048))
        self.limit.setValue((250, 0.5, 100)[self.brand])
        self.kp.setValue(0.025 if self.brand == 1 else 1)
        self.ki.setValue(0.02 if self.brand == 1 else 1)
        self.kd.setValue(0)
        self.position_kp.setValue(0.5)
        self.position_ki.setValue(0)
        self.position_kd.setValue(0)
        self.limit_label.setText("转矩上限 [N·m]" if self.brand == 1 else "输出上限 [码]")
        self.effort_chart.title = "反馈转矩" if self.brand == 1 else "反馈电流原始码"
        self.effort_chart.unit = "N·m" if self.brand == 1 else "码"
        self.scan_lo.setMaximum(2046 if self.brand == 1 else 32)
        self.scan_hi.setMaximum(2046 if self.brand == 1 else 32)
        self.scan_hi.setValue(32)
        self.load_protection()
        self.reset_view()

    def protection_key(self):
        return f"profiles/{self.brand}/{self.model_index}"

    def load_protection(self):
        self.loading_preferences = True
        key = self.protection_key()
        self.temperature.setValue(self.preferences.value(f"{key}/temperature", 80, type=int))
        self.feedback_timeout.setValue(self.preferences.value(f"{key}/feedbackTimeout", 100, type=int))
        self.angle_min.setValue(self.preferences.value(f"{key}/angleMin", -180.0, type=float))
        self.angle_max.setValue(self.preferences.value(f"{key}/angleMax", 180.0, type=float))
        self.angle_enabled.setChecked(self.preferences.value(f"{key}/angleEnabled", False, type=bool))
        self.loading_preferences = False
        has_temperature = self.brand != 0 or self.model_index != 1
        self.temperature.setVisible(has_temperature)
        self.temperature_label.setVisible(has_temperature)
        self.native_zero.setVisible(self.brand != 0)
        self.protection_note.setText(
            "修改后，下次使能时由测试板执行。" if has_temperature else
            "C610 标准 CAN 反馈无温度字段。反馈超时和角度软限位可用。"
        )
        self.zero_note.setText((
            "软件位置以当前轴方向、减速比为准。",
            "驱动器零点按达妙协议设置，软件会检查位置反馈。",
            "领控驱动器零点写入 ROM，电机重上电后生效。",
        )[self.brand])

    def save_protection(self, *_):
        if self.loading_preferences:
            return
        key = self.protection_key()
        for name, value in (
            ("temperature", self.temperature.value()), ("feedbackTimeout", self.feedback_timeout.value()),
            ("angleMin", self.angle_min.value()), ("angleMax", self.angle_max.value()),
            ("angleEnabled", self.angle_enabled.isChecked()),
        ):
            self.preferences.setValue(f"{key}/{name}", value)
        self.refresh_enabled()

    def reset_view(self):
        self.nodes.clear()
        self.next_ports.clear()
        self.port_scan = None
        self.table.setRowCount(0)
        self.scan_status.setText("请选择型号和 CAN 口")
        self.clear_selection()
        self.refresh_enabled()

    def clear_selection(self):
        self.active = self.staged = None
        self.online = self.dm_ready = False
        self.needs_reload = False
        self.device.setText("未选中电机")
        self.route.setText("从左侧列表选中一台电机")
        self.feedback.setText("等待实时反馈")
        self.displayed_tx = None
        self.clear_charts()
        self.change_param(self.param_combo.currentIndex())

    def clear_charts(self):
        self.samples.clear()
        self.start_tick = self.last_seq = None
        self.was_online = False
        for chart in self.charts:
            chart.clear()

    def refresh_enabled(self):
        ready = self.ready and not self.flashing
        moving = self.state in (State.RUNNING, State.STARTING, State.STOPPING)
        free = ready and not moving and self.pending is None
        detached = not self.connected and not self.connecting
        for widget in (self.board, self.probe, self.refresh):
            widget.setEnabled(detached)
        self.connect_button.setEnabled(not self.flashing and not self.connecting and
                                       (self.connected or self.probe.currentData() is not None))
        for widget in (self.flash_button, self.import_button):
            widget.setEnabled(self.connected and not moving and self.pending is None and not self.flashing)
        self.frequency_button.setEnabled(not self.flashing and not self.connecting)
        self.stop.setEnabled(ready)
        for widget in (*self.brand_tabs.buttons(), self.model, self.port, self.scan_lo, self.scan_hi, self.encoder):
            widget.setEnabled(not moving and self.pending is None and not self.flashing)
        self.scan.setEnabled(free)
        node = self.selected_row()
        self.select_button.setEnabled(free and node is not None and not node.conflict)
        self.manual.setEnabled(free)
        for widget in (self.mode, self.strategy, self.limit, self.speed_limit, self.ratio, self.reverse,
                       self.kp, self.ki, self.kd, self.position_kp, self.position_ki, self.position_kd):
            widget.setEnabled(not moving and self.pending is None)
        selected = free and self.active is not None and self.online
        self.enable.setEnabled(selected and not self.fault and not self.needs_reload and (self.brand != 1 or self.dm_ready))
        self.zero.setEnabled(selected)
        self.set_reference.setEnabled(selected)
        self.native_zero.setEnabled(selected and not self.needs_reload and (self.brand != 1 or self.dm_ready))
        for widget in (self.temperature, self.feedback_timeout, self.angle_enabled):
            widget.setEnabled(not moving and self.pending is None)
        for widget in (self.angle_min, self.angle_max):
            widget.setEnabled(self.angle_enabled.isChecked() and not moving and self.pending is None)
        self.update_target.setEnabled(ready and self.state == State.RUNNING and self.pending is None)
        can_param = selected and self.parameter is not None
        current = can_param and self.param_readback is not None
        lk_offset = self.brand == 2 and self.parameter is not None and self.parameter.addr == 0x90
        can_write_offset = not lk_offset or (self.selected_encoder == 16384 and not self.needs_reload)
        self.param_combo.setEnabled(not moving and self.pending is None)
        self.param_read.setEnabled(can_param)
        self.edit_area.setEnabled(current and can_write_offset)
        self.param_write.setEnabled(current and self.parameter.writable and can_write_offset)
        self.param_write.setToolTip("领控零偏写入需要已选中 14 位编码器配置。" if lk_offset else "")
        self.param_save.setEnabled(can_param and (self.brand == 1 or (self.parameter.addr == 0x30 and current)))
        self.export.setEnabled(bool(self.samples))

    def notify(self, message, error=False):
        self.notice.setText(message)
        self.notice.setObjectName("alert" if error else "muted")
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        if error:
            self.connecting = self.flashing = False
            self.progress.hide()
        self.refresh_enabled()

    def probes(self, devices):
        self.probe.clear()
        for description, uid in devices:
            self.probe.addItem(description, uid)
        if not devices:
            self.probe.addItem("未检测到探针")
        self.notify(f"找到 {len(devices)} 个 SWD 探针。" if devices else "未检测到 J-Link 或 CMSIS-DAP。")

    def connect_probe(self):
        if self.connected:
            self.worker.send("disconnect")
        elif self.probe.currentData() is not None:
            self.connecting = True
            self.connection.setText("正在连接")
            self.refresh_enabled()
            self.worker.send("connect", self.board.currentIndex(), self.probe.currentData(), self.read_swd_khz, self.sample_hz)

    def saved_rate(self, key, options, default):
        value = self.preferences.value(key, default, type=int)
        return value if value in options else default

    def frequency_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("频率设置")
        layout = QFormLayout(dialog)
        fields = (
            ("烧录 SWD 时钟", "swd/flashKHz", SWD_RATES_KHZ, self.flash_swd_khz, "kHz"),
            ("读取 SWD 时钟", "swd/readKHz", READ_SWD_RATES_KHZ, self.read_swd_khz, "kHz"),
            ("上位机读取频率", "swd/sampleHz", SAMPLE_RATES_HZ, self.sample_hz, "Hz"),
        )
        controls = []
        for title, _, rates, current, unit in fields:
            control = QComboBox()
            for rate in rates:
                control.addItem(f"{rate} {unit}", rate)
            control.setCurrentIndex(control.findData(current))
            controls.append(control)
            layout.addRow(title, control)
        note = label("读取 SWD 时钟在下次连接时生效。\n实际采样率取决于探针和电机反馈。", "muted")
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            self.flash_swd_khz, self.read_swd_khz, self.sample_hz = (control.currentData() for control in controls)
            for (_, key, _, _, _), control in zip(fields, controls):
                self.preferences.setValue(key, control.currentData())
            self.worker.send("sample_rate", self.sample_hz)

    def link(self, connected, ready, message):
        self.connected, self.ready, self.connecting = connected, ready, False
        self.connection.setText(message)
        self.connect_button.setText("断开" if connected else "连接")
        if not ready:
            self.pending = None
            self.state = State.IDLE
            self.update_state_badge("待机")
            self.reset_view()
        self.refresh_enabled()

    def update_progress(self, value):
        self.progress.setRange(0, 0 if value == 0 else 100)
        self.progress.setValue(value)
        if value == 100:
            self.flashing = False
            self.refresh_enabled()
            QTimer.singleShot(650, self.progress.hide)

    def import_firmware(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 STM32 固件", "", "STM32 固件 (*.hex *.elf *.axf)")
        if path:
            self.flash(path)

    def flash(self, path):
        image = Path(path).name if path else "内置测试固件"
        prompt = f"以 {self.flash_swd_khz} kHz SWD 将 {image} 写入 {self.board.currentText()}，覆盖对应 Flash 扇区。继续？"
        if QMessageBox.question(self, "烧录固件", prompt, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.flashing = True
        self.progress.setValue(0)
        self.progress.show()
        self.refresh_enabled()
        self.worker.send("flash", path, self.flash_swd_khz)

    def issue(self, op, args=(), node=None, port=1, limits=(), control=()):
        self.pending = op
        encoder = (65536, 16384, 32768)[self.encoder.currentIndex()]
        self.worker.send("command", command(op, port, self.brand, self.model_index, node, args, encoder, limits, control))
        self.refresh_enabled()

    def start_scan(self):
        if self.scan_lo.value() > self.scan_hi.value():
            self.notify("起始编号需小于或等于结束编号。", True)
            return
        self.reset_view()
        selected = self.port.currentData()
        self.next_ports.extend([selected] if selected else range(1, BOARDS[self.board.currentIndex()].ports + 1))
        self.scan_next()

    def scan_next(self):
        if not self.next_ports:
            self.port_scan = None
            self.scan_status.setText(f"扫描结束，发现 {len(self.nodes)} 台")
            return
        self.port_scan = self.next_ports.popleft()
        self.scan_status.setText(f"正在扫描 CAN{self.port_scan}…")
        self.issue(Op.SCAN, (self.scan_lo.value(), self.scan_hi.value()), port=self.port_scan)

    def discovered(self, nodes):
        if self.port_scan is None:
            return
        for node in nodes:
            self.nodes[(node.port, node.id, node.rx)] = node
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.nodes))
        for row, node in enumerate(sorted(self.nodes.values(), key=lambda n: (n.port, n.id, n.rx))):
            values = (f"CAN{node.port}", str(node.id), f"{node.tx:03X}", f"{node.rx:03X}",
                      str(node.slot + 1) if self.brand == 0 else "—")
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setData(Qt.UserRole, node)
                if node.conflict:
                    item.setToolTip("ID 冲突")
                    item.setForeground(Qt.red)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self.refresh_enabled()

    def selected_row(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def select_row(self):
        node = self.selected_row()
        if node and not node.conflict:
            self.select_node(node)

    def select_node(self, node):
        self.staged = node
        self.issue(Op.SELECT, node=node)

    def manual_route(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("手动指定 CAN 路由")
        layout = QFormLayout(dialog)
        port = combo([f"CAN{i + 1}" for i in range(BOARDS[self.board.currentIndex()].ports)])
        port.setCurrentIndex((self.port.currentData() or 1) - 1)
        device = QLineEdit("1")
        rx_field = QLineEdit("0x11" if self.brand == 1 else "0x141")
        tx_field = QLineEdit("0x141")
        layout.addRow("接口", port)
        layout.addRow("电机编号", device)
        if self.brand != 0:
            layout.addRow("反馈 RX", rx_field)
        if self.brand == 2:
            layout.addRow("控制 TX", tx_field)
        layout.addRow(label("ID 支持十进制和 0x 十六进制", "muted"))
        actions = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addRow(actions)
        if not dialog.exec():
            return
        try:
            id_number = parse_id(device.text())
            if id_number < 1:
                raise ValueError("电机编号从 1 开始")
            if self.brand == 0:
                gm = self.model_index == 2
                if id_number > (7 if gm else 8):
                    raise ValueError("电机编号超出该 RM 型号范围")
                rx = (0x204 if gm else 0x200) + id_number
                tx = ((0x1ff, 0x2ff) if gm else (0x200, 0x1ff))[id_number > 4]
                flags = (id_number - 1) % 4 + 1
            else:
                tx = id_number if self.brand == 1 else parse_id(tx_field.text())
                rx, flags = parse_id(rx_field.text()), 1
            self.select_node(Node(port.currentIndex() + 1, id_number, rx, tx, flags))
        except ValueError as error:
            self.notify(str(error), True)

    def stop_output(self):
        self.next_ports.clear()
        self.port_scan = None
        self.issue(Op.STOP)

    def change_mode(self, *_):
        speed_mode = self.mode.currentIndex() == 0
        self.target_label.setText("目标转速 [rpm]" if speed_mode else "相对位置 [°]")
        limit = self.speed_limit.value() if speed_mode else 36000
        self.target.setRange(-limit, limit)

    def change_strategy(self, *_):
        native = self.strategy.currentIndex() == 1
        for widget in (self.limit_label, self.limit, self.tuning):
            widget.setVisible(not native)
        self.tune_panel.setVisible(not native and self.tuning.isChecked())
        self.native_note.setText("速度和位置由驱动器闭环，输出限值沿用驱动器设置。")
        self.native_note.setVisible(native)

    def show_tuning(self, checked):
        self.tune_panel.setVisible(checked and self.strategy.currentIndex() == 0)
        self.tuning.setText("收起 PID 参数" if checked else "展开 PID 参数")

    def run_motor(self):
        angle_enabled = self.angle_enabled.isChecked()
        low, high = self.angle_min.value(), self.angle_max.value()
        if angle_enabled and low >= high:
            self.notify("最小角度必须小于最大角度。", True)
            return
        self.issue(Op.START, (
            self.mode.currentIndex() + 1, bits(self.target.value()), bits(self.limit.value()), bits(self.speed_limit.value()),
            bits(self.kp.value()), bits(self.ki.value()), bits(self.position_kp.value()), bits(self.ratio.value()),
            int(self.reverse.isChecked()),
        ), limits=(bits(self.temperature.value()), self.feedback_timeout.value(), bits(low), bits(high), int(angle_enabled)),
            control=(bits(self.kd.value()), bits(self.position_ki.value()), bits(self.position_kd.value()), self.strategy.currentIndex()))

    def set_position_reference(self, position):
        self.issue(Op.ZERO, (bits(position), bits(self.ratio.value()), int(self.reverse.isChecked())))

    def write_native_zero(self):
        message = "将当前位置写为驱动器零点。请确认电机已失能、停稳并位于机械零位。"
        if self.brand == 2:
            message += "\n写入领控 ROM 后，给电机重上电并重新选中。"
        if QMessageBox.question(self, "写入驱动器零点", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.issue(Op.NATIVE_ZERO)

    def parameters(self):
        return DM_PARAMS if self.brand == 1 else LK_PARAMS if self.brand == 2 else ()

    def change_param(self, index):
        self.param_readback = None
        self.param_value.setText("当前值 —")
        items = self.parameters()
        self.parameter = items[index] if 0 <= index < len(items) else None
        self.param_editors.clear()
        while self.editor_layout.rowCount():
            self.editor_layout.removeRow(0)
        p = self.parameter
        if p and p.writable:
            if p.kind == "pid":
                for name in LK_PID_NAMES:
                    editor = SliderEditor(0, 255, False)
                    self.param_editors.append(editor)
                    self.editor_layout.addRow(name, editor)
            else:
                editor = combo(["MIT", "位置／速度", "速度"]) if p.kind == "mode" else SliderEditor(p.lo, p.hi, p.kind == "float")
                self.param_editors.append(editor)
                self.editor_layout.addRow("新值", editor)
        self.refresh_enabled()

    def write_param(self):
        p = self.parameter
        if self.param_readback is None or not p or not p.writable:
            return
        if self.brand == 2 and p.addr == 0x90:
            if self.selected_encoder != 16384 or self.needs_reload:
                return
            message = "将新的编码器零偏写入领控驱动器 ROM。请确认电机已失能并停稳。"
            if QMessageBox.question(self, "写入编码器零偏", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        if p.kind == "mode":
            values = [self.param_editors[0].currentIndex() + 1]
        else:
            values = [bits(e.editor.value()) if p.kind == "float" else e.editor.value() for e in self.param_editors]
        self.issue(Op.WRITE, (p.addr, *values))

    def save_param(self):
        if self.brand == 1:
            message = "保存达妙电机当前参数，包含此前写入的其他参数。"
            args = (0,)
        else:
            message = "将刚读回的领控 PID 值写入电机 ROM。"
            args = (0x30, *self.param_readback)
        if QMessageBox.question(self, "掉电保存", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.issue(Op.SAVE, args)

    def render_param(self, values):
        p = self.parameter
        if p is None or not values:
            return
        if p.kind == "pid":
            if len(values) != len(self.param_editors):
                return
            message = " / ".join(str(value) for value in values)
            for editor, value in zip(self.param_editors, values):
                editor.editor.setValue(value)
        elif p.kind == "mode":
            index = values[0] - 1
            self.param_editors[0].setCurrentIndex(index if 0 <= index <= 2 else -1)
            message = self.param_editors[0].currentText() or f"模式 {values[0]}"
        else:
            value = real(values[0]) if p.kind == "float" else values[0]
            message = f"{value:.5g}" if p.kind == "float" else (f"0x{value:03X}" if p.kind == "hex" else str(value))
            if self.param_editors:
                from math import isfinite
                if not isfinite(value):
                    self.param_readback = None
                    self.param_value.setText("当前值无效")
                    return
                self.param_editors[0].editor.setValue(value)
        self.param_value.setText(f"当前值 {message}")
        self.param_readback = tuple(values)

    def reply(self, op, result, values):
        if self.pending != op:
            return
        self.pending = None
        if result:
            if op == Op.SCAN:
                port = self.port_scan
                self.scan_next()
                self.notify(f"CAN{port} · {RESULT[result]}", True)
                return
            if op in (Op.WRITE, Op.READ):
                self.param_readback = None
                if result == 5:
                    self.render_param(values)
            if op == Op.SELECT:
                self.staged = None
            self.notify(RESULT[result] if result < len(RESULT) else f"固件错误 {result}", True)
            return
        if op == Op.SCAN:
            self.scan_next()
        elif op == Op.SELECT:
            self.active, self.staged = self.staged, None
            self.selected_encoder = (65536, 16384, 32768)[self.encoder.currentIndex()]
            self.clear_charts()
            node = self.active
            self.device.setText(f"{self.model.currentText()}  #{node.id}")
            self.show_route(node.tx)
            self.change_param(self.param_combo.currentIndex())
            if self.narrow:
                self.workspace_tabs.button(1).setChecked(True)
                self.show_workspace()
        elif op in (Op.READ, Op.WRITE):
            self.render_param(values)
        elif op in (Op.ZERO, Op.NATIVE_ZERO):
            self.clear_charts()
        messages = {
            Op.STOP: "输出已停止。", Op.SELECT: "路由已选定，等待反馈。", Op.START: "已进入测试运行。",
            Op.TARGET: "目标已更新。", Op.ZERO: "软件位置基准已更新。", Op.READ: "已读取电机参数。",
            Op.WRITE: "已写入并读回校验。", Op.SAVE: "电机已应答保存指令。",
            Op.NATIVE_ZERO: (f"驱动器已应答，零偏 {values[0]}。请重上电并重新选中电机。" if self.brand == 2 and values
                             else "已读取达妙驱动器置零后的反馈。"),
        }
        if op in messages:
            self.notify(messages[op])
        self.refresh_enabled()

    def status(self, data):
        self.state = State(data[2])
        fault_text = f"已停止 · {RESULT[data[4]]}" if self.state == State.FAULT and 0 < data[4] < len(RESULT) else STATE[self.state]
        self.update_state_badge(fault_text)
        self.online = bool(data[21] & 128)
        self.needs_reload = bool(data[21] & 64)
        self.dm_ready = data[21] & 6 == 6
        self.fault = data[22]
        if self.state == State.SCANNING and data[12] != 0xffffffff and self.brand != 0:
            self.scan_status.setText(f"CAN{data[25]} · 查询编号 {data[12]} · 已发现 {len(self.nodes)} 台")
        if self.active:
            if self.pending != Op.SELECT and data[21] & 8 and data[26] != self.displayed_tx:
                self.show_route(data[26])
            detail = f"反馈 {data[6]} ms 前" if self.online else "等待电机反馈"
            if self.online:
                detail += f"  ·  温度 {real(data[10]):.0f} °C" if data[21] & 32 else "  ·  温度不可读"
            if self.fault:
                detail += f"  ·  故障 0x{self.fault:X}"
            if self.brand == 1 and not self.dm_ready:
                detail += "\n正在读取驱动器量程和模式。"
            if data[21] & 1:
                detail = "CAN Bus-Off · 请检查总线"
            if self.state == State.STOPPING and data[4] == 4:
                detail = "停止指令回包超时，仍在尝试停机。"
            if self.needs_reload:
                detail += "\n已发出零点写入，请确认结果，重上电后重新选中。"
            self.feedback.setText(detail)
            self.capture(data)
        self.refresh_enabled()

    def show_route(self, tx):
        node = self.active
        self.displayed_tx = tx
        slot = f"  ·  槽 {node.slot + 1}" if self.brand == 0 else ""
        query = "\n查询 TX 0x7FF" if self.brand == 1 else ""
        self.route.setText(f"CAN{node.port}  ·  TX 0x{tx:03X}  ·  RX 0x{node.rx:03X}{slot}{query}")

    def update_state_badge(self, text):
        palette = {
            State.RUNNING: "running", State.STARTING: "busy", State.SCANNING: "busy",
            State.STOPPING: "busy", State.FAULT: "fault",
        }.get(self.state, "idle")
        self.state_label.setText(text)
        if self.state_label.property("state") != palette:
            self.state_label.setProperty("state", palette)
            self.state_label.style().unpolish(self.state_label)
            self.state_label.style().polish(self.state_label)

    def capture(self, data):
        if self.curve_paused or (self.online and self.last_seq == data[5]) or (not self.online and not self.was_online):
            return
        if self.start_tick is None:
            self.start_tick = data[1]
        t = ((data[1] - self.start_tick) & 0xffffffff) / 1000
        if self.online:
            running = self.state == State.RUNNING
            speed, pos, effort = (real(data[i]) for i in (7, 8, 9))
            speed_target = real(data[24]) if running and self.mode.currentIndex() == 0 else None
            pos_target = real(data[24]) if running and self.mode.currentIndex() == 1 else None
            self.last_seq = data[5]
        else:
            speed = pos = effort = speed_target = pos_target = None
        self.was_online = self.online
        self.samples.append((t, speed, pos, effort, speed_target, pos_target))
        self.speed_chart.add(t, speed, speed_target)
        self.position_chart.add(t, pos, pos_target)
        self.effort_chart.add(t, effort)

    def set_chart_range(self, index):
        for chart in self.charts:
            chart.window = (10, 30, 60)[index]
            chart.update()

    def toggle_pause(self, paused):
        self.curve_paused = paused
        self.pause.setText("继续绘图" if paused else "暂停绘图")
        if not paused and self.samples:
            gap = self.samples[-1][0] + 0.001
            for chart in self.charts:
                chart.add(gap, None)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出采样", "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                output = csv.writer(file)
                output.writerow(("时间_s", "转速_rpm", "相对位置_deg", self.effort_chart.title, "目标转速_rpm", "目标位置_deg"))
                output.writerows(self.samples)
            self.notify(f"已导出 {len(self.samples)} 条记录。")
        except OSError as error:
            self.notify(str(error), True)

    def closeEvent(self, event):
        if self.flashing:
            event.ignore()
            self.notify("正在操作 Flash，请等待烧录和校验结束。")
            return
        self.worker.send("quit")
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    worker = ProbeWorker()
    window = BenchWindow(worker)
    worker.start()
    worker.send("list")
    window.show()
    code = app.exec()
    worker.join(timeout=2.0)
    return code


if __name__ == "__main__":
    sys.exit(main())
