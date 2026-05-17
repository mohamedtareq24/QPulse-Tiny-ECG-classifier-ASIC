_CFG = None
_SERIAL_TRANSPORT = None
_ADC_JTAG_TRANSPORT = None


def set_cfg(cfg) -> None:
    global _CFG
    _CFG = cfg


def get_cfg():
    global _CFG
    if _CFG is not None:
        return _CFG

    # Fallback path for environments that alias/import this package under
    # multiple module names (for example ecg_uvm.* -> adc_uvm.* during dry-run).
    # In that case, one runtime module instance may miss set_cfg() while ConfigDB
    # still contains the canonical configuration object.
    try:
        from pyuvm import ConfigDB

        cfg = ConfigDB().get(None, "", "cfg")
    except Exception as exc:
        raise RuntimeError("Environment config was not initialized") from exc

    _CFG = cfg
    return _CFG


def set_serial_transport(transport) -> None:
    global _SERIAL_TRANSPORT
    _SERIAL_TRANSPORT = transport


def get_serial_transport():
    if _SERIAL_TRANSPORT is None:
        raise RuntimeError("Serial transport was not initialized")
    return _SERIAL_TRANSPORT


def set_adc_jtag_transport(transport) -> None:
    global _ADC_JTAG_TRANSPORT
    _ADC_JTAG_TRANSPORT = transport


def get_adc_jtag_transport():
    if _ADC_JTAG_TRANSPORT is None:
        raise RuntimeError("ADC JTAG transport was not initialized")
    return _ADC_JTAG_TRANSPORT

