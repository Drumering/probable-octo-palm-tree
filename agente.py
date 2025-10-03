# --- 1. Importações e Configuração Inicial ---
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import os
import logging
import datetime
import pytz
import json

# Importações do Gemini
from google import genai
from google.genai import types

# Importações das Ferramentas do Calendar
from google_calendar_tools import (
    obter_eventos_por_palavra_chave, 
    verificar_disponibilidade, 
    criar_evento, 
    sugerir_horarios,
    TIMEZONE_BRAZIL # Importa a constante do fuso horário para uso local
)

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Constantes e Variáveis Globais
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

client = genai.Client(api_key=GEMINI_API_KEY)
user_context_storage = {} # Memória/Estado para raciocínio multi-turno

# --- 2. Schemas e Tools do Gemini ---

AGENDAMENTO_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "titulo": types.Schema(type=types.Type.STRING, description="O título ou resumo do evento."),
        "data": types.Schema(type=types.Type.STRING, description="A data do evento, SEMPRE no formato 'YYYY-MM-DD'."),
        "hora": types.Schema(type=types.Type.STRING, description="A hora do evento no formato 'HH:MM' (24 horas).")
    },
    required=["titulo", "data", "hora"]
)

CONSULTA_AGENDA_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name='obter_eventos_por_palavra_chave',
            description='Busca eventos futuros no calendário com base em uma palavra-chave (ex: "almoço", "reunião").',
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'keyword': types.Schema(type=types.Type.STRING, description='A palavra-chave de busca.')
                },
                required=['keyword']
            )
        )
    ]
)

# --- 3. Funções de Raciocínio (Gemini Logic) ---

def analisar_e_decidir_acao_com_gemini(texto: str) -> dict | None:
    """
    Usa o Gemini para analisar a intenção (agendar/consultar) e extrair os parâmetros.

    Args:
        texto: A mensagem de entrada do usuário.

    Retorna:
        Um dicionário JSON com a decisão ('action') e os parâmetros, ou None em caso de erro.
    """
    today_date = datetime.date.today().strftime('%Y-%m-%d')
    
    prompt = (
        f"A data atual é {today_date}. Analise o pedido do usuário: '{texto}'. "
        "DECIDA se a intenção é 'agendar', 'consultar' ou 'verificar'. "
        "Se a intenção for 'consultar', extraia APENAS o assunto principal do evento (ex: 'almoço', 'reunião'). "
        "Se a intenção for 'agendar' ou 'verificar', converta a data para YYYY-MM-DD. "
        "Sua resposta DEVE ser um JSON que inclui o campo 'action'."
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        'action': types.Schema(type=types.Type.STRING, description='A ação principal: "agendar", "consultar" ou "verificar".'),
                        'agendamento': AGENDAMENTO_SCHEMA,
                        'consulta': types.Schema(type=types.Type.STRING, description='A palavra-chave para consulta, se a ação for "consultar".')
                    },
                    required=['action']
                ),
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        logging.error(f"Erro ao chamar a API do Gemini: {e}")
        return None


# --- 4. Funções de Execução das Ações ---

async def execute_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE, keyword: str):
    """
    Executa a lógica de consulta (busca) no calendário.
    """
    chat_id = update.effective_chat.id
    
    if not keyword:
        await context.bot.send_message(chat_id=chat_id, text="Não consegui extrair a palavra-chave para consulta.")
        return

    eventos = obter_eventos_por_palavra_chave(keyword)
    
    if eventos:
        response_text = f"Encontrei os seguintes eventos futuros sobre '{keyword}':\n\n"
        for event in eventos:
            response_text += f"📅 {event['titulo']} - {event['data_hora']}\n"
    else:
        response_text = f"Não encontrei eventos futuros para '{keyword}'."
    
    await context.bot.send_message(chat_id=chat_id, text=response_text)


