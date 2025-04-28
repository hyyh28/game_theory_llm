# utils.py
import time

def parse(message):
    assert '<s>' in message and '</s>' in message
    start = message.index('<s>') + len('<s>')
    end = message.index('</s>')
    return message[start:end].strip()

def parse_action(message, choices):
    action = parse(message)
    assert action in choices, f"Invalid action: {action}"
    return action

def safe_call_api(call_func, model, prompt, system_prompt, retry_times=3, sleep_time=0.5):
    for attempt in range(retry_times):
        try:
            return call_func(model, prompt, system_prompt)
        except Exception as e:
            print(f"API call failed: {e}. Retry {attempt + 1}/{retry_times}")
            time.sleep(sleep_time)
    raise RuntimeError("API call failed after retries.")

def generate_chain_of_thought(agent_name, role, actions, previous_messages=None):
    cot = f"### {agent_name}'s Thought Process\n"
    cot += f"As a {role} agent, I need to carefully consider my strategy.\n"
    if previous_messages:
        cot += f"Reviewing previous negotiation messages, I assess the trustworthiness and intentions of my counterpart.\n"
    cot += f"My available actions are: {', '.join(actions)}.\n"
    cot += "I should choose an action that maximizes my long-term benefit, considering possible cooperation or betrayal by the other player.\n"
    cot += "I also need to think about offering a reward share to facilitate cooperation if needed.\n"
    return cot
