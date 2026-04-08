import sys
import os
import re
import time
import queue
import threading
import datetime
import contextlib
import io


@contextlib.contextmanager
def _suppress_f5tts_output():
    """Suppress stdout and stderr at both Python object and OS file-descriptor level.

    Python-level redirect catches library print() calls.
    OS fd-level redirect catches native code (objc dylib warnings, C extensions).
    """
    # Python-level redirect
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    # OS fd-level redirect (catches objc/dyld warnings from C extensions)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)

    try:
        yield
    finally:
        # Restore OS file descriptors first
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        # Restore Python objects
        sys.stdout = old_out
        sys.stderr = old_err

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from My_Tools.AIVT_print import aprint

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

f5tts_parameters = {
    "ref_audio":  os.path.join(PROJECT_ROOT, "TextToSpeech", "reference", "nahida_ref.wav"),
    "ref_text":   "",
    "nfe_step":   8,
    "speed":      1.0,
    "output_dir": os.path.join(PROJECT_ROOT, "Audio", "tts"),
}

# Sentinel value returned when streaming has already handled playback
STREAMED_SENTINEL = "__F5TTS_STREAMED__"

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from f5_tts.api import F5TTS as _F5TTS
                aprint("* Loading F5-TTS model (first time only)... *")
                with _suppress_f5tts_output():
                    _model = _F5TTS()
                aprint(f"* F5-TTS model loaded (device: {_model.device}) *")
    return _model


def split_sentences(text: str) -> list:
    """Split text on Chinese sentence-ending punctuation. Merges fragments < 5 chars."""
    parts = re.split(r'(?<=[。！？])', text)
    sentences = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        buf += p
        if len(buf) >= 5:
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)
    return sentences if sentences else [text]


def _generate_sentence(text: str, output_path: str) -> str:
    """Generate speech for one sentence and save to output_path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    model = _get_model()
    with _suppress_f5tts_output():
        model.infer(
            ref_file  = f5tts_parameters["ref_audio"],
            ref_text  = f5tts_parameters["ref_text"],
            gen_text  = text,
            file_wave = output_path,
            nfe_step  = f5tts_parameters["nfe_step"],
            speed     = f5tts_parameters["speed"],
            show_info = lambda x: None,
        )
    return output_path


_QUEUE_DONE = None


def f5tts_streaming(text: str, output_device: str = "") -> str:
    """
    Split text into sentences and stream: generate each sentence then play it
    immediately, overlapping generation of the next sentence with playback.
    Blocks until all sentences are played. Returns STREAMED_SENTINEL.
    """
    import Play_Audio

    sentences = split_sentences(text)
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    audio_queue = queue.Queue()

    def generator():
        for i, sentence in enumerate(sentences, 1):
            out = os.path.join(f5tts_parameters["output_dir"], f"{ts}_f5_{i:02d}.wav")
            _generate_sentence(sentence, out)
            audio_queue.put(out)
        audio_queue.put(_QUEUE_DONE)

    def player():
        while True:
            path = audio_queue.get()
            if path is _QUEUE_DONE:
                break
            Play_Audio.PlayAudio(path, output_device_name=output_device)

    gen_thread  = threading.Thread(target=generator, daemon=True)
    play_thread = threading.Thread(target=player,    daemon=True)
    gen_thread.start()
    play_thread.start()
    gen_thread.join()
    play_thread.join()

    return STREAMED_SENTINEL


def f5tts(text: str, output_path: str) -> str:
    """Single-shot generation without streaming. Returns output_path."""
    return _generate_sentence(text, output_path)
