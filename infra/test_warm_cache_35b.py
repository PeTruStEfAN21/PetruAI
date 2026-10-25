#!/usr/bin/env python3
"""
PetruAI - Task A4: Warm prompt cache test for Qwen3.6-35B-A3B
1. Sends ~16,000 token prompt to populate cache.
2. Sends the same 16k prompt + 500 new tokens, generating 300 tokens.
3. Records warm prefill time, decode time, and total latency.
"""
import time
import json
import urllib.request

SERVER_URL = "http://127.0.0.1:8080"

def get_16k_context():
    # Read research notes to build ~16,000 tokens
    with open("research_notes/Agent de cod local și antrenare/local_models.md", "r", encoding="utf-8") as f:
        t1 = f.read()
    with open("research_notes/Agent de cod local și antrenare/memory_and_monitoring.md", "r", encoding="utf-8") as f:
        t2 = f.read()
    with open("research_notes/Agent de cod local și antrenare/harnesses.md", "r", encoding="utf-8") as f:
        t3 = f.read()
    
    # Target ~14,500 tokens so 14.5k + 500 + 300 < 16,000 fits within 16k context
    combined = (t1 + "\n\n" + t2 + "\n\n" + t3)[:34000]
    return combined

def count_tokens(text):
    req = urllib.request.Request(
        f"{SERVER_URL}/tokenize",
        data=json.dumps({"content": text}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode())
        return len(d.get("tokens", []))

def run_warm_cache_test():
    base_16k = get_16k_context()
    
    # 500 new tokens (approx 1500 chars of instructions)
    new_500_tokens = (
        "\n\n# SARCINA CURENTA: Integrare si evaluare comparativa\n"
        "Pe baza intregii cercetari de mai sus, realizeaza o analiza detaliata a avantajelor si compromisurilor "
        "intre rularea unui model 9B dens complet in VRAM vs un model 35B MoE cu expert offload in RAM pe un laptop RTX 4050. "
        "Include consideratii despre latenta prefill la cold start vs warm cache, consumul de energie pe baterie, "
        "stabilitatea tool calling-ului in framework-uri de agenti precum OpenCode sau Hermes, "
        "si modul in care memoria proiectului din MEMORY.md poate fi structurata incremental pentru a minimiza "
        "numarul de tokeni recititi la fiecare pas. Argumenteaza cu cifre concrete din cercetare.\n"
    )
    
    print("Pasul 1: Incarcare prompt initial de ~16k tokeni pentru populare cache...")
    payload_step1 = {
        "messages": [
            {"role": "system", "content": "You are PetruAI, an expert local software architect."},
            {"role": "user", "content": base_16k + "\n\nRaspunde cu un singur cuvant: GATA."}
        ],
        "temperature": 0.1,
        "max_tokens": 10
    }
    
    req1 = urllib.request.Request(
        f"{SERVER_URL}/v1/chat/completions",
        data=json.dumps(payload_step1).encode(),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req1, timeout=300) as resp:
        res1 = json.loads(resp.read().decode())
    time_step1 = time.perf_counter() - t0
    
    timings1 = res1.get("timings", {})
    usage1 = res1.get("usage", {})
    prompt_tokens_1 = usage1.get("prompt_tokens", timings1.get("prompt_n", 0))
    print(f"Pasul 1 finalizat: {prompt_tokens_1} tokeni procesati in {time_step1:.2f}s ({timings1.get('prompt_per_second', 0):.1f} tok/s)")
    
    print("\nPasul 2: Trimitere prompt cald (16k cache + ~500 tokeni noi) cu generare 300 tokeni...")
    payload_step2 = {
        "messages": [
            {"role": "system", "content": "You are PetruAI, an expert local software architect."},
            {"role": "user", "content": base_16k + new_500_tokens}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }
    
    req2 = urllib.request.Request(
        f"{SERVER_URL}/v1/chat/completions",
        data=json.dumps(payload_step2).encode(),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req2, timeout=180) as resp:
        res2 = json.loads(resp.read().decode())
    time_step2 = time.perf_counter() - t0
    
    timings2 = res2.get("timings", {})
    usage2 = res2.get("usage", {})
    cached_tokens = timings2.get("cache_n", usage2.get("prompt_tokens_details", {}).get("cached_tokens", 0))
    new_prompt_tokens = timings2.get("prompt_n", 0)
    gen_tokens = usage2.get("completion_tokens", timings2.get("predicted_n", 0))
    
    prefill_warm_ms = timings2.get("prompt_ms", 0)
    decode_ms = timings2.get("predicted_ms", 0)
    decode_tok_s = timings2.get("predicted_per_second", 0)
    
    print("\n" + "="*60)
    print("REZULTATE PAS CALD (PROMPT CACHE 16K) — QWEN3.6-35B")
    print("="*60)
    print(f"Tokeni in cache (reutilizati): {cached_tokens}")
    print(f"Tokeni noi evaluati (delta): {new_prompt_tokens}")
    print(f"Timp evaluare delta: {prefill_warm_ms:.1f} ms ({new_prompt_tokens / (prefill_warm_ms/1000):.1f} tok/s)" if prefill_warm_ms > 0 else f"Timp evaluare delta: {prefill_warm_ms:.1f} ms")
    print(f"Tokeni generati: {gen_tokens}")
    print(f"Timp generare: {decode_ms:.1f} ms ({decode_tok_s:.2f} tok/s)")
    print(f"Timp total wall clock (Pasul 2): {time_step2:.2f} s")
    print("="*60 + "\n")
    
    out_data = {
        "step1_prompt_tokens": prompt_tokens_1,
        "step1_time_s": time_step1,
        "step2_cached_tokens": cached_tokens,
        "step2_delta_tokens": new_prompt_tokens,
        "step2_prefill_ms": prefill_warm_ms,
        "step2_generated_tokens": gen_tokens,
        "step2_decode_ms": decode_ms,
        "step2_decode_tok_s": decode_tok_s,
        "step2_total_wall_s": time_step2
    }
    with open("infra/bench_35b_warm_cache.json", "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    return out_data

if __name__ == "__main__":
    run_warm_cache_test()
