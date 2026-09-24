# src/finetuning/../bedrock_comparison.py  (or a new src/model_serving/ module - your call)

from dotenv import load_dotenv
load_dotenv()

import boto3
import time
from openai import OpenAI

bedrock = boto3.client("bedrock-runtime", region_name="eu-north-1")
openai_client = OpenAI()

def call_openai(prompt):
    start = time.time()
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    elapsed = time.time() - start
    return response.choices[0].message.content, elapsed

def call_bedrock(prompt):
    start = time.time()
    response = bedrock.converse(
        modelId="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}]
    )
    elapsed = time.time() - start
    return response["output"]["message"]["content"][0]["text"], elapsed

if __name__ == "__main__":
    prompt = "In one sentence, what's the difference between RAG and fine-tuning?"

    text, t = call_openai(prompt)
    print(f"OpenAI ({t:.2f}s): {text}\n")

    text, t = call_bedrock(prompt)
    print(f"Bedrock/Claude ({t:.2f}s): {text}")