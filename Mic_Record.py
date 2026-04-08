import time
import threading
import pyaudio
import wave
import audioop

import keyboard

import AI_Vtuber_UI as aivtui
from My_Tools.AIVT_print import aprint










user_mic_status = {
    "mic_on": False,
    "mic_record_running": False,
    "mic_checker_running": False,
    "mic_hotkeys_using": False,
    "mic_hotkey_1_detecting": False,
    "mic_hotkey_1_using": False,
    "mic_hotkey_1": "`",
    "mic_hotkey_2_detecting": False,
    "mic_hotkey_2_using": False,
    "mic_hotkey_2": "caps lock",
}

User_Mic_parameters = {
    "user_mic_audio_path": "Audio/user_mic_record/input_user_mic.wav",
    "input_device_name": "",
    "channels": 1,
    "format": pyaudio.paInt16,
    "rate": 24000,
    "chunk": 1024,
    "minimum_duration": 1,
    "energy_threshold": 500,
    "silence_duration_threshold": 2.0,
}

Audio_frames_out = []
Mic_hotkey_pressed = False

from shared_pyaudio import get_pyaudio

def MC_Record():
    global user_mic_status, User_Mic_parameters, Mic_hotkey_pressed, Audio_frames_out

    # IMPORTANT: Clear leftover audio frames from previous session to prevent instant Whisper triggers
    Audio_frames_out.clear()

    input_device_index = Get_available_input_devices_ID(User_Mic_parameters["input_device_name"])
    CHUNK = User_Mic_parameters["chunk"]

    p = get_pyaudio()
    try:
        audio_stream = p.open(
                input=True,
                input_device_index=input_device_index,
                channels=User_Mic_parameters["channels"],
                format=User_Mic_parameters["format"],
                rate=User_Mic_parameters["rate"],
                frames_per_buffer=CHUNK,
            )
    except OSError as e:
        aprint(f"!!! Error opening audio stream: {e} !!!")
        print(f"[DEBUG] OSError details: {e}")
        if e.errno == -9996:
            aprint("!!! No default input/output device found or access denied (macOS). !!!")
            aprint("!!! Please ensure the terminal/app has Microphone permissions or select a device manually in 'Setting' tab. !!!")
        user_mic_status["mic_on"] = False
        user_mic_status["mic_record_running"] = False
        return

    import platform
    if platform.system() == "Darwin":
        user_mic_status["mic_hotkeys_using"] = False

    Mic_hotkey_pressed = False
    
    dmhp = threading.Thread(target=Detect_Mic_hotkey_pressed)
    dmhp.start()

    while user_mic_status["mic_on"]:
        # Safety Guard: Never record while AI is speaking
        if aivtui.speaking_continue_count > 0:
            time.sleep(0.5)
            continue
            
        should_record = Mic_hotkey_pressed or (not user_mic_status.get("mic_hotkeys_using", False))
        if should_record:
            frames = []
            start_time = time.time()
            current_time = start_time
            last_spoken_time = start_time
            has_spoken = False
            
            while user_mic_status["mic_on"] and (Mic_hotkey_pressed or (not user_mic_status.get("mic_hotkeys_using", False))):
                data = audio_stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                current_time = time.time()

                # VAD calculation
                rms = audioop.rms(data, p.get_sample_size(User_Mic_parameters["format"]))
                if rms > User_Mic_parameters["energy_threshold"]:
                    last_spoken_time = current_time
                    has_spoken = True
                
                # Check silence duration
                if has_spoken and (current_time - last_spoken_time) > User_Mic_parameters["silence_duration_threshold"]:
                    user_mic_status["mic_on"] = False  # Immediately break loop directly
                    aprint("* Voice Detected, processing... *")
                    aivtui.GUI_Conversation_History_list.append({"chat_role": "system", "chat_now": "", "ai_name": "System", "ai_ans": "command:force_stop_mic"})
                    break

            if current_time - start_time >= User_Mic_parameters["minimum_duration"]:
                Audio_frames_out.append(frames)
                aprint("* Voice Detected *")
                # print(f"[DEBUG] Recorded frames length: {len(frames)}")
            else:
                aprint("*** Mic Record Cancel ***")
                print(f"[DEBUG] Record canceled, duration too short: {current_time - start_time}")
            
            # # print("[DEBUG] Inner while loop executed properly.")
            
        # a# print("[DEBUG] Outer loop tick")
        time.sleep(0.1)

    # print("[DEBUG] Exited outer loop. Setting mic_record_running to False.")
    user_mic_status["mic_record_running"] = False
    
    try:
        if audio_stream.is_active():
            audio_stream.stop_stream()
        audio_stream.close()
        # print("[DEBUG] audio_stream closed successfully.")
    except Exception as e:
        print(f"[DEBUG] Error closing audio_stream: {e}")

    aprint("* User Mic OFF *")


