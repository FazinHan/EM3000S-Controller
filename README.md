# EM3000S Controller

Python control utilities for the Holmarc EM-3000S electromagnet power supply (serial/RS‑232 over VISA). This project contains a lightweight controller class and test scripts based on reverse‑engineered command logs.

Note: This repository is not affiliated with Holmarc. Use at your own risk and follow all lab safety practices when operating electromagnets and high‑current power supplies.

## Requirements

- Python 3.9+ (tested on Windows)
- PyVISA (`pyvisa`)
- A VISA backend
  - [NI‑VISA](https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html)
  - `pyvisa-py` was not found to work during initial testing
- Serial/COM access to the EM‑3000S (e.g., COM5 → `ASRL5::INSTR`)
- Ensure the vendor software is closed before running this code (it can lock the COM port)

## Install
The fastest, cleanest installation will happen using the `environment.yaml` file.
```bash
$ conda env create -f environment.yaml -n <env-name>
$ conda activate <env-name>
```

To identify your electromagnet:

```py
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())
```

The instrument will be labelled `ASRLx::INSTR`, where `x` will correspond to the COM port number.

Automatic detection is not implemented (is not planned either), however on Windows your COM port number can be discovered from device manager by unplugging all other instruments and noting the only serial over USB.

## Quickstart

```python
from HolmarcMagnet import Controller

magnet = Controller(resource_name='ASRL5::INSTR')  # e.g., COM5
if magnet.connect():
    try:
        magnet.set_current(1.0)     # set target current in Amps
        field = magnet.query_field() # read field (mT)
        print("Field:", field, "mT")

        magnet.pulse(-2.0, 5)       # pulse to -2 A for 5 s, then stop and read field
    finally:
        magnet.disconnect()
```

- Default serial settings: 19200 baud, 8 data bits, no parity, 1 stop bit, no terminations.

## API summary

Class: `HolmarcMagnet.Controller`

- `connect() -> bool`: Open and configure the VISA serial session
- `disconnect() -> None`: Close instrument and resource manager
- `set_current(amps: float) -> None`: Set target current (A)
- `query_field() -> float | None`: Read field in millitesla (mT) without performing a full stop
- `stop_and_query_field() -> float | str`: Stop output and read field (mT)
- `pulse(amps: float, duration_sec: int|float) -> None`: Set current, poll field during hold, then stop and read field
- `current_map(current_amps: float) -> list[int]`: Internal helper to convert amps → 4‑byte value

## Protocol notes (reverse‑engineered)

- Transport: Raw serial over VISA
- Settings: 19200 Baud, 8‑N‑1
- Pattern overview:
  - Ready check: `0x64`
  - Start/set value: `0x1E` then `0x2C` then 4 data bytes
  - End: `0x00` (followed by device `0x12` ack)
  - Stop: `0x2B`
  - Field query: `0x0A` then device returns 3 bytes: [mag_hi, mag_lo, sign]
- Field decoding:
  - Magnitude: `(hi << 8) | lo`, scale ≈ divide by 10 → mT
  - Sign byte: `0x00 = +`, `0x01 = −`
- Current encoding:
  - 4 bytes: `[mag_hi, mag_lo, 0x00, sign]`
  - Sign bit is last byte: `0x00 = −`, `0x01 = +`
  - Magnitude is linearly mapped from Amps (see `current_map`)

## Troubleshooting

- Port busy or VISA error: close vendor apps; confirm COM number; restart kernels
- No response/timeout: check baud

## Notes

- I derived the protocol here painfully from packet captures; minor variations may exist between firmware versions. I have no way to test with one electromagnet! 
- A small negative `startup_delay_sec` is used in `pulse` to tune readout timing; adjust as needed for your setup.