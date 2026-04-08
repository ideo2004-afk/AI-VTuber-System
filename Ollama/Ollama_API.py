import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import threading
import time
import queue
import ollama

import AIVT_Config
from My_Tools.AIVT_print import aprint

ollama_parameters = {
    "model": "llama3",
    "base_url": "http://localhost:11434",
    "max_output_tokens" : 512,
    "temperature" : 0.8,
    "timeout" : 60,
    "retry" : 3,
}

def run_with_timeout_Ollama_API(
        conversation,
        chatQ,
        model_name="llama3",
        base_url="http://localhost:11434",
        max_output_tokens=512,
        temperature=0.8,
        timeout=120,
        retry=3,
        command=None,
    ):

    start_time = time.time()
    ans = queue.Queue()

    # Pre-check if Ollama is responsive (with 5s timeout)
    try:
        from ollama import Client
        check_client = Client(host=base_url, timeout=5.0)
        check_client.list()
    except Exception as e:
        aprint(f"! Ollama Warning: Server at {base_url} not responding within 5s: {e}")

    Ot = threading.Thread(
        target=Ollama_API_thread,
        args=(conversation, ans, ),
        kwargs={
            "model_name":model_name,
            "base_url":base_url,
            "max_output_tokens":max_output_tokens,
            "temperature":temperature,
            "retry":retry,
            "timeout":timeout,
            "command":command,
            },
        )

    Ot.start()
    Ot.join(timeout)

    if Ot.is_alive():
        aprint(f"! Ollama API Timeout after {timeout}s!")
        return None

    else:
        end_time = time.time()
        llm_result = ans.get()

        if llm_result:
            cleaned_llm_result = "\n".join(line.strip() for line in llm_result.splitlines() if line.strip())
            return cleaned_llm_result
        return ""

def Ollama_API_thread(
        conversation,
        ans,
        model_name = "llama3",
        base_url = "http://localhost:11434",
        max_output_tokens = 512,
        temperature = 0.8,
        retry = 3,
        timeout = 120,
        command = None,
        ):
    
    # Initialize client with timeout to ensure the thread can exit on failure
    client = ollama.Client(host=base_url, timeout=float(timeout))

    reT = 0
    while reT < retry:
        reT += 1
        try:
            if command != "no_print" and reT > 1:
                aprint(f"! Ollama retry {reT}/{retry}...")
            response = client.chat(
                model=model_name,
                messages=conversation,
                options={
                    "temperature": temperature,
                    "num_predict": max_output_tokens,
                    "stop": ["<|file_separator|>", "<|end_of_turn|>", "<|start_of_turn|>", "</start_of_turn>", "<end_of_turn>", "</end_of_turn>"]
                }
            )
            
            if 'message' in response and 'content' in response['message']:
                ans.put(response['message']['content'])
                return
            else:
                aprint(f"! Ollama response error: {response}")
                ans.put("")
                return

        except Exception as e:
            if reT < retry:
                aprint(f"! Ollama retry {reT}/{retry} failed: {e}")
                time.sleep(1)
                continue
            else:
                aprint(f"! Ollama failed after {retry} retries: {e}")
                ans.put("")
                return

def get_available_models(base_url="http://localhost:11434"):
    try:
        client = ollama.Client(host=base_url)
        response = client.list()
        models = []
        if hasattr(response, 'models'):
            for m in response.models:
                if hasattr(m, 'model'):
                    models.append(m.model)
                elif isinstance(m, dict) and 'name' in m:
                    models.append(m['name'])
                else:
                    models.append(str(m).split(" ")[0].replace("model='", "").replace("'", ""))
        elif isinstance(response, dict) and 'models' in response:
            for m in response['models']:
                models.append(m.get('name') if isinstance(m, dict) else str(m))
        return models
    except Exception as e:
        print(f"Error fetching Ollama models: {e}")
        return []
