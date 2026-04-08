"""
Kokoro TTS 獨立測試腳本
測試各語音的音質與生成延遲，評估是否適合整合進 AI VTuber 系統。

模型檔案位置：models/kokoro/
  kokoro-v1.0.int8.onnx  (~88 MB, int8 量化版)
  voices-v1.0.bin

安裝：
  ./venv/bin/pip install kokoro-onnx==0.4.7

執行：
  ./venv/bin/python3 TextToSpeech/test_kokoro_tts.py
"""

import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import soundfile as sf
from kokoro_onnx import Kokoro

# ── 路徑設定 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MODEL_PATH   = os.path.join(PROJECT_ROOT, "models", "kokoro", "kokoro-v1.0.int8.onnx")
VOICES_PATH  = os.path.join(PROJECT_ROOT, "models", "kokoro", "voices-v1.0.bin")
OUTPUT_DIR   = os.path.join(PROJECT_ROOT, "Audio", "tts")

# ── 可用語音（v1.0 模型，普通話）────────────────────────────────────────────
#   女聲：zf_xiaobei  zf_xiaoni  zf_xiaoxiao  zf_xiaoyi
#   男聲：zm_yunjian  zm_yunxi   zm_yunxia    zm_yunyang

kokoro_parameters = {
    "model_path":  MODEL_PATH,
    "voices_path": VOICES_PATH,
    "voice":       "zf_xiaoni",
    "speed":       1.0,
    "lang":        "cmn",  # espeak-ng 的普通話語言代碼，"zh" 不被支援
}


def kokorotts(
        text: str,
        output_path: str,
        voice: str       = "zf_xiaoni",
        speed: float     = 1.0,
        lang: str        = "cmn",
        model_path: str  = MODEL_PATH,
        voices_path: str = VOICES_PATH,
        kokoro_instance  = None,
) -> float:
    """
    生成語音並存至 output_path。
    回傳生成耗時（秒）。
    可傳入已建立的 kokoro_instance 避免重複載入模型。
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    t0 = time.perf_counter()
    kokoro = kokoro_instance or Kokoro(model_path, voices_path)
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
    sf.write(output_path, samples, sample_rate)
    elapsed = time.perf_counter() - t0

    print(f"  → 已存：{os.path.basename(output_path)}  ({elapsed:.2f}s)")
    return elapsed


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("Kokoro TTS 測試 — 普通話語音 × 繁體中文文字")
    print(f"模型：{os.path.basename(MODEL_PATH)}")
    print("=" * 60)

    # 預先載入模型（第一次載入會慢 2–5 秒）
    print("\n載入模型中...")
    t_load = time.perf_counter()
    kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    print(f"模型載入完成（{time.perf_counter() - t_load:.2f}s）\n")

    test_cases = [
        # (編號_標籤, 文字, 語音)
        ("01_zf_xiaoni",
         "大家好！我是你們的虛擬主播，很高興認識你們！",
         "zf_xiaoni"),

        ("02_zf_xiaobei",
         "大家好！我是你們的虛擬主播，很高興認識你們！",
         "zf_xiaobei"),

        ("03_zf_xiaoxiao",
         "大家好！我是你們的虛擬主播，很高興認識你們！",
         "zf_xiaoxiao"),

        ("04_zf_xiaoyi",
         "大家好！我是你們的虛擬主播，很高興認識你們！",
         "zf_xiaoyi"),

        ("05_zm_yunxi",
         "各位觀眾大家好，今天我們來玩一個有趣的遊戲。",
         "zm_yunxi"),

        ("06_short_latency",
         "你好！",
         "zf_xiaoni"),

        ("07_medium_latency",
         "哇，這個遊戲好難！但是我不會放棄的！加油！",
         "zf_xiaoni"),

        ("08_long_latency",
         "在遙遠的地方，有一座美麗的城市，城市裡的人們每天都過著幸福快樂的生活，他們互相幫助，共同創造美好的未來。",
         "zf_xiaoni"),
    ]

    latencies = []
    for label, text, voice in test_cases:
        out_path = os.path.join(OUTPUT_DIR, f"kokoro_{label}.wav")
        print(f"[{label}]  語音：{voice}")
        print(f"  文字：{text}")
        elapsed = kokorotts(
            text=text,
            output_path=out_path,
            voice=voice,
            speed=1.0,
            lang="cmn",
            kokoro_instance=kokoro,
        )
        latencies.append((label, elapsed))
        print()

    print("=" * 60)
    print("延遲總結")
    print("=" * 60)
    for label, t in latencies:
        bar = "█" * int(t / 0.1)
        print(f"  {label:<25} {t:>5.2f}s  {bar}")

    print(f"\n輸出目錄：{OUTPUT_DIR}")
    print("請用播放器聆聽 kokoro_*.wav 評估音質。\n")

    # 選用：透過系統播放第一個輸出
    try:
        import Play_Audio
        first = os.path.join(OUTPUT_DIR, "kokoro_01_zf_xiaoni.wav")
        if os.path.exists(first):
            print(f"播放：{os.path.basename(first)}")
            Play_Audio.PlayAudio(first, output_device_name="")
    except Exception as e:
        print(f"[自動播放略過] {e}")
