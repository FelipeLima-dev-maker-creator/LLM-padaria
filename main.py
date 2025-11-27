import json
from openai import OpenAI
import pdfplumber
import csv
import re
import difflib
import unicodedata
import os
from dotenv import load_dotenv
from typing import List, Tuple, Dict


Produto = Tuple[str, float]

# -----------------------------
# Configuração do cliente OpenAI
# -----------------------------
load_dotenv()
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    print("ERRO: A variável de ambiente OPENAI_API_KEY não foi carregada corretamente.")
    exit()


# Função para carregar PDF

def load_pdf_text(pdf_path: str) -> str:
    """Extrai texto de todas as páginas de um PDF."""
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except FileNotFoundError:
        return f"Erro ao ler o PDF: Arquivo '{pdf_path}' não encontrado."
    except Exception as e:
        return f"Erro ao ler o PDF: {e}"


# Função para extrair produtos e preços do texto do PDF

def extract_products(pdf_text: str) -> List[Produto]:
    """Extrai uma lista de (Nome do Produto, Preço) do texto formatado do PDF."""
    produtos: List[Produto] = []
    # Expressão regular mais robusta: busca qualquer coisa antes de '—' e um preço R$X,XX
    # Não vamos considerar a primeira linha do PDF no loop se ela for um cabeçalho
    
    # Vamos iterar as linhas e usar o REGEX.
    # Ex: Pão Francês — R$0,80 
    # Ex: Bolo Inteiro Chocolate — R$38,00
    
    # Regex ajustado para capturar o nome e o preço corretamente
    # Padrão: (Nome) — R$(X,XX ou X.XX)
    pattern = r"(.+?)\s*—\s*R\$\s*(\d+[,.]\d{2})"
    
    for line in pdf_text.splitlines():
        # A linha pode ter mais de um produto, se eles estiverem na mesma linha separados por um espaço.
        # Ex: Pão Francês — R$0,80 | Pão de Forma — R$8,50
        
        # Vamos dividir a linha usando '|' para tratar múltiplos itens na mesma linha
        parts = line.split('|')
        
        for part in parts:
            match = re.search(pattern, part.strip())
            if match:
                nome = match.group(1).strip()
                # Substitui vírgula por ponto para conversão em float
                preco_str = match.group(2).replace(",", ".")
                try:
                    preco = float(preco_str)
                    produtos.append((nome, preco))
                except ValueError:
                    # Ignora se a conversão falhar (improvável se o regex funcionar)
                    pass
                    
    return produtos

# -----------------------------
# Função para normalizar texto
# -----------------------------
def remover_acentos(texto: str) -> str:
    """Remove acentos e caracteres especiais para melhor comparação (fuzzy matching)."""
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                   if unicodedata.category(c) != 'Mn')

