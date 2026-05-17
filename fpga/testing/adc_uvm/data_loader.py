from pathlib import Path

_NUM_CLASSES = 5


def _hex_lines(path: Path) -> list[int]:
    """Read every 0x... line in order, ignore everything else — same as readmemh."""
    values = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.lower().startswith("0x"):
                values.append(int(line, 16))
    return values


def load_input_frames(input_path: str, frame_len: int, num_frames: int) -> list[list[int]]:
    """Return raw 10-bit samples from the TV input dat, grouped into frames of frame_len."""
    samples = [v & 0x3FF for v in _hex_lines(Path(input_path))]
    if not samples:
        raise RuntimeError(f"no hex values found in input file: {input_path}")

    frames = []
    for i in range(num_frames):
        start = i * frame_len
        end = start + frame_len
        if end > len(samples):
            break
        frames.append(samples[start:end])

    if not frames:
        raise RuntimeError(f"input file has {len(samples)} samples, need at least {frame_len}")
    return frames


def load_reference_onehots(output_path: str, num_frames: int) -> tuple[list[int], str]:
    """Return expected one-hot bytes from the C-sim TV output dat.

    Each 0x... line is one packed transaction: _NUM_CLASSES x 16-bit words.
    Lower 10 bits of each word = signed ap_fixed logit. Returns 1<<argmax per transaction.
    """
    path = Path(output_path)
    if not path.exists():
        raise RuntimeError(f"output TV dat not found: {path}")

    onehots = []
    for packed in _hex_lines(path):
        logits = []
        for i in range(_NUM_CLASSES):
            word = (packed >> ((_NUM_CLASSES - 1 - i) * 16)) & 0xFFFF
            raw = word & 0x3FF
            if raw & 0x200:     # sign bit
                raw -= 0x400
            logits.append(raw)
        onehots.append(1 << logits.index(max(logits)))

    if len(onehots) < num_frames:
        raise RuntimeError(
            f"insufficient reference transactions: need={num_frames} have={len(onehots)}"
        )
    return onehots[:num_frames], str(path)
