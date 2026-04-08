import pyaudio

_pyaudio_instance = None

def get_pyaudio():
    global _pyaudio_instance
    if _pyaudio_instance is None:
        _pyaudio_instance = pyaudio.PyAudio()
    return _pyaudio_instance
