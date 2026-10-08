"""Native PCM playback for Windows/Linux; no shell or platform tool names in core."""
import sounddevice
import soundfile


def play_wav(file) -> None:
    samples, rate = soundfile.read(str(file), dtype="float32", always_2d=True)
    if len(samples) == 0:
        raise ValueError("Audiodatei enthält keine Samples")
    sounddevice.play(samples, rate, blocking=True)
