import requests

BASE = "http://127.0.0.1:5000/"

response = requests.get(BASE + "llm", data = {"prompt": "USER:\nTell me a funny joke please.\n\nASSISTANT:\n"})

print(response.json())