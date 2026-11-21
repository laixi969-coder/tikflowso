"""Local-only FFmpeg + whisper.cpp transcriptions; no model downloads."""
from importlib.util import find_spec
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import wave

from workspace import RequestError

LIMIT_BYTES = 48 * 1024 * 1024
SLOT = threading.BoundedSemaphore(1)


def model():
    return Path(os.getenv("TIKFLOWSO_WHISPER_MODEL", Path(__file__).parent / ".data/models/whisper.bin"))


def available():
    return bool(model().is_file() and shutil.which("ffmpeg") and (shutil.which("whisper-cli") or find_spec("pywhispercpp")))


def transcribe(media, language="auto"):
    if not available():
        raise RequestError(503, "请配置本地语音识别引擎与 Whisper 权重")
    if language not in {"auto", "zh", "en"} or not 0 < len(media) <= LIMIT_BYTES:
        raise ValueError("请检查音轨文件大小和语言")
    if not SLOT.acquire(blocking=False):
        raise RequestError(429, "本机正在转写其他音轨，请稍后重试")
    try:
        with tempfile.TemporaryDirectory(prefix="tikflowso-asr-") as tmp:
            origin, audio, result = (Path(tmp) / n for n in ("source", "speech.wav", "captions"))
            origin.write_bytes(media)
            decode = subprocess.run(["ffmpeg","-nostdin","-v","error","-protocol_whitelist","file",
                "-format_whitelist","mov,matroska,webm,mp3,wav,aiff,aac,flac,ogg","-i",str(origin),
                "-map","0:a:0","-t","601","-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            if decode.returncode:
                raise ValueError("无法解码音轨，请选择含声音的本地音频或视频")
            with wave.open(str(audio)) as wav:
                duration = wav.getnframes() / wav.getframerate()
            if not 0 < duration <= 600:
                raise ValueError("单段音轨时长须大于零且不超过 10 分钟")
            if shutil.which("whisper-cli"):
                command = ["whisper-cli","-ng","-t","4","-l",language,"-m",str(model()),"-f",str(audio),
                           "-otxt","-osrt","-of",str(result)]
            else:
                command = [sys.executable, __file__, str(model()), str(audio), str(result), language]
            engine = subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
            if engine.returncode or not result.with_suffix(".srt").exists():
                raise RequestError(503, "本地语音识别引擎运行失败，请检查权重")
            return {"text":result.with_suffix(".txt").read_text().strip(),
                    "srt":result.with_suffix(".srt").read_text(), "seconds":round(duration,2)}
    except subprocess.TimeoutExpired as exc:
        raise RequestError(503, "本次音轨处理超时，请缩短文件后重试") from exc
    finally:
        SLOT.release()

if __name__ == "__main__":
    # The container ships CPU whisper.cpp bindings. Isolate inference for the same timeout as the CLI.
    from pywhispercpp.model import Model
    from pywhispercpp.utils import output_srt, output_txt
    weights, audio, output, language = sys.argv[1:]
    engine = Model(str(Path(weights).resolve(strict=True)), n_threads=4, context_params={"use_gpu":False})
    segments = engine.transcribe(audio, language=language)
    output_txt(segments, output)
    output_srt(segments, output)
