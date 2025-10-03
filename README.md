# 🤖 Agente Inteligente de Calendar (Telegram + Gemini + Google Calendar)

Este projeto implementa um **Agente de Telegram** em Python. Ele utiliza o modelo **Gemini** para processar a linguagem natural e extrair a intenção do usuário (agendar ou consultar), e interage com o **Google Calendar API** para gerenciar eventos de forma inteligente.

---

## ✨ Funcionalidades Principais

* **Agendamento Inteligente:** Cria eventos no Google Calendar a partir de comandos em linguagem natural (ex: "agende minha reunião amanhã às 15h").
* **Verificação de Disponibilidade:** Checa se o horário solicitado está livre. Se estiver ocupado, sugere horários alternativos automaticamente (fluxo multi-turno).
* **Consulta por Palavra-Chave:** Busca os próximos eventos futuros no seu calendário por um termo específico (ex: "o que tenho de almoço agendado?").
* **Estabilidade da API:** Implementa a formatação estrita de data ISO (`YYYY-MM-DDTHH:MM:SSZ`) para evitar o erro `HttpError 400` da API do Google Calendar.

---

## 🚀 Primeiros Passos (Setup)

Siga estas etapas para clonar e colocar o agente em funcionamento:

### 1. Clonagem e Ambiente Virtual

1.  **Clone o repositório:**
    ```bash
    git clone [URL_DO_SEU_REPOSITORIO]
    cd [pasta_do_projeto]
    ```

2.  **Crie e ative o ambiente virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS/WSL
    # ou .\venv\Scripts\activate  # Windows PowerShell
    ```

3.  **Instale as dependências:**
    O projeto requer as seguintes bibliotecas. Crie um arquivo `requirements.txt` se ele ainda não existir.

    ```bash
    pip install -r requirements.txt
    ```
    *(Conteúdo esperado do `requirements.txt`: `python-telegram-bot`, `python-dotenv`, `google-genai`, `google-auth-oauthlib`, `google-api-python-client`, `pytz`)*

### 2. Configuração de Credenciais

O agente precisa de chaves de API para o Telegram, o Gemini e o Google Calendar.

#### a) Arquivo `.env`

Crie um arquivo chamado **`.env`** na raiz do projeto, preenchendo com suas chaves:

```ini
# .env file

# Token fornecido pelo BotFather no Telegram
TOKEN_TELEGRAM="SEU_TOKEN_DO_BOT_TELEGRAM"

# Sua chave de API do Google Gemini
GEMINI_API_KEY="SUA_CHAVE_API_DO_GEMINI"
```

#### b) Google Calendar API (OAuth)

1. Acesse o Google Cloud Console e habilite a Google Calendar API para seu projeto.

2. Crie uma credencial do tipo OAuth 2.0 Client ID.

    - Selecione o tipo Aplicativo de computador (`Desktop app`).

3. Baixe o arquivo JSON gerado e renomeie-o para `credentials.json`. Este arquivo deve estar na raiz do projeto.

### 3. Execução
Execute o script principal:

```bash
python agente.py
```
Na primeira execução, o processo de autenticação do Google (OAuth Flow) será iniciado. Você precisará clicar no link fornecido no terminal para autorizar o acesso à sua conta Google.

- Após a autorização, um arquivo token.json será gerado na raiz do projeto.
- O agente começará a rodar e estará pronto para responder no Telegram.

## 💡 Como Interagir

Com o agente online, encontre seu bot no Telegram e use comandos em linguagem natural:

| Intenção | Exemplo de Comando |
| :--- | :--- |
| **Agendamento** | `agende meu café com a equipe na terça às 10:30` |
| **Verificação** | `verifique se estou livre amanhã 14h` |
| **Consulta** | `o que tenho agendado sobre "Projeto Alfa"` |
| **Comando Inicial** | `/start` |