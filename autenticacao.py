import os.path
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# --- RACIOCÍNIO DO CÓDIGO ---
# 1. Definimos o nível de acesso que nosso agente precisa.
#    "readonly" seria apenas para leitura, mas precisamos de "events" para criar eventos.
#    "https://www.googleapis.com/auth/calendar.events" permite leitura e escrita de eventos.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def main():
    creds = None
    # 2. Verificamos se já existe um arquivo "token.json".
    #    Se sim, significa que já fizemos a autenticação e podemos pular para o próximo passo.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # 3. Se não houver credenciais válidas, iniciamos o processo de autenticação.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Se o token expirou, ele tenta atualizá-lo automaticamente.
            creds.refresh(Request())
        else:
            # Este é o fluxo de autenticação inicial.
            # Ele lê o arquivo 'credentials.json', abre uma janela do navegador,
            # pede sua permissão e, se concedida, salva o token em um arquivo chamado 'token.json'.
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Salva o token para uso futuro
        with open("token.json", "w") as token:
            token.write(creds.to_json())

if __name__ == "__main__":
    main()