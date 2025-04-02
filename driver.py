import usb
import sys
from threading import Thread
from typing import List, Dict, Any
from evdev import UInput, ecodes, AbsInfo
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
  QApplication,
  QMainWindow,
  QTabWidget,
  QWidget,
  QVBoxLayout,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QSpinBox,
  QCheckBox,
  QPushButton,
  QGroupBox,
  QListWidget,
  QListWidgetItem,
  QInputDialog,
  QMessageBox
)


class Driver(QMainWindow):
  def __init__(self):
    super().__init__()
    self.setWindowTitle("Tablet driver")
    self.setGeometry(100, 100, 500, 350)
    self.injection_active = False

    self.settings = {
      "xinput_name": "10moons-pen",
      "vendor_id": "0x08f2",
      "product_id": "0x6811",
      "pen": {
        "max_x": 4096,
        "max_y": 4096,
        "max_pressure": 2047,
        "resolution_x": 20,
        "resolution_y": 30
      },
      "actions": {
        "pen": "BTN_TOOL_PEN",
        "stylus": "BTN_STYLUS",
        "pen_touch": "BTN_TOUCH",
        "pen_buttons": [
          "KEY_LEFTBRACE",
          "KEY_RIGHTBRACE"
        ],
        "tablet_buttons": [
          "KEY_LEFTCTRL+KEY_KPMINUS",
          "KEY_KPPLUS",
          "KEY_B",
          "KEY_F",
          "KEY_LEFTCTRL+KEY_Z",
          "KEY_SPACE"
        ]
      },
      "settings": {
        "swap_axis": False,
        "swap_direction_x": True,
        "swap_direction_y": False
      }
    }

    main_tab_widget = QTabWidget()

    injection_tab = self.create_injection_tab()
    main_tab_widget.addTab(injection_tab, "Injection")

    settings_tab = self.create_settings_tab()
    main_tab_widget.addTab(settings_tab, "Settings")

    central_widget = QWidget()
    central_widget.setLayout(QVBoxLayout())
    central_widget.layout().addWidget(main_tab_widget)
    self.setCentralWidget(central_widget)

  def create_injection_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    self.injection_status_label = QLabel("Injection has not started")
    self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.injection_status_label.setStyleSheet("font-size: 25px;")
    layout.addWidget(self.injection_status_label)

    self.toggle_injection_btn = QPushButton("Start injection")
    self.toggle_injection_btn.clicked.connect(self.toggle_injection)
    layout.addWidget(self.toggle_injection_btn)

    tab.setLayout(layout)
    return tab

  def toggle_injection(self) -> None:
    self.injection_active = not self.injection_active

    if self.injection_active:
      try:
        def convert_codes(target: List[str]) -> List[int]:
          temp = []
          for t in target: temp.extend([ecodes.ecodes[x] for x in t.split("+")])
          return temp

        def setEvents(target: List[int]) -> Dict[int, List[Any]]:
          if target == self.btn_codes: return {ecodes.EV_KEY: self.btn_codes}
          return {
            ecodes.EV_KEY: self.pen_codes,
            ecodes.EV_ABS: [
              (ecodes.ABS_X, AbsInfo(
                0, 0, self.settings["pen"]["max_x"], 0, 0, self.settings["pen"]["resolution_x"]
              )),
              (ecodes.ABS_Y, AbsInfo(
                0, 0, self.settings["pen"]["max_y"], 0, 0, self.settings["pen"]["resolution_y"]
              )),
              (ecodes.ABS_PRESSURE, AbsInfo(0, 0, self.settings["pen"]["max_pressure"], 0, 0, 0))
            ],
          }

        # Subtitle is indicated if the devices >= 2.
        def setUInput(any_events: Dict[int, List[Any]], subtitle: str) -> UInput:
          return UInput(events=any_events, name=self.settings["xinput_name"] + subtitle, version=0x3)

        def coordinate_axis(axis: str) -> int:
          return self.settings["pen"]["max_" + axis] * self.settings["settings"]["swap_direction_" + axis]

        # Get the required ecodes from configuration.
        self.pen_codes = []
        self.btn_codes = []
        for k, v in self.settings["actions"].items():
          codes = self.btn_codes if k == "tablet_buttons" else self.pen_codes
          if isinstance(v, list): codes.extend(v)
          else: codes.append(v)

        self.pen_codes = convert_codes(self.pen_codes)
        self.btn_codes = convert_codes(self.btn_codes)

        # Find the device.
        # NOTE: Idk why, but it needs to be converted to int, although it didn't need to do so before.
        self.dev = usb.core.find(
          idVendor=int(self.settings["vendor_id"], 16), idProduct=int(self.settings["product_id"], 16)
        )
        if self.dev is None: raise Exception("Device not found")
        # Interface [0] refers to mass storage.
        # Interface [1] does not reac in any way.
        # Select end point for reading second interface [2] for actual data.
        # FIXME: I couldn't find a stylus in the interface [2] and
        # in the documentation it is present in interface [1], but it is not supported.
        self.ep = self.dev[0].interfaces()[2].endpoints()[0]
        # Reset the device (don't know why, but till it works don't touch it).
        self.dev.reset()

        # Drop default kernel driver from all devices.
        for i in [0, 1, 2]:
          if self.dev.is_kernel_driver_active(i):
            self.dev.detach_kernel_driver(i)

        # Set new configuration.
        self.dev.set_configuration()

        self.vpen = setUInput(setEvents(self.pen_codes), "")
        self.vbtn = setUInput(setEvents(self.btn_codes), "_buttons")

        # Direction and axis configuration.
        self.max_x = coordinate_axis("x")
        self.max_y = coordinate_axis("y")
        self.x1, self.x2, self.y1, self.y2 = (3, 2, 5, 4) if self.settings["settings"]["swap_axis"] else (5, 4, 3, 2)

        self.pressed = -1

        # TODO: migrate from classic Thread to qt QThread?
        self.injection_thread = Thread(target=self.read_device_data)
        self.injection_thread.daemon = True
        self.injection_thread.start()

        self.injection_status_label.setText("Injection started")
        self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.injection_status_label.setStyleSheet("font-size: 25px; color: green;")
        self.toggle_injection_btn.setText("Stop injection")
      except Exception as e:
        self.injection_active = False
        QMessageBox.critical(self, "Error", f"Failed to start injection: {str(e)}")
        self.injection_status_label.setText("Injection failed")
        self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.injection_status_label.setStyleSheet("font-size: 25px; color: red;")
        self.toggle_injection_btn.setText("Start injection")
    else:
      if hasattr(self, "vpen"): self.vpen.close()
      if hasattr(self, "vbtn"): self.vbtn.close()

      self.injection_status_label.setText("Injection has not started")
      self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
      self.injection_status_label.setStyleSheet("font-size: 25px;")
      self.toggle_injection_btn.setText("Start injection")

  def read_device_data(self) -> None:
    while self.injection_active:
      try:
        data = self.dev.read(self.ep.bEndpointAddress, self.ep.wMaxPacketSize)
        # Pen codes.
        if data[1] in [192, 193]:
          pen_x = abs(self.max_x - (data[self.x1] * 255 + data[self.x2]))
          pen_y = abs(self.max_y - (data[self.y1] * 255 + data[self.y2]))
          pen_pressure = data[7] * 255 + data[6]
          self.vpen.write(ecodes.EV_ABS, ecodes.ABS_X, pen_x)
          self.vpen.write(ecodes.EV_ABS, ecodes.ABS_Y, pen_y)
          self.vpen.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, pen_pressure)
          if data[1] == 192: self.vpen.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
          else: self.vpen.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1)
        # Tablet button actions.
        elif data[0] == 2:
          press_type = 1
          if data[3] == 86: pressed = 0
          elif data[3] == 87: pressed = 1
          elif data[3] == 47: pressed = 2
          elif data[3] == 48: pressed = 3
          elif data[3] == 43: pressed = 4
          elif data[3] == 44: pressed = 5
          else: press_type = 0
          key_codes = self.settings["actions"]["tablet_buttons"][pressed].split("+")
          for key in key_codes:
            act = ecodes.ecodes[key]
            self.vbtn.write(ecodes.EV_KEY, act, press_type)
        # Flush.
        self.vpen.syn()
        self.vbtn.syn()
      except usb.core.USBError as e:
        if e.args[0] == 19:
          self.vpen.close()
          self.vbtn.close()
          self.injection_active = False
          self.injection_status_label.setText("Device disconnected")
          self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
          self.injection_status_label.setStyleSheet("font-size: 25px; color: red;")
          self.toggle_injection_btn.setText("Start injection")
          break
      except UnboundLocalError:
        self.vpen.close()
        self.vbtn.close()
        self.injection_active = False
        self.injection_status_label.setText("Device disconnected")
        self.injection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.injection_status_label.setStyleSheet("font-size: 25px; color: red;")
        self.toggle_injection_btn.setText("Start injection")
        break

  def create_settings_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    settings_sub_tabs = QTabWidget()

    basic_tab = self.setup_basic_tab()
    pen_tab = self.setup_pen_tab()
    actions_tab = self.setup_actions_tab()
    axis_tab = self.setup_axis_tab()

    settings_sub_tabs.addTab(basic_tab, "Name")
    settings_sub_tabs.addTab(pen_tab, "Pen")
    settings_sub_tabs.addTab(actions_tab, "Actions")
    settings_sub_tabs.addTab(axis_tab, "Axis")

    button_box = QHBoxLayout()
    save_btn = QPushButton("Save")
    save_btn.clicked.connect(self.save_settings)

    button_box.addWidget(save_btn)

    layout.addWidget(settings_sub_tabs)
    layout.addLayout(button_box)

    tab.setLayout(layout)
    return tab

  def setup_basic_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    name_group = QGroupBox("Device name")
    name_layout = QHBoxLayout()
    name_label = QLabel("XInput Name:")
    self.name_edit = QLineEdit(self.settings["xinput_name"])
    name_layout.addWidget(name_label)
    name_layout.addWidget(self.name_edit)
    name_group.setLayout(name_layout)

    id_group = QGroupBox("IDs")
    id_layout = QVBoxLayout()

    vendor_layout = QHBoxLayout()
    vendor_label = QLabel("Vendor ID:")
    self.vendor_edit = QLineEdit(self.settings["vendor_id"])
    vendor_layout.addWidget(vendor_label)
    vendor_layout.addWidget(self.vendor_edit)

    product_layout = QHBoxLayout()
    product_label = QLabel("Product ID:")
    self.product_edit = QLineEdit(self.settings["product_id"])
    product_layout.addWidget(product_label)
    product_layout.addWidget(self.product_edit)

    id_layout.addLayout(vendor_layout)
    id_layout.addLayout(product_layout)
    id_group.setLayout(id_layout)

    layout.addWidget(name_group)
    layout.addWidget(id_group)
    layout.addStretch()

    tab.setLayout(layout)
    return tab

  def setup_pen_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    max_group = QGroupBox("Maximum value")
    max_layout = QVBoxLayout()

    max_x_layout = QHBoxLayout()
    max_x_label = QLabel("Max X:")
    self.max_x_spin = QSpinBox()
    self.max_x_spin.setRange(0, 10000)
    self.max_x_spin.setValue(self.settings["pen"]["max_x"])
    max_x_layout.addWidget(max_x_label)
    max_x_layout.addWidget(self.max_x_spin)

    max_y_layout = QHBoxLayout()
    max_y_label = QLabel("Max Y:")
    self.max_y_spin = QSpinBox()
    self.max_y_spin.setRange(0, 10000)
    self.max_y_spin.setValue(self.settings["pen"]["max_y"])
    max_y_layout.addWidget(max_y_label)
    max_y_layout.addWidget(self.max_y_spin)

    pressure_layout = QHBoxLayout()
    pressure_label = QLabel("Max Pressure:")
    self.pressure_spin = QSpinBox()
    self.pressure_spin.setRange(0, 10000)
    self.pressure_spin.setValue(self.settings["pen"]["max_pressure"])
    pressure_layout.addWidget(pressure_label)
    pressure_layout.addWidget(self.pressure_spin)

    max_layout.addLayout(max_x_layout)
    max_layout.addLayout(max_y_layout)
    max_layout.addLayout(pressure_layout)
    max_group.setLayout(max_layout)

    res_group = QGroupBox("Resolution")
    res_layout = QVBoxLayout()

    res_x_layout = QHBoxLayout()
    res_x_label = QLabel("Resolution X:")
    self.res_x_spin = QSpinBox()
    self.res_x_spin.setRange(0, 100)
    self.res_x_spin.setValue(self.settings["pen"]["resolution_x"])
    res_x_layout.addWidget(res_x_label)
    res_x_layout.addWidget(self.res_x_spin)

    res_y_layout = QHBoxLayout()
    res_y_label = QLabel("Resolution Y:")
    self.res_y_spin = QSpinBox()
    self.res_y_spin.setRange(0, 100)
    self.res_y_spin.setValue(self.settings["pen"]["resolution_y"])
    res_y_layout.addWidget(res_y_label)
    res_y_layout.addWidget(self.res_y_spin)

    res_layout.addLayout(res_x_layout)
    res_layout.addLayout(res_y_layout)
    res_group.setLayout(res_layout)

    layout.addWidget(max_group)
    layout.addWidget(res_group)
    layout.addStretch()

    tab.setLayout(layout)
    return tab

  def setup_actions_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    basic_actions_group = QGroupBox("Main actions")
    basic_layout = QVBoxLayout()

    pen_layout = QHBoxLayout()
    pen_label = QLabel("Pen:")
    self.pen_edit = QLineEdit(self.settings["actions"]["pen"])
    pen_layout.addWidget(pen_label)
    pen_layout.addWidget(self.pen_edit)

    stylus_layout = QHBoxLayout()
    stylus_label = QLabel("Stylus:")
    self.stylus_edit = QLineEdit(self.settings["actions"]["stylus"])
    stylus_layout.addWidget(stylus_label)
    stylus_layout.addWidget(self.stylus_edit)

    touch_layout = QHBoxLayout()
    touch_label = QLabel("Pen Touch:")
    self.touch_edit = QLineEdit(self.settings["actions"]["pen_touch"])
    touch_layout.addWidget(touch_label)
    touch_layout.addWidget(self.touch_edit)

    basic_layout.addLayout(pen_layout)
    basic_layout.addLayout(stylus_layout)
    basic_layout.addLayout(touch_layout)
    basic_actions_group.setLayout(basic_layout)

    pen_buttons_group = QGroupBox("Pen buttons")
    self.pen_buttons_list = QListWidget()
    for btn in self.settings["actions"]["pen_buttons"]:
      QListWidgetItem(btn, self.pen_buttons_list)

    pen_buttons_layout = QVBoxLayout()
    pen_buttons_layout.addWidget(self.pen_buttons_list)

    pen_buttons_btn_layout = QHBoxLayout()
    add_pen_btn = QPushButton("Add")
    add_pen_btn.clicked.connect(self.add_pen_button)
    remove_pen_btn = QPushButton("Remove")
    remove_pen_btn.clicked.connect(self.remove_pen_button)

    pen_buttons_btn_layout.addWidget(add_pen_btn)
    pen_buttons_btn_layout.addWidget(remove_pen_btn)
    pen_buttons_layout.addLayout(pen_buttons_btn_layout)
    pen_buttons_group.setLayout(pen_buttons_layout)

    tablet_buttons_group = QGroupBox("Tablet buttons")
    self.tablet_buttons_list = QListWidget()
    for btn in self.settings["actions"]["tablet_buttons"]:
      QListWidgetItem(btn, self.tablet_buttons_list)

    tablet_buttons_layout = QHBoxLayout()
    tablet_buttons_layout.addWidget(self.tablet_buttons_list)

    tablet_buttons_btn_layout = QHBoxLayout()
    add_tablet_btn = QPushButton("Add")
    add_tablet_btn.clicked.connect(self.add_tablet_button)
    remove_tablet_btn = QPushButton("Remove")
    remove_tablet_btn.clicked.connect(self.remove_tablet_button)

    tablet_buttons_btn_layout.addWidget(add_tablet_btn)
    tablet_buttons_btn_layout.addWidget(remove_tablet_btn)
    tablet_buttons_layout.addLayout(tablet_buttons_btn_layout)
    tablet_buttons_group.setLayout(tablet_buttons_layout)

    layout.addWidget(basic_actions_group)
    layout.addWidget(pen_buttons_group)
    layout.addWidget(tablet_buttons_group)
    layout.addStretch()

    tab.setLayout(layout)
    return tab

  def setup_axis_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout()

    axis_group = QGroupBox("Axis settings")
    axis_layout = QVBoxLayout()

    self.swap_axis_check = QCheckBox("Swap the X/Y axis")
    self.swap_axis_check.setChecked(self.settings["settings"]["swap_axis"])

    self.swap_x_dir_check = QCheckBox("Invert X direction")
    self.swap_x_dir_check.setChecked(self.settings["settings"]["swap_direction_x"])

    self.swap_y_dir_check = QCheckBox("Invert Y direction")
    self.swap_y_dir_check.setChecked(self.settings["settings"]["swap_direction_y"])

    axis_layout.addWidget(self.swap_axis_check)
    axis_layout.addWidget(self.swap_x_dir_check)
    axis_layout.addWidget(self.swap_y_dir_check)
    axis_group.setLayout(axis_layout)

    layout.addWidget(axis_group)
    layout.addStretch()

    tab.setLayout(layout)
    return tab

  def add_pen_button(self) -> None:
    text, ok = QInputDialog.getText(self, "Add button", "Enter code button:")
    if ok and text: QListWidgetItem(text, self.pen_buttons_list)

  def remove_pen_button(self) -> None:
    if self.pen_buttons_list.currentItem():
      self.pen_buttons_list.takeItem(self.pen_buttons_list.currentRow())

  def add_tablet_button(self) -> None:
    text, ok = QInputDialog.getText(self, "Add button", "Enter code button:")
    if ok and text: QListWidgetItem(text, self.tablet_buttons_list)

  def remove_tablet_button(self) -> None:
    if self.tablet_buttons_list.currentItem():
      self.tablet_buttons_list.takeItem(self.tablet_buttons_list.currentRow())

  def save_settings(self) -> None:
    self.settings["xinput_name"] = self.name_edit.text()
    self.settings["vendor_id"] = self.vendor_edit.text()
    self.settings["product_id"] = self.product_edit.text()

    self.settings["pen"]["max_x"] = self.max_x_spin.value()
    self.settings["pen"]["max_y"] = self.max_y_spin.value()
    self.settings["pen"]["max_pressure"] = self.pressure_spin.value()
    self.settings["pen"]["resolution_x"] = self.res_x_spin.value()
    self.settings["pen"]["resolution_y"] = self.res_y_spin.value()

    self.settings["actions"]["pen"] = self.pen_edit.text()
    self.settings["actions"]["stylus"] = self.stylus_edit.text()
    self.settings["actions"]["pen_touch"] = self.touch_edit.text()

    self.settings["actions"]["pen_buttons"] = []
    for i in range(self.pen_buttons_list.count()):
      self.settings["actions"]["pen_buttons"].append(self.pen_buttons_list.item(i).text())

    self.settings["actions"]["tablet_buttons"] = []
    for i in range(self.tablet_buttons_list.count()):
      self.settings["actions"]["tablet_buttons"].append(self.tablet_buttons_list.item(i).text())

    self.settings["settings"]["swap_axis"] = self.swap_axis_check.isChecked()
    self.settings["settings"]["swap_direction_x"] = self.swap_x_dir_check.isChecked()
    self.settings["settings"]["swap_direction_y"] = self.swap_y_dir_check.isChecked()

    QMessageBox.information(
      self, "Save", "Settings successfully updated", QMessageBox.StandardButton.Ok
    )

if __name__ == "__main__":
  app = QApplication([])
  widget = Driver()
  widget.show()
  sys.exit(app.exec())