async def execute_agendamento(update: Update, context: ContextTypes.DEFAULT_TYPE, entidades: dict):
    """
    Executa a lógica principal de agendamento (Validação, Verificação, Criação).
    Lida com o fluxo multi-turno de sugestão de horários.
    """
    chat_id = update.effective_chat.id
    
    try:
        # 1. Validação e Formatação Inicial
        if not entidades or not entidades.get('titulo') or not entidades.get('hora'):
            raise ValueError("Dados incompletos do Gemini.")

        resumo = entidades["titulo"]
        data_alvo_str = entidades["data"].strip()

        data_alvo = datetime.datetime.strptime(data_alvo_str, '%Y-%m-%d').date()
        hora, minuto = map(int, entidades["hora"].split(':'))
        fuso_brasil = pytz.timezone(TIMEZONE_BRAZIL)

        # 2. Formatação ISO com Fuso Horário
        # Assume 1 hora de duração padrão para o evento
        inicio_com_fuso = fuso_brasil.localize(datetime.datetime.combine(data_alvo, datetime.time(hora, minuto)))
        fim_com_fuso = inicio_com_fuso + datetime.timedelta(hours=1)
        inicio_iso = inicio_com_fuso.isoformat()
        fim_iso = fim_com_fuso.isoformat()

    except Exception as e:
        logging.error(f"Erro na conversão de dados do agendamento: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Houve um erro na conversão dos dados do agendamento. Tente um formato de data/hora mais claro.")
        return

    # 3. AÇÃO: Verificar Disponibilidade
    disponivel = verificar_disponibilidade(inicio_iso, fim_iso)

    if disponivel:
        # 3.1. Criar Evento Imediatamente
        link_evento = criar_evento(resumo, inicio_iso, fim_iso)
        texto_resposta = (
            f"✅ Perfeito! O evento '{resumo}' foi agendado para "
            f"{data_alvo.strftime('%d/%m/%Y')} às {inicio_com_fuso.strftime('%H:%M')}. "
            f"Veja no seu calendário: {link_evento}"
        )
    else:
        # 3.2. Sugerir Horários (Inicia o fluxo Multi-Turno)
        sugestoes = sugerir_horarios(inicio_iso, fim_iso)
        if sugestoes:
            suggestion_map = {}
            numbered_suggestions = []
            for i, iso_time in enumerate(sugestoes):
                dt_obj = datetime.datetime.fromisoformat(iso_time)
                suggestion_map[f"{i + 1}"] = iso_time
                numbered_suggestions.append(f"({i + 1}) às {dt_obj.strftime('%H:%M')}")
            
            # Salva o contexto na memória
            user_context_storage[chat_id] = {'summary': resumo, 'suggestions': suggestion_map}
            
            sugestoes_str = ' ou '.join(numbered_suggestions)
            texto_resposta = (
                f"❌ O horário solicitado ({inicio_com_fuso.strftime('%H:%M')}) está ocupado. "
                f"Que tal uma dessas opções: {sugestoes_str}? "
                f"Responda com o número da opção desejada (ex: '1')."
            )
        else:
            texto_resposta = "❌ O horário solicitado está ocupado e não consegui encontrar horários livres próximos."

    await context.bot.send_message(chat_id=chat_id, text=texto_resposta)

