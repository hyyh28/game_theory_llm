import anthropic
import time
from openai import OpenAI

####### data generation close-source models #######
claude_key =  None
open_ai_key = None
deepseek_key = "sk-30d3ca4f89664ab3af676bb640a5f7bc"

def call_api(model, message, system_prompt):
    if 'sonnet' in model:
        api_client = anthropic.Anthropic(
                api_key=claude_key,
            )
        system_prompt = system_prompt
        message = api_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=2000,
            temperature=1.0,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        return message.content[0].text
    elif 'opus' in model:
        api_client = anthropic.Anthropic(
                api_key=claude_key,
            )
        system_prompt = system_prompt
        message = api_client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=2000,
            temperature=1.0,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        return message.content[0].text
    elif 'gpt-4o' in model:
        openai_client = OpenAI(api_key=open_ai_key)
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=1.0,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    elif 'gpt-4o-mini' in model:
        openai_client = OpenAI(api_key=open_ai_key)
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=1.0,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    elif 'o1' in model:
        openai_client = OpenAI(api_key=open_ai_key)
        response = openai_client.chat.completions.create(
            model = "o1-preview", 
            messages=[
                {"role": "user", "content": message},
            ]
            )
        return response.choices[0].message.content
    elif 'sonnet3' in model:
        openai_client = OpenAI(api_key=open_ai_key)
        response = openai_client.chat.completions.create(
            model = "claude-3-sonnet-20240229", 
            messages=[
                {"role": "user", "content": message},
            ],
            temperature=1.0,
            )
        return response.choices[0].message.content
    elif 'deepseek' in model:
        openai_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com/v1")
        response = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            max_tokens=1000,
        )
        return response.choices[0].message.content



def call_anthropic_api(message, system_prompt):
    api_client = anthropic.Anthropic(
        api_key=claude_key,
    )
    system_prompt = system_prompt
    message = api_client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=3000,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
    return message.content[0].text


def call_gpt4_api(message, system_prompt):
    openai_client = OpenAI(api_key=open_ai_key)
    response = openai_client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=1000,
    )
    return response.choices[0].message.content


def call_gpt35_api(message, system_prompt):
    openai_client = OpenAI(api_key=open_ai_key)
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=1000,
    )
    return response.choices[0].message.content

def call_deepseek_api(message, system_prompt):
    openai_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
    response = openai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=1000,
    )
    return response.choices[0].message.content



def close_source_call(model, message, system_prompt):
    if model == "claude":
        result = call_anthropic_api(message, system_prompt)
    elif model == "gpt4":
        result = call_gpt4_api(message, system_prompt)
    elif model == "gemini":
        result = call_gpt35_api(message, system_prompt)
    elif model == "deepseek":
        result = call_deepseek_api(message, system_prompt)
    return result

