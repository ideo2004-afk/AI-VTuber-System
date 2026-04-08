"""
F5-TTS 分句串流測試腳本
模擬 LLM 回傳完整文字後，分句逐句生成並立即播放的效果。

流程：
  生成執行緒：句1→生成→放入queue → 句2→生成→放入queue → ...
  播放執行緒：從queue取出→播放 → 取出→播放 → ...
  兩者並行，播放句1時同步生成句2，感知延遲只剩首句時間。

執行：
  ./venv/bin/python3 TextToSpeech/test_f5tts_streaming.py
"""

import sys
import os
import re
import time
import queue
import threading
import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import soundfile as sf
from f5_tts.api import F5TTS
import Play_Audio

# ── 設定 ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REF_AUDIO    = os.path.join(PROJECT_ROOT, "TextToSpeech", "reference", "nahida_ref.wav")
REF_TEXT     = "天气真好呀,暖洋洋的我们的身边马上也要热闹起来了."  # 參考音檔文字，固定不跑 Whisper
OUTPUT_DIR   = os.path.join(PROJECT_ROOT, "Audio", "tts", "streaming")
NFE_STEP     = 8

f5tts_parameters = {
    "ref_audio": REF_AUDIO,
    "ref_text":  REF_TEXT,
    "nfe_step":  NFE_STEP,
    "speed":     1.0,
}


# ── 分句 ─────────────────────────────────────────────────────────────────────
def split_sentences(text: str) -> list[str]:
    """
    按中文句末標點分句，過短的片段合併到下一句。
    """
    parts = re.split(r'(?<=[。！？])', text)
    sentences = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        buf += p
        if len(buf) >= 5:          # 至少 5 字才獨立成句
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)
    return sentences


# ── F5-TTS 生成 ───────────────────────────────────────────────────────────────
def generate_sentence(tts: F5TTS, text: str, output_path: str) -> float:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    t0 = time.perf_counter()
    tts.infer(
        ref_file  = f5tts_parameters["ref_audio"],
        ref_text  = f5tts_parameters["ref_text"],
        gen_text  = text,
        file_wave = output_path,
        nfe_step  = f5tts_parameters["nfe_step"],
        speed     = f5tts_parameters["speed"],
        show_info = lambda x: None,
    )
    return time.perf_counter() - t0


# ── 串流核心 ──────────────────────────────────────────────────────────────────
SENTINEL = None  # 放入 queue 代表生成結束

def streaming_tts_and_play(text: str, tts: F5TTS, output_device: str = ""):
    """
    分句串流：生成執行緒 + 播放執行緒並行。
    回傳 (首句感知延遲, 總耗時)
    """
    sentences = split_sentences(text)
    if not sentences:
        return 0, 0

    print(f"\n共 {len(sentences)} 句：")
    for i, s in enumerate(sentences, 1):
        print(f"  [{i}] {s}")
    print()

    audio_queue = queue.Queue()
    t_start = time.perf_counter()
    first_play_time = [None]

    # ── 生成執行緒 ──
    def generator():
        ts = datetime.datetime.now().strftime("%H%M%S")
        for i, sentence in enumerate(sentences, 1):
            out = os.path.join(OUTPUT_DIR, f"{ts}_s{i:02d}.wav")
            t0 = time.perf_counter()
            generate_sentence(tts, sentence, out)
            elapsed = time.perf_counter() - t0
            print(f"  生成[{i}] {elapsed:.2f}s  → {os.path.basename(out)}")
            audio_queue.put((i, sentence, out))
        audio_queue.put(SENTINEL)

    # ── 播放執行緒 ──
    def player():
        while True:
            item = audio_queue.get()
            if item is SENTINEL:
                break
            i, sentence, path = item
            if first_play_time[0] is None:
                first_play_time[0] = time.perf_counter() - t_start
                print(f"\n  ★ 首句開始播放（感知延遲 {first_play_time[0]:.2f}s）")
            print(f"  播放[{i}] {sentence}")
            Play_Audio.PlayAudio(path, output_device_name=output_device)

    gen_thread  = threading.Thread(target=generator, daemon=True)
    play_thread = threading.Thread(target=player, daemon=True)

    gen_thread.start()
    play_thread.start()

    gen_thread.join()
    play_thread.join()

    total = time.perf_counter() - t_start
    return first_play_time[0], total


# ── 測試 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("載入 F5-TTS 模型...")
    t0 = time.perf_counter()
    tts = F5TTS()
    print(f"載入完成（{time.perf_counter()-t0:.1f}s），裝置：{tts.device}\n")

    # 模擬 LLM 回傳的較長回應
    test_texts = [
        "大家好！我是你們的虛擬主播！今天心情很好，讓我們一起來玩遊戲吧！",
        "哇，這個關卡好難！但是沒關係，我不會放棄的！加油加油！我一定可以過關！",
        "謝謝大家的支持！你們的留言我都有看到！有你們陪伴真的很開心！下次見！",
    ]

    for idx, text in enumerate(test_texts, 1):
        print("=" * 60)
        print(f"測試 {idx}：{text}")
        print("=" * 60)

        first_latency, total = streaming_tts_and_play(text, tts)

        print(f"\n  首句感知延遲：{first_latency:.2f}s")
        print(f"  總耗時：      {total:.2f}s\n")
