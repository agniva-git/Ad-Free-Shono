import io
import wave


def make_wav(frames: int = 4000, tone: int = 1) -> io.BytesIO:
    """A tiny valid WAV. A different `tone` gives different bytes (so it is not a duplicate)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes([tone % 256, (tone * 7) % 256]) * frames)
    buf.seek(0)
    return buf


def upload(client, name="track.wav", tone=1, **form):
    res = client.post("/api/upload", files={"file": (name, make_wav(tone=tone), "audio/wav")}, data=form)
    assert res.status_code == 201, res.text
    return res.json()
