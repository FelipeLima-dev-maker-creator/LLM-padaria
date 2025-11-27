☕ Padaria LLM - Assistente de Pedidos Inteligente
Este projeto implementa um assistente de IA capaz de processar pedidos de clientes com base em um cardápio fornecido em formato PDF, interpretando a intenção do cliente, calculando o valor total e registrando o histórico de transações em um arquivo CSV.

📄 Cardápio e Preços
O coração do sistema é o arquivo ListaPrecosLLM.pdf.
O agente de IA utiliza este PDF para:
-Extração de Dados: Na inicialização, o agente lê e interpreta o conteúdo do ListaPrecosLLM.pdf para criar uma lista precisa de produtos e seus respectivos preços (Ex: Pão Francês — R$0,80).
-Cálculo e Interpretação: Quando um cliente insere um pedido (Ex: "2 pao fraces e 1 Café com Leite"), a IA utiliza esta lista de preços para:
-Fazer a correspondência de nomes (Fuzzy Matching).
-Calcular o valor total com base nos preços do PDF.

💾 Registro de Transações (CSV)
Após o cálculo e a confirmação do pedido, todas as transações são registradas no arquivo
Exemplo: 
Felipe Barreto;2 Bolo Inteiro Chocolate — R$76.00;R$76.00
Tanigawa;3 Coxinha — R$18.00 | 1 Pastel Assado — R$6.50;R$24.50
Matue;1 Coxinha — R$6.00 | 2 Esfirra — R$10.00 | 1 Torta de Limão — R$40.00;R$56.00
