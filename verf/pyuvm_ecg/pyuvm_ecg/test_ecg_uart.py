import os

import cocotb
from pyuvm import ConfigDB, uvm_root

# Import tests so pyuvm factory sees them.
from ecg_uvm.runtime import set_dut
from ecg_uvm.uart_vif import ECGUartVif
from ecg_uvm.tests.test_lib import (  # noqa: F401
    ECGFullDatasetTest,
    ECGMiniRegressionTest,
    ECGQualifierToggleTest,
    ECGSmokeTest,
    ECGSoftResetTest,
    ECGTenEpochTest,
)
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
async def run_pyuvm_uart_env(dut):
    set_dut(dut)  # Keep for backward compat if needed elsewhere

    vif = ECGUartVif(dut)
    ConfigDB().set(None, "*", "vif", vif)

    test_name = os.getenv("UVM_TESTNAME", "ECGSmokeTest")
    await uvm_root().run_test(test_name)