# -----------------------------
# Pergunta ao LLM (resposta amigável)
# -----------------------------
def ask_llm(question: str, pdf_text: str = "") -> str:
    """Envia a pergunta ao LLM com o contexto do PDF."""
    context = ""
    if pdf_text:
        context = f"O usuário carregou um cardápio/lista de preços. Aqui está o conteúdo:\n\n{pdf_text}\n\n"
    
    # Adicionando um prompt mais claro sobre a sua função
    system_prompt = (
        "Você é um assistente de atendimento na Padaria Barreto. "
        "Seu objetivo é ser prestativo, educado e responder perguntas com base "
        "no cardápio/preços fornecidos no contexto. NÃO calcule o total do pedido. "
        "Apenas confirme os itens pedidos ou responda a outras dúvidas."
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context + question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Desculpe, houve um erro ao comunicar com a IA: {e}"


# Função para calcular pedidos (fuzzy matching e quantidades)

def calcular_pedido_completo(pedido: str, produtos: List[Produto]) -> Tuple[float, List[str]]:
    """Calcula o total de um pedido usando fuzzy matching com a lista de produtos."""
    total = 0.0
    itens_pedidos: List[str] = []
    
    # Cria uma lista de nomes de produtos normalizados para a comparação
    nomes_prod_norm: List[str] = [remover_acentos(p[0].lower()) for p in produtos]
    
    # Cria um mapa de (Nome Normalizado -> (Nome Original, Preço)) para fácil lookup
    mapa_produtos: Dict[str, Produto] = {
        remover_acentos(p[0].lower()): p for p in produtos
    }

    # Divide o pedido em itens individuais (ex: '2 pães, 1 café e 3 sonhos')
    palavras = re.split(r',| e ', remover_acentos(pedido.lower()))
    palavras = [p.strip() for p in palavras if p.strip()]

    # Regex para identificar QUANTIDADE e NOME em qualquer ordem, com ou sem a palavra 'de'
    # Ex: '2 paes franceses', 'paes franceses 2', '2 de paes'
    # Padrão: (\d+)?\s*(.*?)(\s+\d+)?
    # Tenta encontrar um número no início ou no fim da string
    
    for palavra in palavras:
        qtd_match = re.match(r'(\d+)\s+(.+)', palavra)
        
        if qtd_match:
            qtd = int(qtd_match.group(1))
            prod_nome_raw = qtd_match.group(2).strip()
        else:
            qtd = 1
            prod_nome_raw = palavra

        # Pega a melhor correspondência (fuzzy matching)
        match = difflib.get_close_matches(prod_nome_raw, nomes_prod_norm, n=1, cutoff=0.6)

        if match:
            nome_norm_match = match[0]
            nome_original, preco = mapa_produtos[nome_norm_match]
            
            subtotal = preco * qtd
            total += subtotal
            # Salva o item usando o nome original para o output
            itens_pedidos.append(f"{qtd} {nome_original} — R${subtotal:.2f}")
        else:
            # Melhoria: feedback sobre itens não encontrados
            print(f" Aviso: Não encontramos '{prod_nome_raw}' no cardápio.")


    return round(total, 2), itens_pedidos


# Função para formatar e exibir o cardápio

def display_cardapio(produtos: List[Produto]):
    """Formata e exibe os produtos disponíveis para o usuário."""
    print("""
-----------------------------------------------------------------------
          Padaria Barreto Doces – Lista de Preços e Atendimento 
-----------------------------------------------------------------------""")
    for nome, preco in produtos:
        
        preco_str = f"R${preco:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
        print(f"• {nome:.<30} {preco_str}") # Alinha o nome com pontos
    
    print("-" * 55)


def main():
    print(" Assistente LLM - Atendimento Padaria \n")

    pdf_path = "ListaPrecosLLM.pdf"
    pdf_text = load_pdf_text(pdf_path)

    if pdf_text.startswith("Erro"):
        print(pdf_text)
        return

    # CORREÇÃO/MELHORIA: Extrai a lista real de produtos do PDF.
    produtos_cardapio = extract_products(pdf_text)
    
    if not produtos_cardapio:
        print("ERRO: Não foi possível extrair nenhum produto do PDF. Verifique o formato do arquivo.")
        return

    # CORREÇÃO: Exibe a lista real de produtos.
    display_cardapio(produtos_cardapio)

    cliente = input("Por favor, digite seu nome: ").strip()
    print(f"\nOlá, **{cliente}**! Bem-vindo(a) à Padaria.\n")

    total_final = 0.0
    todos_itens = []

    while True:
        # Permite que o cliente peça vários itens de uma vez
        pedido_text = input("Insira os itens que deseja (ex: 2 pães franceses e 1 café com leite): ").strip()

        if pedido_text.lower() in ["sair", "finalizar", "x"]:
            break
        
        if not pedido_text:
            continue

        # 1 — Resposta amigável do LLM (apenas confirmação/conversa)
        resposta = ask_llm(pedido_text, pdf_text)
        print("\n**Assistente:**", resposta, "\n")

        # 2 — Cálculo REAL do pedido
        total, itens = calcular_pedido_completo(pedido_text, produtos_cardapio)

        if total > 0:
            total_final += total
            todos_itens.extend(itens)
            print(f" Itens adicionados. Subtotal atual: **R${total_final:.2f}**")
        
        print("-" * 55)


        # 3 — Pergunta se quer continuar
        continuar = input("Deseja pedir mais algum item? (s/n): ").strip().lower()
        if continuar not in ["s", "sim"]:
            break

    # FINALIZAÇÃO DO PEDIDO
    print("\n" + "="*50)
    print(f" RESUMO DO PEDIDO DE {cliente.upper()}:")
    print("="*50)
    
    if todos_itens:
        for item in todos_itens:
            print(f"- {item}")

        print("\n" + "="*50)
        print(f"**TOTAL A PAGAR: R${total_final:,.2f}**")
        print("="*50)
        
        
        csv_file = "pedidos.csv"
        # Garante que o arquivo CSV tenha o cabeçalho se for a primeira vez
        file_exists = os.path.isfile(csv_file) and os.path.getsize(csv_file) > 0

        with open(csv_file, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, delimiter=';') # Use ; como delimitador para evitar problemas com vírgulas no preço
            
            if not file_exists:
                writer.writerow(["Cliente", "Itens", "Total"])
                
            # Formata a lista de itens para o CSV
            itens_str = " | ".join(todos_itens)
            writer.writerow([cliente, itens_str, f"R${total_final:,.2f}"])

        print(f"\n Pedido salvo em '{csv_file}'. Obrigado pela preferência!\n")
    else:
        print("Nenhum item foi pedido. Volte sempre!")

if __name__ == "__main__":
    main()