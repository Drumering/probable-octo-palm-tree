# Importações de Bibliotecas
import os
import datetime
import logging
import pytz
import unicodedata
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- Configuração Global ---
# Escopo necessário para acesso de escrita e leitura de eventos
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIMEZONE_BRAZIL = 'America/Sao_Paulo'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Funções Auxiliares ---

def normalize_keyword(keyword: str) -> str:
    """
    Converte a palavra-chave para um formato ASCII limpo, removendo acentos e
    convertendo para minúsculas, para garantir compatibilidade com a busca 'q' da API.
    """
    # Normaliza para NFD (separa caractere base de acento), remove diacríticos (acentos),
    # decodifica para string e converte para minúsculas.
    keyword_ascii = unicodedata.normalize('NFD', keyword).encode('ascii', 'ignore').decode("utf-8").lower()
    return keyword_ascii

def get_calendar_service():
    """
    Autentica e obtém o objeto de serviço da API do Google Calendar (v3).
    Gerencia o carregamento, refresh e salvamento do arquivo 'token.json'.

    Retorna:
        Objeto googleapiclient.discovery.Resource para interagir com a API.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # Se o token estiver expirado e houver um refresh token, tenta renovar.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Caso contrário, inicia o fluxo de autenticação via navegador.
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Salva as credenciais atualizadas no arquivo.
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def format_datetime_for_query(dt_object: datetime.datetime) -> str:
    """
    Formata um objeto datetime em UTC para o formato ISO 8601 estrito ('YYYY-MM-DDTHH:MM:SSZ').
    Este formato é o mais estável para os parâmetros timeMin/timeMax da API.
    """
    dt_truncated = dt_object.replace(microsecond=0)
    # Garante o formato 'Z' (Zulu Time/UTC) sem o offset '+00:00' que causa o 400 Bad Request.
    return dt_truncated.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

# --- Funções de Ferramentas (Tools) do Agente ---

def verificar_disponibilidade(start_time_iso: str, end_time_iso: str) -> bool:
    """
    Verifica se o calendário primário está livre no intervalo especificado.

    Args:
        start_time_iso: Início do intervalo no formato ISO 8601 com fuso horário.
        end_time_iso: Fim do intervalo no formato ISO 8601 com fuso horário.

    Retorna:
        True se estiver livre, False se estiver ocupado (eventos encontrados).
    """
    service = get_calendar_service()
    
    # A consulta de eventos usa 'singleEvents=True' e 'orderBy' para ser mais robusta.
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_time_iso,
        timeMax=end_time_iso,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    # Se encontrou eventos, o horário está ocupado
    return not events

def criar_evento(summary: str, start_time_iso: str, end_time_iso: str) -> str:
    """
    Cria um novo evento de 1 hora no calendário principal.

    Args:
        summary: Título do evento.
        start_time_iso: Início do evento no formato ISO 8601 com fuso horário.
        end_time_iso: Fim do evento no formato ISO 8601 com fuso horário.

    Retorna:
        O link HTML para o evento no Google Calendar.
    """
    service = get_calendar_service()
    
    event = {
        'summary': summary,
        'start': {
            'dateTime': start_time_iso,
            'timeZone': TIMEZONE_BRAZIL,
        },
        'end': {
            'dateTime': end_time_iso,
            'timeZone': TIMEZONE_BRAZIL,
        },
    }
    
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event.get('htmlLink')

def sugerir_horarios(start_time_iso: str, end_time_iso: str) -> list[str]:
    """
    Sugere horários subsequentes (30, 60, 90 minutos após) se o horário original estiver ocupado.

    Args:
        start_time_iso: O horário inicial ocupado.
        end_time_iso: O horário final do intervalo (usado para calcular a duração).

    Retorna:
        Uma lista de strings ISO 8601 dos novos horários de início disponíveis.
    """
    start_time_dt = datetime.datetime.fromisoformat(start_time_iso)
    
    suggestions_iso = []
    
    # Tenta 30, 60 e 90 minutos depois do horário original
    for offset in [30, 60, 90]:
        new_start_time = start_time_dt + datetime.timedelta(minutes=offset)
        new_end_time = new_start_time + datetime.timedelta(hours=1) # Mantém 1h de duração
        
        new_start_time_iso = new_start_time.isoformat()
        new_end_time_iso = new_end_time.isoformat()

        if verificar_disponibilidade(new_start_time_iso, new_end_time_iso):
            suggestions_iso.append(new_start_time_iso)
            
    return suggestions_iso

def obter_eventos_por_palavra_chave(keyword: str) -> list[dict]:
    """
    Busca os 10 próximos eventos futuros por palavra-chave no título, descrição ou localização.
    
    Args:
        keyword: A palavra-chave de busca fornecida pelo Gemini.

    Retorna:
        Uma lista de dicionários formatados, ou lista vazia se não houver eventos.
    """
    service = get_calendar_service()

    clean_keyword = normalize_keyword(keyword)

    # 1. Define o ponto de partida (agora) em UTC
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    # 2. Formata a data de forma robusta para evitar o HttpError 400
    now_iso = format_datetime_for_query(now_dt)

    logging.info(f"Buscando eventos com a palavra-chave: {clean_keyword} e timeMin: {now_iso}")
    
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now_iso,  # Filtra apenas eventos futuros a partir de agora
        maxResults=10,    # Limita a 10 resultados
        # singleEvents e orderBy removidos para estabilidade com o parâmetro 'q'
        q=clean_keyword,  # O parâmetro de busca de texto livre
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        return []

    # Processa e formata os eventos para exibição
    results = []
    brazil_timezone = pytz.timezone(TIMEZONE_BRAZIL)
    
    for event in events:
        # Pega o 'dateTime' para eventos com hora ou 'date' para eventos de dia inteiro
        start = event['start'].get('dateTime', event['start'].get('date'))
        dt_obj = datetime.datetime.fromisoformat(start)
        
        # Converte o horário para o fuso horário de exibição (Brasil)
        local_time = dt_obj.astimezone(brazil_timezone)
        
        results.append({
            'titulo': event['summary'],
            'data_hora': local_time.strftime('%d/%m às %H:%M')
        })
        
    return results