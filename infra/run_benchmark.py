#!/usr/bin/env python3
"""
PetruAI Benchmark Script
Measures prefill (prompt processing) and decode (generation) tok/s on ~4,000 token prompt,
and verifies valid tool call output with --jinja.
"""
import time
import json
import urllib.request
import urllib.error

SERVER_URL = "http://127.0.0.1:8080"

# Sample 4k context: realistic coding agent context
# PetruAI system prompt + tools + architecture documentation
SYSTEM_PROMPT = """You are PetruAI, an expert autonomous local coding CLI agent running entirely on the user's machine.
You follow strict behavioral guidelines:
1. Always ask clarifying design questions before generating or modifying code if requirements are ambiguous.
2. Respect user architecture decisions without arguing.
3. Be concise and precise.
4. When tools are available, call them directly to inspect, read, or modify files or run environment commands.
5. Provide high quality, idiomatic code across multiple languages including Dart, Flutter, Python, TypeScript, and Rust.
"""

def generate_context():
    # Read research notes or documentation to build an exact ~4,000 token context
    with open("docs/HANDOFF.md", "r", encoding="utf-8") as f:
        handoff = f.read()
    with open("research_notes/Agent de cod local și antrenare/memory_and_monitoring.md", "r", encoding="utf-8") as f:
        memory_notes = f.read()
    
    # Target ~4,000 tokens total prompt
    context = (
        f"# Project Handoff Context\n{handoff}\n\n"
        f"# Architecture & Memory Research\n{memory_notes[:7000]}"
    )
    return context

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Inspect the git status of the working tree, returning untracked, modified, and staged files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "verbose": {
                        "type": "boolean",
                        "description": "Include detailed branch and diff information"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to read"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a terminal shell command and return its exit code, stdout, and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

def check_health():
    try:
        req = urllib.request.Request(f"{SERVER_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False

def count_tokens(text):
    try:
        req = urllib.request.Request(
            f"{SERVER_URL}/tokenize",
            data=json.dumps({"content": text}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return len(data.get("tokens", []))
    except Exception as e:
        print(f"Tokenize endpoint error: {e}")
        return None

import subprocess

def get_gpu_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True
        ).strip()
        used, total = [int(x.strip()) for x in out.split(",")]
        return used, total
    except Exception:
        return None, None

def run_benchmark():
    context = generate_context()
    user_prompt = "Verifică starea depozitului git (git status) pentru a vedea ce modificări există în proiect."
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context},
        {"role": "user", "content": user_prompt}
    ]
    
    payload = {
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 256
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
    total_wall_time = time.perf_counter() - t0
    
    result = json.loads(raw)
    result["_total_wall_time"] = total_wall_time
    
    vram_used, vram_total = get_gpu_vram()
    result["_vram_used_mb"] = vram_used
    result["_vram_total_mb"] = vram_total
    return result

if __name__ == "__main__":
    if not check_health():
        print("ERROR: Server is not running on", SERVER_URL)
        exit(1)
    print("Server healthy. Running benchmark on ~4k prompt...")
    res = run_benchmark()
    
    timings = res.get("timings", {})
    usage = res.get("usage", {})
    choice = res.get("choices", [{}])[0]
    msg = choice.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    
    prompt_tokens = usage.get("prompt_tokens", timings.get("prompt_n"))
    completion_tokens = usage.get("completion_tokens", timings.get("predicted_n"))
    
    prefill_tok_s = timings.get("prompt_per_second")
    prefill_ms = timings.get("prompt_ms")
    decode_tok_s = timings.get("predicted_per_second")
    decode_ms = timings.get("predicted_ms")
    
    vram_str = f"{res.get('_vram_used_mb')} / {res.get('_vram_total_mb')} MB" if res.get('_vram_used_mb') else "N/A"
    
    print("\n" + "="*60)
    print("BENCHMARK RESULTS")
    print("="*60)
    print(f"Model: {res.get('model')}")
    print(f"Prompt Tokens: {prompt_tokens}")
    print(f"Completion Tokens: {completion_tokens}")
    print(f"Prefill (Prompt Processing): {prefill_tok_s:.2f} tok/s ({prefill_ms:.1f} ms)" if prefill_tok_s else "Prefill: N/A")
    print(f"Decode (Generation): {decode_tok_s:.2f} tok/s ({decode_ms:.1f} ms)" if decode_tok_s else "Decode: N/A")
    print(f"Total Wall Clock Time: {res.get('_total_wall_time'):.2f} s")
    print(f"VRAM Used: {vram_str}")
    print(f"Finish Reason: {choice.get('finish_reason')}")
    print(f"Tool Calls Count: {len(tool_calls)}")
    if tool_calls:
        tc = tool_calls[0]
        func = tc.get("function", {})
        print(f"  Tool Name: {func.get('name')}")
        print(f"  Arguments: {func.get('arguments')}")
        try:
            parsed_args = json.loads(func.get("arguments", "{}"))
            print(f"  Arguments Valid JSON: YES ({parsed_args})")
        except Exception:
            print("  Arguments Valid JSON: NO")
    # Save to a temp json file for reporting FIRST
    with open("infra/last_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    reasoning = msg.get('reasoning_content', '').strip()[:200].encode('ascii', errors='replace').decode('ascii')
    print(f"Reasoning / Thought: {reasoning}")
    print("="*60 + "\n")
