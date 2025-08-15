import os
import requests
import json
import sqlite3
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
DB_FILE = "jobs.db"


def setup_database():
    """Cria o banco de dados e a tabela de vagas, se não existirem."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # A tabela 'jobs' terá uma coluna 'link' que é a chave primária.
    # Isso garante que cada link seja único no banco de dados.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            link TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()
    print("Banco de dados configurado com sucesso.")


def is_job_in_db(link):
    """Verifica se um link de vaga já existe no banco de dados."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # O '?' é um placeholder para evitar injeção de SQL
    cursor.execute("SELECT 1 FROM jobs WHERE link = ?", (link,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def add_job_to_db(link):
    """Adiciona um novo link de vaga ao banco de dados."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Usamos 'INSERT OR IGNORE' para que, se o link já existir, o comando
    # seja simplesmente ignorado sem causar um erro.
    cursor.execute("INSERT OR IGNORE INTO jobs (link) VALUES (?)", (link,))
    conn.commit()
    conn.close()


def scrape_gupy(url, max_pages=5):
    """
    Raspa o site da Gupy, navegando entre as páginas, extrai os detalhes 
    das vagas e retorna uma lista de dicionários.
    
    :param url: A URL inicial da busca.
    :param max_pages: O número máximo de páginas para raspar.
    """
    print("Iniciando o scraper da Gupy com suporte a paginação...")
    vagas_encontradas = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=60000)

            page_count = 1
            while page_count <= max_pages:
                print(f"\n--- Raspando a página {page_count} ---")
                
                # Espera o container principal das vagas carregar
                page.wait_for_selector('main#main-content ul', timeout=30000)
                time.sleep(3) # Pausa extra para garantir renderização completa
                
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                job_list_container = soup.find('main', id='main-content').find('ul')
                
                if not job_list_container:
                    print("Container de vagas não encontrado na página. Saindo...")
                    break
                    
                lista_de_vagas_html = job_list_container.find_all("li")
                print(f"Processando {len(lista_de_vagas_html)} vagas encontradas na página atual...")
                
                for vaga_html in lista_de_vagas_html:
                    # ... (O código de extração de cada vaga continua o mesmo)
                    titulo_tag = vaga_html.find("h3")
                    link_tag = vaga_html.find("a")

                    if titulo_tag and link_tag and link_tag.has_attr('href'):
                        link = link_tag["href"]
                        if not link.startswith("http"):
                            link = "https://portal.gupy.io" + link

                        location_tag = vaga_html.select_one('span[data-testid="job-location"]')
                        work_model_tag = vaga_html.select_one('div[aria-label^="Modelo de trabalho"] span')
                        
                        vaga_data = {
                            "title": titulo_tag.get_text(strip=True),
                            "link": link,
                            "location": location_tag.get_text(strip=True) if location_tag else "Não informado",
                            "work_model": work_model_tag.get_text(strip=True) if work_model_tag else "Não informado",
                        }
                        vagas_encontradas.append(vaga_data)

                # --- LÓGICA DE PAGINAÇÃO ---
                # Procura o botão "Próxima página"
                next_button_selector = 'button[aria-label="Next page"]'
                next_button = page.query_selector(next_button_selector)

                print(f"DEBUG: Botão 'Próxima' encontrado? {bool(next_button)}")

                # Verifica se o botão existe e se NÃO está desativado
                if next_button and not next_button.is_disabled():
                    print("Encontrado botão 'Próxima página'. Clicando...")
                    next_button.click()
                    page_count += 1
                    page.wait_for_load_state('networkidle', timeout=30000)
                    # page.wait_for_load_state('domcontentloaded')
                    time.sleep(2)
                else:
                    print("Não há mais páginas ou o botão 'Próxima página' está desativado. Finalizando a raspagem.")
                    break # Sai do loop while
            
            browser.close()
            
    except Exception as e:
        print(f"Ocorreu um erro inesperado no Playwright: {e}")
        return vagas_encontradas # Retorna o que conseguiu coletar até o erro

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
        return False

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
        return True
    else:
        # Se ocorrer uma falha, exibe o código de status para depuração.
        print(
            f"Falha ao enviar para o Discord. Status: {response.status_code}")
        return False


# Ponto de entrada do script.
# O código neste bloco só é executado quando o arquivo é chamado diretamente.
if __name__ == "__main__":
    print("Iniciando processo de busca e notificação de vagas...")

    setup_database()

    # 1. Chama a função de scraping para buscar as vagas.
    lista_de_vagas = scrape_gupy(GUPY_URL)

    vagas_novas = []
    for vaga in lista_de_vagas:
        if not is_job_in_db(vaga["link"]):
            vagas_novas.append(vaga)

    # 2. Se nenhuma vaga for encontrada, exibe uma mensagem e encerra.
    if not vagas_novas:
        print("Nenhuma vaga nova encontrada. Encerrando.")
    else:
        # 3. Se encontrou vagas, inicia o processo de envio.
        print(f"\nEnviando {len(vagas_novas)} vagas para o Discord...\n")
        # Para cada vaga na lista...
        for vaga in vagas_novas:
            # ...formata a mensagem...
            mensagem_formatada = format_discord_message(vaga)
            # ...e envia para o Discord.
            sucesso_envio = send_to_discord(DISCORD_WEBHOOK_URL, mensagem_formatada)
            # Delay de 1 segundo para evitar sobrecarregar a API do Discord.
            
            if sucesso_envio:
                add_job_to_db(vaga["link"])
                print(f"Vaga '{vaga['title']}' registrada no banco de dados.")

            time.sleep(3)

    print("\nProcesso finalizado.")
