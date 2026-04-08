import os
import sys
import time
import threading
import queue
import json

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import questionary
from questionary import Style as QStyle

import AI_Vtuber_UI as aivtui
import Mic_Record as mcrc
import VTubeStudioPlugin.VTubeStudioPlugin as vtsp
from My_Tools.AIVT_print import aprint

_cli_style = QStyle([
    ("qmark",        "fg:#7ecfff bold"),
    ("question",     "bold"),
    ("answer",       "fg:#7ecfff bold"),
    ("pointer",      "fg:#7ecfff bold"),
    ("highlighted",  "fg:#7ecfff bold"),
    ("selected",     "fg:#7ecfff"),
    ("separator",    "fg:#444444"),
    ("instruction",  "fg:#888888"),
])

class AIVT_Core:
    def __init__(self, config_path="config.json"):
        aprint("=== AI-VTuber System Core CLI Starting ===")
        self.config_path = config_path
        self.running = True
        self.input_queue = queue.Queue() # New queue for terminal input
        
        # 1. Load Configuration
        aivtui.load_config_json(self.config_path)
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # 2. Interactive LLM Selection
        self.select_llm_mode()

        # 3. Initialize Backend State
        aivtui.GUI_Running = True
        aivtui.GUI_Auto_Mic_Mode = True # Default to auto mic for CLI
        
        # Load character and conversation
        aivtui.Load_AIVT_Character()
        aivtui.Initialize_conversation(self.config["user"]["character"])

        # Load instruction_enhance_prompt from character file (GUI mode does this on startup)
        aivtui.GUI_LLM_parameters["instruction_enhance_prompt"] = aivtui.get_instruction_enhance_prompt(
            self.config["user"]["character"]
        )
        
        # 4. Connect to VTube Studio (optional)
        self.vts_thread = None
        if self.config["vtube_studio"]["enabled"]:
            connect_vts = questionary.select(
                "是否連結 VTube Studio？",
                choices=["否", "是"],
                default="否",
                style=_cli_style,
            ).ask() == "是"
            if connect_vts:
                aprint("* Connecting to VTube Studio... *")
                self.vts_thread = threading.Thread(target=self.init_vtsp, daemon=True)
                self.vts_thread.start()
            else:
                aprint("* 跳過 VTube Studio 連線 *")

    def select_llm_mode(self):
        default = self.config['llm']['active']
        choices = [
            f"Google Gemini  ({self.config['llm']['gemini']['model']})",
            f"OpenAI GPT     ({self.config['llm']['gpt']['model']})",
            f"Ollama Local   ({self.config['llm']['ollama']['model']})",
        ]
        label_to_key = {
            choices[0]: "Gemini",
            choices[1]: "GPT",
            choices[2]: "Ollama",
        }
        default_choice = next((c for c in choices if label_to_key[c] == default), choices[0])

        selected_label = questionary.select(
            "請選擇 LLM 模式：",
            choices=choices,
            default=default_choice,
            style=_cli_style,
        ).ask()

        selected = label_to_key.get(selected_label, default)
        aivtui.GUI_LLM_parameters["model"] = selected
        aprint(f"➤ 已選擇模式: {selected}")

    def init_vtsp(self):
        # Trigger authentication and connection with config parameters
        vtsp.AIVT_VTSP_authenticated(
            host=self.config["vtube_studio"]["host"],
            port=self.config["vtube_studio"]["port"]
        )
        
        if vtsp.AIVT_VTSP_Status["authenticated"]:
            aprint("✓ VTube Studio Connected & Authenticated")
        else:
            aprint("! VTube Studio 未連線（請先開啟 VTube Studio 後重啟系統）")

    def run(self):
        # Start core background threads
        threading.Thread(target=aivtui.subtitles_speak_checker, daemon=True).start()
        threading.Thread(target=self.terminal_input_loop, daemon=True).start()

        # C. Microphone Monitor Loop
        # In CLI mode, we use Mic_Record's internal loops
        mcrc.User_Mic_parameters.update({
            "input_device_name": self.config["audio"]["mic_device"]
        })
        # Disable hotkeys to enable "Auto-Mic" / Continuous listening
        mcrc.user_mic_status["mic_hotkeys_using"] = False 
        
        aprint(f"\n[System Ready] User: {self.config['user']['name']} | Character: {self.config['user']['character']}")
        
        # Wait for VTS connection to settle, then set audio output accordingly
        import Play_Audio as pla
        if self.vts_thread:
            self.vts_thread.join(timeout=10)
        if vtsp.AIVT_VTSP_Status["authenticated"]:
            device = self.config["audio"].get("vts_output_device", "BlackHole 2ch")
            aprint(f"* 音訊輸出 → {device} (VTS模式) *")
        else:
            device = self.config["audio"].get("output_device", "")
            aprint(f"* 音訊輸出 → 系統預設 *")
        pla.play_audio_parameters["ai_voice_output_device_name"] = device
        
        aprint("Listening... (Press Ctrl+C to exit)\n")
        
        try:
            # Main Execution Loop
            while self.running:
                # 1. Check for transcribed text from Whisper
                if len(aivtui.OpenAI_Whisper_LLM_wait_list) > 0:
                    ans_request = aivtui.OpenAI_Whisper_LLM_wait_list.pop(0)
                    self.process_chat_request(ans_request)

                # 2. Check for manual terminal input
                if not self.input_queue.empty():
                    text = self.input_queue.get()
                    if text:
                        ans_request = {"role": "user", "content": text}
                        self.process_chat_request(ans_request)

                # 3. Handle Mic Start/Stop Commands (Auto-restart)
                # Scan the entire list for mic commands, clear old ones
                for event in aivtui.GUI_Conversation_History_list[:]:
                    if isinstance(event, dict):
                        cmd = event.get("ai_ans", "")
                        if cmd == "command:start_mic":
                            aivtui.GUI_Conversation_History_list.remove(event)
                            self.start_mic_recording()
                            break
                        elif cmd == "command:force_stop_mic":
                            aprint("* Mic Forced Stop (Processing) *")
                            mcrc.user_mic_status["mic_on"] = False
                            aivtui.GUI_Conversation_History_list.remove(event)
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def process_chat_request(self, ans_request):
        aprint(f"\n> {self.config['user']['name']}: {ans_request['content']}")
        
        # Send to LLM
        llm_ans_queue = queue.Queue()
        threading.Thread(
            target=aivtui.LLM_Request_thread, 
            args=(ans_request, llm_ans_queue)
        ).start()
        
        # Monitor LLM Answer
        def monitor_llm():
            ans = llm_ans_queue.get()
            if ans:
                aprint(f"♥ {self.config['user']['character']}: {ans}")
                # The subtitles_speak_checker will pick up from GUI_AIVT_Speaking_wait_list if we push there
                aivtui.GUI_AIVT_Speaking_wait_list.append({
                    "chat_role": "user_mic",
                    "chat_now": ans_request["content"],
                    "ai_ans": ans,
                    "ai_name": self.config["user"]["character"]
                })
        
        threading.Thread(target=monitor_llm, daemon=True).start()

    def terminal_input_loop(self):
        while self.running:
            # We use a simple input prompt. 
            # Note: This might overlap with output, but it's the standard CLI approach.
            user_text = input("User Input > ").strip()
            if user_text:
                self.input_queue.put(user_text)

    def start_mic_recording(self):
        # This mirrors the GUI logic to start mic threads
        if mcrc.user_mic_status["mic_on"]:
            return # Already on
            
        aprint("* Mic Opening... *")
        mcrc.user_mic_status["mic_on"] = True
        # Start the recording thread
        threading.Thread(target=mcrc.MC_Record, daemon=True).start()
        # Start the output checker (which calls Whisper)
        threading.Thread(target=mcrc.MC_Output_checker, daemon=True).start()

    def stop(self):
        aprint("\nExiting AIVT Core...")
        self.running = False
        aivtui.GUI_Running = False
        sys.exit(0)

if __name__ == "__main__":
    core = AIVT_Core()
    # Initial start
    core.start_mic_recording()
    core.run()
