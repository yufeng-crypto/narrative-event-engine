# -*- coding: utf-8 -*-
"""Test runner for Director/Predictor/Performer APIs"""

import json
import os
import sys
import requests
import re

# Paths
CONFIG_PATH = r"C:\Users\20731\.openclaw\workspace\logic\prototype\config.json"
CHARACTER_FILE = r"C:\Users\20731\.openclaw\workspace\logic\test_logs\2026-02-26\character_palace.json"
OUTPUT_DIR = r"C:\Users\20731\.openclaw\workspace\logic\test_logs\2026-02-26\run_001"

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_character():
    with open(CHARACTER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_prompt(prompt_name):
    prompt_path = os.path.join(r"C:\Users\20731\.openclaw\workspace\logic\roles", f"{prompt_name}.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def call_api(messages, config):
    api_config = config.get('api', {})
    api_key = api_config.get('api_key', '')
    url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": api_config.get('model', 'MiniMax-M2.5'),
        "messages": messages
    }
    
    response = requests.post(url, headers=headers, json=data, timeout=120)
    result = response.json()
    
    if 'choices' in result and len(result['choices']) > 0:
        return result['choices'][0]['message']['content']
    else:
        return f"[API ERROR] {result}"

def call_director(role_content, axes_data, user_message, conversation_history, config):
    director_prompt = load_prompt("director")
    
    if not director_prompt:
        director_prompt = "You are a Narrative Director. Output STORY_PATCH based on conversation history and role settings."

    conv_text = "\n".join([
        f"{'User' if m['role']=='user' else 'NPC'}: {m['content'][:200]}"
        for m in conversation_history[-5:]
    ])
    
    axes_text = f"Axes: Intimacy={axes_data.get('Intimacy', 3)}, Risk={axes_data.get('Risk', 6)}, Info={axes_data.get('Info', 5)}, Action={axes_data.get('Action', 4)}, Rel={axes_data.get('Rel', 2)}, Growth={axes_data.get('Growth', 7)}"

    system_prompt = f"""{director_prompt}

Role:
{role_content[:1500]}

{axes_text}

History:
{conv_text}

User: {user_message}

Generate STORY_PATCH."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Generate STORY_PATCH"}
    ]
    
    return call_api(messages, config)

def call_predictor(role_content, axes_data, user_message, conversation_history, config):
    predictor_prompt = load_prompt("predictor")
    
    if not predictor_prompt:
        predictor_prompt = "You are a narrative prediction engine. Generate event cards based on conversation and axes state."

    conv_text = "\n".join([
        f"{'User' if m['role']=='user' else 'NPC'}: {m['content'][:200]}"
        for m in conversation_history[-5:]
    ])
    
    axes_text = f"Axes: Intimacy={axes_data.get('Intimacy', 3)}, Risk={axes_data.get('Risk', 6)}, Info={axes_data.get('Info', 5)}, Action={axes_data.get('Action', 4)}, Rel={axes_data.get('Rel', 2)}, Growth={axes_data.get('Growth', 7)}"

    system_prompt = f"""{predictor_prompt}

Role:
{role_content[:1500]}

{axes_text}

History:
{conv_text}

User: {user_message}

Generate event cards in JSON format."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Generate event cards"}
    ]
    
    return call_api(messages, config)

def call_performer(role_content, director_output, user_message, conversation_history, config):
    # Extract focus
    focus = ""
    match = re.search(r'focus[:\s]+([^\n]+)', director_output, re.IGNORECASE)
    if match:
        focus = match.group(1).strip()
    
    system_prompt = f"""You are an NPC. Reply according to the role setting:

{role_content}

Director instructions:
{director_output}

Focus: {focus}

Reply to the user as this character."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    return call_api(messages, config)

if __name__ == "__main__":
    print("=" * 60)
    print("Running test scenario...")
    print("=" * 60)
    
    config = load_config()
    character = load_character()
    
    role_content = character.get('content', '')
    role_name = character.get('name', 'Unknown')
    axes_data = character.get('axes', {})
    
    user_input = "姐姐一个人在这冷宫，可还好？"
    conversation_history = []
    
    print(f"\nRole: {role_name}")
    print(f"User: {user_input}")
    print(f"Axes: {axes_data}")
    
    # 1. Director
    print("\n[1/3] Calling Director API...")
    director_output = call_director(role_content, axes_data, user_input, conversation_history, config)
    print(f"Director output: {len(director_output)} chars")
    
    # 2. Predictor
    print("\n[2/3] Calling Predictor API...")
    predictor_output = call_predictor(role_content, axes_data, user_input, conversation_history, config)
    print(f"Predictor output: {len(predictor_output)} chars")
    
    # 3. Performer
    print("\n[3/3] Calling Performer API...")
    performer_output = call_performer(role_content, director_output, user_input, conversation_history, config)
    print(f"Performer output: {len(performer_output)} chars")
    
    # Save results
    print(f"\nSaving to: {OUTPUT_DIR}")
    
    with open(os.path.join(OUTPUT_DIR, "director_output.json"), 'w', encoding='utf-8') as f:
        json.dump({"director_output": director_output}, f, ensure_ascii=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, "predictor_output.json"), 'w', encoding='utf-8') as f:
        json.dump({"predictor_output": predictor_output}, f, ensure_ascii=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, "performer_output.json"), 'w', encoding='utf-8') as f:
        json.dump({"performer_output": performer_output}, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
    
    print("\n[Director Preview]")
    print(director_output[:500] + "..." if len(director_output) > 500 else director_output)
    
    print("\n[Predictor Preview]")
    print(predictor_output[:500] + "..." if len(predictor_output) > 500 else predictor_output)
    
    print("\n[Performer Preview]")
    print(performer_output[:300] + "..." if len(performer_output) > 300 else performer_output)
