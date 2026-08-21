from dotenv import load_dotenv
load_dotenv()

from src.llm_client import ProductionLLMClient

def main():
    client = ProductionLLMClient()
    messages = [{"role": "system", "content": "You are a helpful assistant."}]

    print("Chatbot ready. Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ")
        if user_input.strip().lower() == "quit":
            break
        messages.append({"role": "user", "content": user_input})
        response = client.chat(messages)
        reply = response.choices[0].message.content
        print(f"Assistant: {reply}\n")
        messages.append({"role": "assistant", "content": reply})

    client.report()

if __name__ == "__main__":
    main()