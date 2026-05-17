# UART Communication Troubleshooting Guide

## Issue Symptoms

- `asyncio.TimeoutError` in `UARTTxDriver.run_phase()` during `writer.drain()`
- RX monitor: "RX timeout waiting for DUT response byte"
- Scoreboard mismatches (one-hot encoding errors)
- Test hangs or fails after initial communication

## Root Cause Analysis

### 1. **UART Write Timeout (Most Common)**
When `writer.drain()` times out, the UART transmission buffer cannot be flushed because:
- **Flow control blocking**: RTS/CTS or DSR/DTR handshakes are preventing transmission
- **Device not accepting data**: USB serial adapter or DUT is not ready
- **Buffer full**: The device-side UART buffer is full

### 2. **DUT Not Responding**
When RX monitor gets no response:
- DUT is halted or crashed
- UART RX line not properly connected
- DUT firmware/hardware not responding to input

### 3. **Mismatches During Communication**
One-hot encoding mismatches suggest:
- Data corruption during transmission
- Timing synchronization issues
- Baud rate mismatch between host and DUT

## Diagnostic Steps

### Step 1: Verify Physical Connection
```bash
# Check if USB serial device exists and is readable/writable
ls -la /dev/ttyUSB0
lsusb -v | grep -A5 "FT232"  # For common USB-UART adapters

# Test basic communication with a known good sequence
stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb
echo -ne '\x00\x00' > /dev/ttyUSB0
```

### Step 2: Monitor Raw UART Traffic
```bash
# Capture UART traffic while running test
cat /dev/ttyUSB0 > uart_capture.bin &
BG_PID=$!
timeout 5 python run_hil.py --test ECGSmokeTest --port /dev/ttyUSB0 2>&1 | tee test.log
kill $BG_PID

# Analyze captured data
xxd uart_capture.bin | head -20
```

### Step 2: Monitor Raw UART Traffic
```bash
# Capture UART traffic while running test
cat /dev/ttyUSB0 > uart_capture.bin &
BG_PID=$!
timeout 5 python run_hil.py --test ECGSmokeTest --port /dev/ttyUSB0 2>&1 | tee test.log
kill $BG_PID

# Analyze captured data
xxd uart_capture.bin | head -20
```

## Step 3: FTDI-Specific Configuration

### Check FTDI Chip Details
```bash
# Identify FTDI chip and drivers
lsusb -v | grep -A10 "FTDI"
dmesg | grep -i ftdi | tail -20

# Check FTDI eeprom settings (requires libftdi tools)
sudo ftdi_eeprom --read-eeprom /dev/ttyUSB0
```

### Optimize FTDI Latency Timer
FTDI chips have a USB latency timer (default 2ms) that can cause delays:

```bash
# Install libftdi-dev if needed for ftdi_eeprom
sudo apt-get install libftdi-dev

# Set FTDI latency to 1ms (lower = faster response to data)
sudo python3 << 'EOF'
import ftdi
ftdi_dev = ftdi.new()
# Bitbang mode: ID 0
if ftdi_dev.usb_open_desc(0x0403, 0x6001, None, None) == 0:
    ftdi_dev.setlatencytimer(1)  # 1ms latency
    ftdi_dev.usb_close()
    print("FTDI latency set to 1ms")
else:
    print("Failed to open FTDI device")
EOF
```

### Increase FTDI USB RX Buffer
```bash
# Check current USB buffer settings
cat /sys/module/ftdi_sio/parameters/read_urb_length

# Increase RX buffer (requires driver reload)
echo 4096 | sudo tee /sys/module/ftdi_sio/parameters/read_urb_length
```

### Alternative: Use ftdi_eeprom to Persist Settings
```bash
# Create config file for your FTDI chip
cat > ftdi_config.conf << 'EOF'
vendor_id=0x0403
product_id=0x6001
in_is_isochronous=0
out_is_isochronous=0
use_serial=1
high_current=0
channel_a_type=UART
channel_b_type=UART
power_save=0
clock_polarity=0
data_order=0
flow_control=0
manufacturer="FTDI"
product="USB UART"
serial="A50285BI"
timeout=5000
latency_timer=1
EOF

# Apply to FTDI chip (careful: this modifies EEPROM)
# sudo ftdi_eeprom --erase-eeprom /dev/ttyUSB0
# sudo ftdi_eeprom --build-eeprom ftdi_config.conf /dev/ttyUSB0
# sudo ftdi_eeprom --flash-eeprom /dev/ttyUSB0
```