def Detect_Mic_hotkey_pressed():
    global user_mic_status, Mic_hotkey_pressed
    # Hotkeys disabled on macOS without sudo
    print("* User Mic ON * (Hotkeys disabled on macOS without sudo)")
    user_mic_status["mic_record_running"] = True
    while user_mic_status["mic_on"]:
        time.sleep(0.1)
    Mic_hotkey_pressed = False
    import platform
    if platform.system() != "Darwin":
        try:
            keyboard.unhook_all()
        except:
            pass


def MC_Output_checker():
    global user_mic_status, Audio_frames_out
    # print("[DEBUG] MC_Output_checker started.")
    user_mic_status["mic_checker_running"] = True
    while user_mic_status["mic_on"]:
        if Audio_frames_out:
            # aprint("* output check *")
            # print("[DEBUG] Popping frames and sending to thread.")
            mco = threading.Thread(target=aivtui.OpenAI_Whisper_thread, args=(Audio_frames_out.pop(0), ))
            mco.start()
        time.sleep(0.1)
    
    # print("[DEBUG] checker waiting for mic_record_running to stop.")
    while user_mic_status["mic_record_running"]:
        time.sleep(0.1)
    
    # print("[DEBUG] checker finalizing remaining frames.")
    if Audio_frames_out:
        # aprint("* output check *")
        # print("[DEBUG] Processing last frames...")
        mco = threading.Thread(target=aivtui.OpenAI_Whisper_thread, args=(Audio_frames_out.pop(0), ))
        mco.start()
        mco.join()
        # print("[DEBUG] Last frames processing joined.")
        
    user_mic_status["mic_checker_running"] = False
    # # print("[DEBUG] MC_Output_checker ended.")


import os
def save_audio2wav(audio_frames, save_path):
    global User_Mic_parameters
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    p = get_pyaudio()
    wf = wave.open(save_path, 'wb')
    wf.setnchannels(User_Mic_parameters["channels"])
    wf.setsampwidth(p.get_sample_size(User_Mic_parameters["format"]))
    wf.setframerate(User_Mic_parameters["rate"])
    wf.writeframes(b''.join(audio_frames))
    wf.close()


def Get_key_press():
    print("User Mic Hotkey Detecting(Press ESC to cancel)...")
    event = keyboard.read_event()
    if event.event_type == keyboard.KEY_DOWN:
        key_name = event.name
        if not key_name == "esc":
            print(f"Detected Key: {key_name}")
        else:
            print("User Mic Hotkey Cancel")
        return key_name


def Available_Input_Device():
    p = get_pyaudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            print(f"Input Device id {i} - {p.get_device_info_by_host_api_device_index(0, i).get('name')}")


def Get_available_input_devices_List():
    p = get_pyaudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    input_devices_list = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            input_devices_list.append(p.get_device_info_by_host_api_device_index(0, i).get('name'))
    return input_devices_list


def Get_available_input_devices_ID(devices_name):
    if not devices_name or devices_name.strip() == "":
        return None # PyAudio uses the system default in this case
    p = get_pyaudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            if devices_name == p.get_device_info_by_host_api_device_index(0, i).get('name'):
                return i
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            return i
    return None










if __name__ == "__main__":
    Available_Input_Device()
    devices_id = Get_available_input_devices_ID("Never gonna make you cry never gonna say goodbye")
    print(f"Devices ID: {devices_id}")
    #Get_key_press()


