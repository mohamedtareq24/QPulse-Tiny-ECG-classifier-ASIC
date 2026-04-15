"""cocotb test entrypoint for the TX UVC standalone testbench."""
import os

import cocotb
from pyuvm import uvm_root

from ecg_uvm.runtime import set_dut
from ecg_uvm.uart_vif import ECGUartVif
from pyuvm import ConfigDB

# Register all test classes with the pyuvm factory.
from ecg_uvm.uart_tx_uvc.test.tb_uvm.tx_uvc_tests import (  # noqa: F401
    TxUvcCsrApStartPulseTest,
    TxUvcCsrQualifierDisableTest,
    TxUvcCsrQualifierEnableTest,
    TxUvcCsrQualifierToggleTest,
    TxUvcCsrSanityTest,
    TxUvcCsrSoftResetTest,
    TxUvcOneEpochTest,
    TxUvcTenEpochTest,
)


@cocotb.test()
async def run_tx_uvc_test(dut):
    set_dut(dut)
    test_name = os.getenv("UVM_TESTNAME", "TxUvcOneEpochTest")
    await uvm_root().run_test(test_name)