### Step 4: Check FTDI Driver Load Settings
```bash
# Display current serial port configuration
stty -F /dev/ttyUSB0 -a

# Verify no flow control is blocking
# Should show: -crtscts (no RTS/CTS flow control)
# Should show: -ixoff (no XON/XOFF)
```

### Step 4: Test with Longer Timeouts
Try increasing the byte timeout to see if the issue is timing-related:
```bash
python run_hil.py --test ECGSmokeTest --port /dev/ttyUSB0 \
  --byte-timeout 5.0 --timeout 60.0
```

### Step 5: Enable Driver Logging
The improved drivers now log detailed error information:
- TX driver logs packet data and timeout duration
- RX monitor counts consecutive timeouts
- If you see 5+ consecutive RX timeouts, DUT communication has failed

## Fixes Applied

### Transport Layer (transport.py)
- **Disabled flow control**: Added `rtscts=False`, `dsrdtr=False`, `xonxoff=False`
- **Added inter-byte timeout**: Set `inter_byte_timeout=0.1` to prevent EOF errors

### TX Driver (uart_tx_agent.py)
- **Enhanced error logging**: Now shows which packet caused the timeout
- **Better error messages**: Indicates whether device or flow control is likely the issue

### RX Monitor (uart_rx_agent.py)
- **Timeout counting**: Tracks consecutive timeouts to detect communication failure
- **Threshold detection**: After 5 timeouts, logs that DUT communication has failed
- **Improved diagnostics**: Clearer messages about likely causes

## Common Resolutions

### For FTDI-Specific Issues:

#### FTDI Latency Timer Too High (Most Common)
FTDI devices have a 2ms default latency that buffers USB packets. For real-time communication:
```bash
# Reduce latency to 1ms (requires pyftdi or libftdi)
sudo python3 -c "
import ftdi
dev = ftdi.new()
if dev.usb_open_desc(0x0403, 0x6001, None, None) == 0:
    dev.setlatencytimer(1)
    dev.usb_close()
    print('Set FTDI latency to 1ms')
"

# Or reload ftdi_sio driver with read_urb_length=64
sudo modprobe -r ftdi_sio
sudo modprobe ftdi_sio read_urb_length=64
```

#### FTDI Reset or Reconnect Issues
```bash
# Force FTDI device reset if hanging
sudo sh -c 'echo 1 > /sys/bus/usb/devices/*/power/on'

# Check for FTDI device disconnections in dmesg
dmesg | grep -i "ftdi.*disconnect\|usb.*reset"

# Verify device is still present
lsusb | grep FTDI
```

#### FTDI RX Buffer Overflow
If you see corrupted bytes or dropped data:
```bash
# Increase USB endpoint buffer size
echo 16384 | sudo tee /sys/module/ftdi_sio/parameters/read_urb_length

# Increase kernel tty buffer
cat /proc/sys/net/ipv4/tcp_rmem  # Check current values
sudo sysctl -w net.core.rmem_max=134217728
```

#### FTDI Flow Control Legacy Behavior
Some FTDI devices have RTS/CTS or DTR/DSR configured in EEPROM:
```bash
# Check EEPROM settings
sudo ftdi_eeprom --read-eeprom /dev/ttyUSB0

# If flow control is enabled in EEPROM, disable it and rewrite
# (This requires modifying the EEPROM—be careful!)
```

### For "Flow Control Blocking" Errors:
1. Check USB serial adapter settings
2. Verify DUT is powered and responding
3. Try a different USB cable or port
4. Disable flow control in FPGA UART core if possible

### For "DUT Not Responding":
1. Check FPGA programming status
2. Verify DUT UART RX pin is connected
3. Monitor DUT with logic analyzer to confirm it receives data
4. Check DUT firmware for UART initialization bugs

### For "Baud Rate Mismatch":
1. Verify `--baud 115200` matches FPGA clock and UART divider
2. Check `uart_bauddiv` in cfg.py (default: 16)
3. Calculate actual baud: `clk_freq / (uart_bauddiv * 10) = baud_rate`

## Expected Timing

At 115200 baud, each byte takes:
- **Time per bit**: ~8.7 µs
- **Time per byte** (10 bits): ~87 µs
- **Time for 2 bytes**: ~174 µs

So 2-second timeout should be more than sufficient unless the DUT is stalled.

## Next Steps

If issues persist after applying fixes:
1. Capture and analyze raw UART traffic
2. Check DUT logs/status output
3. Verify UART RX/TX lines with oscilloscope
4. Consider adding explicit RTS/CTS handling if your device requires it
