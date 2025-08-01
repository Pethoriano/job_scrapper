import os
import requests
import json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import time

# Começa carregando as variáveis do arquivo .env.
# Assim, a URL do webhook do Discord não fica exposta direto no código.
load_dotenv()

# Define as constantes usadas no script: a URL de busca da Gupy
# e a URL do webhook obtida do .env.
GUPY_URL = "https://portal.gupy.io/job-search/term=python"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def scrape_gupy(url):
    # Função principal, responsável por entrar no site da Gupy e extrair os dados.
    # Usa o Playwright porque a página carrega vagas dinamicamente com JavaScript.
    # Um request simples não capturaria o conteúdo renderizado.
    # O Playwright abre um navegador em modo headless para carregar a página por completo.
    print("Iniciando o scraper da Gupy...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navega para a URL com um timeout de 60 segundos para permitir o carregamento.
            page.goto(url, timeout=60000)
            
            # Espera pelo seletor do menu de paginação.
            # Isso garante que a lista de vagas foi carregada dinamicamente.
            page.wait_for_selector('nav[aria-label="pagination navigation"]', timeout=30000)
            
            # Pausa para garantir a renderização completa de todos os elementos.
            time.sleep(3)
            
            # Pega o conteúdo HTML final da página.
            html = page.content()
            browser.close()
    except PlaywrightTimeoutError:
        # Captura o erro se o seletor de paginação não aparecer no tempo definido.
        # Evita que o script quebre por lentidão do site ou por mudanças no layout.
        print("Timeout ao esperar pelo seletor de paginação. O site pode estar lento ou o layout mudou.")
        return []
    except Exception as e:
        # Captura genérica para outros erros inesperados do Playwright.
        print(f"Ocorreu um erro inesperado no Playwright: {e}")
        return []

    # O HTML obtido é passado para o BeautifulSoup para facilitar a busca e extração de dados.
    soup = BeautifulSoup(html, "lxml")
    
    # Navega na estrutura do HTML para encontrar o container principal (main) e a lista (ul) das vagas.
    job_list_container = soup.find('main', id='main-content').find('ul')
    
    if not job_list_container:
        return []

    # Pega cada item da lista (cada <li> representa uma vaga).
    lista_de_vagas_html = job_list_container.find_all("li")
    vagas_encontradas = []

    print(f"Processando {len(lista_de_vagas_html)} vagas encontradas...")
    # Inicia um loop para processar o HTML de cada vaga encontrada.
    for vaga_html in lista_de_vagas_html:
        # Para cada vaga, busca a tag do título (h3) e a do link (a).
        titulo_tag = vaga_html.find("h3")
        link_tag = vaga_html.find("a")

        # Prossegue apenas se o título e o link existirem, para evitar erros.
        if titulo_tag and link_tag and link_tag.has_attr('href'):
            link = link_tag["href"]
            # Garante que todos os links sejam absolutos, pois alguns podem ser relativos (ex: /vaga/123).
            if not link.startswith("http"):
                link = "https://portal.gupy.io" + link

            # Usa seletores de CSS mais específicos para capturar a localização e o modelo de trabalho.
            location_tag = vaga_html.select_one('span[data-testid="job-location"]')
            work_model_tag = vaga_html.select_one('div[aria-label^="Modelo de trabalho"] span')
            
            # Monta um dicionário com os dados.
            # Se uma tag não for encontrada, atribui 'Não informado' para manter a consistência.
            vaga_data = {
                "title": titulo_tag.get_text(strip=True),
                "link": link,
                "location": location_tag.get_text(strip=True) if location_tag else "Não informado",
                "work_model": work_model_tag.get_text(strip=True) if work_model_tag else "Não informado",
            }
            vagas_encontradas.append(vaga_data)

    # Retorna a lista final com os dados de todas as vagas encontradas.
    return vagas_encontradas

def format_discord_message(job):
    # Formata a mensagem para o Discord.
    # Pega o dicionário da vaga e monta uma string usando a formatação Markdown do Discord.
    message = (
        f"---\n\n"
        f"**🍞 OPAAA - Chegando mais uma vaga fresquinha**\n\n"
        f"**💼 {job['title']}**\n"
        f"📍 **Local:** {job['location']}\n"
        f"🏢 **Modelo:** {job['work_model']}\n\n"
        f"🔗 [Ver vaga]({job['link']})\n\n"
    )
    return message

def send_to_discord(webhook_url, message):
    # Pega a URL do webhook e a mensagem formatada para enviar ao Discord.
    if not webhook_url:
        print("ERRO: URL do Webhook do Discord não configurada.")
        return

    # O Discord espera um request POST com um corpo em JSON.
    # O conteúdo da mensagem deve estar na chave "content".
    data = {"content": message}
    response = requests.post(
        webhook_url,
        data=json.dumps(data),
        headers={"Content-Type": "application/json"}
    )
    # Verifica se o status da resposta é 204, que indica sucesso para o Discord.
    if response.status_code == 204:
        print("Mensagem enviada com sucesso para o Discord!")
    else:
        # Se ocorrer uma falha, exibe o código de status para depuração.
        print(f"Falha ao enviar para o Discord. Status: {response.status_code}")


# Ponto de entrada do script.
# O código neste bloco só é executado quando o arquivo é chamado diretamente.
if __name__ == "__main__":
    print("Iniciando processo de busca e notificação de vagas...")
    
    # 1. Chama a função de scraping para buscar as vagas.
    lista_de_vagas = scrape_gupy(GUPY_URL)

    # 2. Se nenhuma vaga for encontrada, exibe uma mensagem e encerra.
    if not lista_de_vagas:
        print("Nenhuma vaga nova encontrada. Encerrando.")
    else:
        # 3. Se encontrou vagas, inicia o processo de envio.
        print(f"\nEnviando {len(lista_de_vagas)} vagas para o Discord...\n")
        # Para cada vaga na lista...
        for vaga in lista_de_vagas:
            # ...formata a mensagem...
            mensagem_formatada = format_discord_message(vaga)
            # ...e envia para o Discord.
            send_to_discord(DISCORD_WEBHOOK_URL, mensagem_formatada)
            # Delay de 1 segundo para evitar sobrecarregar a API do Discord.
            time.sleep(3)

    print("\nProcesso finalizado.")