import os
import sys

from evdev import UInput, ecodes, AbsInfo
# Establish usb communication with device
import usb
import yaml


path = os.path.join(os.path.dirname(__file__), "config.yaml")
# Loading tablet configuration
with open(path, "r") as f: config = yaml.load(f, Loader=yaml.FullLoader)

# Get the required ecodes from configuration
pen_codes = []
btn_codes = []
for k, v in config["actions"].items():
    codes = btn_codes if k == "tablet_buttons" else pen_codes
    if isinstance(v, list): codes.extend(v)
    else: codes.append(v)

tempP = []
for p in pen_codes: tempP.extend([ecodes.ecodes[x] for x in p.split("+")])
pen_codes = tempP

tempB = []
for b in btn_codes: tempB.extend([ecodes.ecodes[x] for x in b.split("+")])
btn_codes = tempB

pen_events = {
    ecodes.EV_KEY: pen_codes,
    ecodes.EV_ABS: [
        (ecodes.ABS_X, AbsInfo(0, 0, config["pen"]["max_x"], 0, 0, config["pen"]["resolution_x"])),         
        (ecodes.ABS_Y, AbsInfo(0, 0, config["pen"]["max_y"], 0, 0, config["pen"]["resolution_y"])),
        (ecodes.ABS_PRESSURE, AbsInfo(0, 0, config["pen"]["max_pressure"], 0, 0, 0))
    ],
}

btn_events = {ecodes.EV_KEY: btn_codes}

# Find the device
dev = usb.core.find(idVendor=config["vendor_id"], idProduct=config["product_id"])
# Interface [0] refers to mass storage
# Interface [1] does not reac in any way
# Select end point for reading second interface [2] for actual data
ep = dev[0].interfaces()[2].endpoints()[0]
# Reset the device (don't know why, but till it works don't touch it)
dev.reset()

# Drop default kernel driver from all devices
for i in [0, 1, 2]:
    if dev.is_kernel_driver_active(i): dev.detach_kernel_driver(i)

# Set new configuration
dev.set_configuration()

vpen = UInput(events=pen_events, name=config["xinput_name"], version=0x3)
vbtn = UInput(events=btn_events, name=config["xinput_name"] + "_buttons", version=0x3)

pressed = -1

# Direction and axis configuration
max_x = config["pen"]["max_x"] * config["settings"]["swap_direction_x"]
max_y = config["pen"]["max_y"] * config["settings"]["swap_direction_y"]
x1, x2, y1, y2 = (3, 2, 5, 4) if config["settings"]["swap_axis"] else (5, 4, 3, 2)

# Infinite loop
while True:
    try:
        data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize)
        if data[1] in [192, 193]: # Pen actions
            pen_x = abs(max_x - (data[x1] * 255 + data[x2]))
            pen_y = abs(max_y - (data[y1] * 255 + data[y2]))
            pen_pressure = data[7] * 255 + data[6]
            vpen.write(ecodes.EV_ABS, ecodes.ABS_X, pen_x)
            vpen.write(ecodes.EV_ABS, ecodes.ABS_Y, pen_y)
            vpen.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, pen_pressure)
            if data[1] == 192: vpen.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
            else: vpen.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1)
        elif data[0] == 2: # Tablet button actions
            press_type = 1
            if data[3] == 86: pressed = 0
            elif data[3] == 87: pressed = 1
            elif data[3] == 47: pressed = 2
            elif data[3] == 48: pressed = 3
            elif data[3] == 43: pressed = 4
            elif data[3] == 44: pressed = 5
            else: press_type = 0
            key_codes = config["actions"]["tablet_buttons"][pressed].split("+")
            for key in key_codes:
                act = ecodes.ecodes[key]
                vbtn.write(ecodes.EV_KEY, act, press_type)
        # Flush
        vpen.syn()
        vbtn.syn()
    except usb.core.USBError as e:
        if e.args[0] == 19:
            vpen.close()
            raise Exception("Device has been disconnected")
    except KeyboardInterrupt:
        vpen.close()
        vbtn.close()
        sys.exit("\nDriver terminated successfully")