async def execute_verificacao(update: Update, context: ContextTypes.DEFAULT_TYPE, entidades: dict):
    """
    Executa a lógica de verificação de disponibilidade em um horário específico.
    """
    chat_id = update.effective_chat.id
    
    try:
        # 1. Validação e Formatação Inicial (o mesmo do agendamento)
        if not entidades or not entidades.get('data') or not entidades.get('hora'):
            raise ValueError("Dados de data/hora incompletos do Gemini.")

        data_alvo_str = entidades["data"].strip()
        data_alvo = datetime.datetime.strptime(data_alvo_str, '%Y-%m-%d').date()
        hora, minuto = map(int, entidades["hora"].split(':'))
        fuso_brasil = pytz.timezone(TIMEZONE_BRAZIL)

        # 2. Formatação ISO com Fuso Horário (Assume 1 hora de duração padrão para a verificação)
        inicio_com_fuso = fuso_brasil.localize(datetime.datetime.combine(data_alvo, datetime.time(hora, minuto)))
        fim_com_fuso = inicio_com_fuso + datetime.timedelta(hours=1)
        inicio_iso = inicio_com_fuso.isoformat()
        fim_iso = fim_com_fuso.isoformat()

    except Exception as e:
        logging.error(f"Erro na conversão de dados da verificação: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Houve um erro na conversão da data/hora. Tente um formato mais claro.")
        return

    # 3. AÇÃO: Verificar Disponibilidade
    disponivel = verificar_disponibilidade(inicio_iso, fim_iso)
    
    # 4. Construir Resposta
    data_formatada = inicio_com_fuso.strftime('%d/%m às %H:%M')

    if disponivel:
        texto_resposta = f"✅ **Confirmado!** Você está livre no dia {data_formatada}."
    else:
        # Sugere horários alternativos se o principal estiver ocupado
        sugestoes = sugerir_horarios(inicio_iso, fim_iso)
        
        if sugestoes:
            suggestion_map = {}
            numbered_suggestions = []
            for i, iso_time in enumerate(sugestoes):
                dt_obj = datetime.datetime.fromisoformat(iso_time)
                suggestion_map[f"{i + 1}"] = iso_time
                numbered_suggestions.append(f"({i + 1}) às {dt_obj.strftime('%H:%M')}")

            # Salva o contexto na memória
            user_context_storage[chat_id] = {
                'action': 'awaiting_time_selection',
                'suggestions': suggestion_map
            }

            sugestoes_str = ' ou '.join(numbered_suggestions)
            texto_resposta = (
                f"❌ Ocupado. Você tem compromisso no dia {data_formatada}. "
                f"Encontrei disponibilidade para: {sugestoes_str}."
                f"**Responda com o número da opção desejada para agendar o evento.**"
            )
        else:
            texto_resposta = (
                f"❌ Ocupado. Você tem compromisso no dia {data_formatada} e não encontrei horários livres nas horas seguintes."
            )

    await context.bot.send_message(chat_id=chat_id, text=texto_resposta)

# --- 5. Handlers do Telegram ---

async def iniciar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /start: mensagem de boas-vindas."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Olá! Eu sou o seu agente de agendamento e consulta de calendário. Estou pronto para te ajudar!"
    )


