_CFG = None


def set_cfg(cfg) -> None:
    global _CFG
    _CFG = cfg


def get_cfg():
    if _CFG is None:
        raise RuntimeError("Environment config was not initialized")
    return _CFG
