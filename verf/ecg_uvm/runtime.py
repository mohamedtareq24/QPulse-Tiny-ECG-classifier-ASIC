_DUT = None
_CFG = None


def set_dut(dut) -> None:
    global _DUT
    _DUT = dut


def get_dut():
    if _DUT is None:
        raise RuntimeError("DUT handle was not initialized")
    return _DUT


def set_cfg(cfg) -> None:
    global _CFG
    _CFG = cfg


def get_cfg():
    if _CFG is None:
        raise RuntimeError("Environment config was not initialized")
    return _CFG