async def handle_follow_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler multi-turno: Processa a resposta do usuário (um número) a uma sugestão de horário.
    Unifica a lógica de agendamento e verificação.
    """
    chat_id = update.effective_chat.id
    user_response = update.message.text.strip()
    
    if chat_id not in user_context_storage:
        return False # Sem contexto, passa para o próximo handler
        
    context_data = user_context_storage[chat_id]
    action = context_data.get('action')

    # TRATAMENTO DE SELEÇÃO DE HORÁRIO (Estado: awaiting_time_selection)
    if action == 'awaiting_time_selection' and user_response.isdigit():
        suggestions = context_data['suggestions']
        
        if user_response in suggestions:
            chosen_iso_time = suggestions[user_response]
            
            # --- Lógica de Transição: Agendamento Original vs. Verificação ---
            
            # Se o RESUMO/TÍTULO já existe (veio de um comando 'agendar' original), agenda imediatamente.
            if 'summary' in context_data:
                summary = context_data['summary']
                
                chosen_start_dt = datetime.datetime.fromisoformat(chosen_iso_time)
                chosen_end_dt = (chosen_start_dt + datetime.timedelta(hours=1)).isoformat()
                link = criar_evento(summary, chosen_iso_time, chosen_end_dt)
                
                del user_context_storage[chat_id]
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Agendamento Confirmado! O evento '{summary}' foi marcado para as {chosen_start_dt.strftime('%H:%M')}. Veja: {link}"
                )
                return True # Finaliza o agendamento
                
            # Se o RESUMO/TÍTULO NÃO existe (veio de um comando 'verificar'), pede o título.
            else:
                # ATUALIZA O ESTADO para AWAITING_TITLE, armazenando o horário escolhido
                user_context_storage[chat_id] = {
                    'action': 'awaiting_title',
                    'chosen_time_iso': chosen_iso_time,
                }
                
                # Pede o título do evento
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Ótimo! Horário selecionado. Agora, **qual será o título/resumo** deste evento?"
                )
                return True # Processamento multi-turno completo
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Opção inválida. Por favor, responda apenas com o número da opção (ex: '1', '2', etc.)."
            )
            return True
    
    return False # Passa para o próximo handler se não for uma seleção numérica válida


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler geral: Processa todas as mensagens de texto.
    Usa o Gemini para decidir a intenção e encaminha a ação.
    """
    full_message = update.message.text
    chat_id = update.effective_chat.id

    # 1. VERIFICAÇÃO DE ESTADO MULTI-TURNO: AWAITING TITLE
    if chat_id in user_context_storage:
        context_data = user_context_storage[chat_id]
        if context_data.get('action') == 'awaiting_title':
            
            # AÇÃO: Finalizar o Agendamento com Título Fornecido
            summary = full_message # O texto do usuário é o novo título
            chosen_iso_time = context_data['chosen_time_iso']

            chosen_start_dt = datetime.datetime.fromisoformat(chosen_iso_time)
            chosen_end_dt = (chosen_start_dt + datetime.timedelta(hours=1)).isoformat()
            
            link = criar_evento(summary, chosen_iso_time, chosen_end_dt)
            
            # Limpa a memória para o próximo comando
            del user_context_storage[chat_id]
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Agendamento Confirmado! O evento '{summary}' foi marcado para as {chosen_start_dt.strftime('%H:%M')}. Veja: {link}"
            )
            return # Processamento multi-turno completo, não continua para o Gemini.

    # 2. RACIOCÍNIO: Decisão de Ação (Gemini)
    decision = analisar_e_decidir_acao_com_gemini(full_message)
    
    if not decision:
        await context.bot.send_message(chat_id=chat_id, text="Não consegui processar sua solicitação. Tente de novo.")
        return

    action = decision.get('action')

    if action == 'agendar':
        # 2.1. AÇÃO: Executa a lógica de AGENDAMENTO
        await execute_agendamento(update, context, decision.get('agendamento'))

    elif action == 'verificar':
        # 2.2. AÇÃO: Executa a lógica de VERIFICAÇÃO
        await execute_verificacao(update, context, decision.get('agendamento'))
        
    elif action == 'consultar':
        # 2.3. AÇÃO: Executa a lógica de CONSULTA
        await execute_consulta(update, context, decision.get('consulta'))
        
    else:
        # Resposta padrão se o Gemini retornar uma ação desconhecida ou vazia
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Desculpe, não entendi se você quer agendar ou consultar um evento. Tente 'Agende X' ou 'Qual é o meu X'."
        )


# --- 6. Configuração Principal do App ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN_TELEGRAM).build()

    # Handlers de Comando
    app.add_handler(CommandHandler('start', iniciar_handler))

    # Handlers de Mensagens (Ordem crucial: follow-up > geral)
    # 1. Handler para respostas numéricas (raciocínio multi-turno)
    # filters.Regex(r'^\d+$') garante que apenas números sejam processados aqui.
    app.add_handler(MessageHandler(filters.Regex(r'^\d+$') & (~filters.COMMAND), handle_follow_up))
    
    # 2. Handler geral para o raciocínio de intenção (Gemini)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_messages))

    app.run_polling()