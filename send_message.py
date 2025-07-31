import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

if not webhook_url:
    print("Erro: A variável de ambiente DISCORD_WEBHOOK_URL não foi definida.")
    exit() 

data = {
    "content": "Isso aqui está funcionando?"
}

response = requests.post(
    webhook_url,
    data=json.dumps(data),
    headers={"Content-Type": "application/json"}
)

if response.status_code == 204:
    print("Mensagem enviada com sucesso!")
else:
    print(f"Falha ao enviar mensagem. Status: {response.status_code}")
