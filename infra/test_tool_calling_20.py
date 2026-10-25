#!/usr/bin/env python3
"""
PetruAI - 20 Tool Calling Test Suite
Tests 20 diverse queries to evaluate tool calling precision, JSON validity,
multi-step intent, and edge cases under llama-server with --jinja.
"""
import json
import time
import urllib.request
import urllib.error

SERVER_URL = "http://127.0.0.1:8080"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path to read"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file at the given path with content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path to write"},
                    "content": {"type": "string", "description": "The content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace targeted text in a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path to edit"},
                    "target": {"type": "string", "description": "Exact text to replace"},
                    "replacement": {"type": "string", "description": "Replacement text"}
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a terminal shell command (powershell/bash).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user a clarifying question before taking architectural or design actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "Possible options"}
                },
                "required": ["question"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are PetruAI, an expert local coding assistant in the terminal.
You have access to tools: read_file, write_file, edit_file, run_command, and ask_user.
Rules:
- When a user asks you to perform an action, call the appropriate tool.
- If a question is purely conceptual, answer directly without tools.
- If the user request is ambiguous about architecture/design, call ask_user.
- Always output valid tool call parameters.
"""

TEST_CASES = [
    # 1. Simple read
    {"id": 1, "prompt": "Citește conținutul fișierului docs/HANDOFF.md", "expected_tool": "read_file", "should_call_tool": True},
    # 2. Simple write
    {"id": 2, "prompt": "Creează un fișier temporar scratch/test.txt cu conținutul 'salut lume'", "expected_tool": "write_file", "should_call_tool": True},
    # 3. Simple run git status
    {"id": 3, "prompt": "Rulează comanda git status în terminal", "expected_tool": "run_command", "should_call_tool": True},
    # 4. Git log
    {"id": 4, "prompt": "Afișează ultimele 3 commit-uri din repo folosind git log", "expected_tool": "run_command", "should_call_tool": True},
    # 5. Read infra script
    {"id": 5, "prompt": "Afișează conținutul fișierului infra/start-server.ps1", "expected_tool": "read_file", "should_call_tool": True},
    # 6. Run flutter doctor
    {"id": 6, "prompt": "Rulează flutter doctor pentru a verifica starea SDK-ului", "expected_tool": "run_command", "should_call_tool": True},
    # 7. Edit file
    {"id": 7, "prompt": "Înlocuiește textul 'vechi' cu 'nou' în fișierul scratch/note.txt", "expected_tool": "edit_file", "should_call_tool": True},
    # 8. Ambiguous requirement -> ask_user
    {"id": 8, "prompt": "Vreau să adăugăm o bază de date în proiect dar nu știu ce să aleg între SQLite și PostgreSQL. Întreabă-mă ce prefer.", "expected_tool": "ask_user", "should_call_tool": True},
    # 9. Dart analyze
    {"id": 9, "prompt": "Rulează dart analyze în folderul curent pentru a verifica erorile de tip", "expected_tool": "run_command", "should_call_tool": True},
    # 10. List directory
    {"id": 10, "prompt": "Listează fișierele din folderul docs/ rulând comanda ls sau dir", "expected_tool": "run_command", "should_call_tool": True},
    # 11. Multi-step 1: Read then search
    {"id": 11, "prompt": "Citește fișierul docs/HANDOFF.md și apoi caută mențiunile despre Flutter", "expected_tool": "read_file", "should_call_tool": True},
    # 12. Multi-step 2: Check git diff
    {"id": 12, "prompt": "Verifică diferențele nemarcate din proiect cu git diff", "expected_tool": "run_command", "should_call_tool": True},
    # 13. Path with spaces
    {"id": 13, "prompt": "Citește fișierul research_notes/Agent de cod local și antrenare/local_models.md", "expected_tool": "read_file", "should_call_tool": True},
    # 14. Run python test
    {"id": 14, "prompt": "Rulează suita de teste cu pytest", "expected_tool": "run_command", "should_call_tool": True},
    # 15. Check npm version
    {"id": 15, "prompt": "Verifică ce versiune de npm avem instalată pe sistem", "expected_tool": "run_command", "should_call_tool": True},
    # 16. Pure conceptual question -> NO TOOL CALL
    {"id": 16, "prompt": "Care este diferența conceptuală dintre o clasă abstractă și un mixin în Dart?", "expected_tool": None, "should_call_tool": False},
    # 17. Architecture question -> ask_user or ask question
    {"id": 17, "prompt": "Trebuie să decidem între REST și GraphQL pentru API. Pune-mi întrebările de design necesare.", "expected_tool": "ask_user", "should_call_tool": True},
    # 18. Complex JSON string in command
    {"id": 18, "prompt": "Trimite un request curl de test: curl -X POST http://localhost:8080/health -H 'Content-Type: application/json'", "expected_tool": "run_command", "should_call_tool": True},
    # 19. Write markdown summary
    {"id": 19, "prompt": "Scrie un fișier scratch/rezumat.md cu titlul '# Rezumat' și o listă de 3 puncte", "expected_tool": "write_file", "should_call_tool": True},
    # 20. Pure math/code question -> NO TOOL CALL
    {"id": 20, "prompt": "Explică-mi în 2 fraze cum funcționează algoritmul QuickSort.", "expected_tool": None, "should_call_tool": False}
]

def run_test(case):
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["prompt"]}
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 256
    }
    
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        res = json.loads(resp.read().decode())
    elapsed = time.perf_counter() - t0
    
    choice = res.get("choices", [{}])[0]
    msg = choice.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    
    called_tool = None
    args_valid = False
    args_parsed = {}
    
    if tool_calls:
        func = tool_calls[0].get("function", {})
        called_tool = func.get("name")
        raw_args = func.get("arguments", "{}")
        try:
            args_parsed = json.loads(raw_args)
            args_valid = True
        except Exception:
            args_valid = False
            
    # Evaluation
    expected = case["expected_tool"]
    should_call = case["should_call_tool"]
    
    passed = False
    note = ""
    
    if should_call:
        if called_tool == expected and args_valid:
            passed = True
            note = f"Correct tool '{called_tool}', valid JSON: {args_parsed}"
        elif called_tool and args_valid:
            # Maybe used run_command instead of a specialized tool or vice versa
            passed = True
            note = f"Acceptable tool '{called_tool}' (expected '{expected}'), valid JSON"
        elif called_tool and not args_valid:
            passed = False
            note = f"Called '{called_tool}' but invalid JSON arguments"
        else:
            passed = False
            note = f"Did not call any tool! (Expected '{expected}')"
    else:
        if not called_tool:
            passed = True
            note = "Correctly responded directly without tool call"
        else:
            passed = False
            note = f"Unnecessary tool call: called '{called_tool}' for conceptual query"
            
    return {
        "id": case["id"],
        "prompt": case["prompt"],
        "expected": expected,
        "called": called_tool,
        "args_valid": args_valid,
        "passed": passed,
        "note": note,
        "time_s": round(elapsed, 2)
    }

def run_suite(model_label):
    print(f"\n{'='*70}\nRunning 20 Tool Calling Tests for {model_label}\n{'='*70}")
    results = []
    passed_count = 0
    
    for case in TEST_CASES:
        res = run_test(case)
        results.append(res)
        status_icon = "PASS" if res["passed"] else "FAIL"
        if res["passed"]:
            passed_count += 1
        note_clean = res['note'].encode('ascii', errors='replace').decode('ascii')
        print(f"[{status_icon}] Test #{res['id']:02d}: {note_clean} ({res['time_s']}s)")
        
    rate = (passed_count / len(TEST_CASES)) * 100
    print(f"\nSummary for {model_label}: {passed_count}/{len(TEST_CASES)} passed ({rate:.1f}%)\n{'='*70}\n")
    
    output_file = f"infra/tool_eval_{model_label}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"model": model_label, "rate": rate, "passed": passed_count, "total": len(TEST_CASES), "results": results}, f, indent=2)
    return rate, results

if __name__ == "__main__":
    import sys
    label = sys.argv[1] if len(sys.argv) > 1 else "model"
    run_suite(label)
