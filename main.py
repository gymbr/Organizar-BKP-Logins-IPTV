import streamlit as st
import json
import re
import os
from functools import cmp_to_key

def sort_users(users_list):
    """
    Organiza a lista de usuários com base nas regras de ordenação:
    1. Nome com 👎.
    2. Nomes com letras/palavras, priorizando a palavra final (Z-A).
    3. Emojis na ordem inversa.
    4. Nomes "Teste" por último.
    5. Como desempate, ordena a URL por ordem alfabética de Z até A.
    """
    def get_emoji_sort_key(name):
        # Define a ordem de prioridade dos emojis (da mais alta para a mais baixa)
        priority_order = ['❌', '📺', '🔞', '🟢', '💧', '🔥']
        
        # Cria a chave de ordenação com base na prioridade de cada emoji na sequência
        sort_key = []
        for emoji in name:
            if emoji in priority_order:
                sort_key.append(priority_order.index(emoji))
        
        return tuple(sort_key)

    def compare_users(user1, user2):
        name1 = user1.get('name', '')
        url1 = user1.get('url', '')
        name2 = user2.get('name', '')
        url2 = user2.get('url', '')

        # Regra 1: "Teste" sempre por último
        if name1 == 'Teste' and name2 != 'Teste':
            return 1
        if name1 != 'Teste' and name2 == 'Teste':
            return -1

        # Regra 2: 👎 primeiro
        if '👎' in name1 and '👎' not in name2:
            return -1
        if '👎' not in name1 and '👎' in name2:
            return 1

        # Regra 3: Nomes com palavras
        is_word_name1 = bool(re.search(r'[a-zA-ZáàâãéèêíïóôõöúüçÇÁÀÂÃÉÈÊÍÏÓÕÖÚÜ]', name1))
        is_word_name2 = bool(re.search(r'[a-zA-ZáàâãéèêíïóôõöúüçÇÁÀÂÃÉÈÊÍÏÓÕÖÚÜ]', name2))
        
        if is_word_name1 and not is_word_name2:
            return -1
        if not is_word_name1 and is_word_name2:
            return 1

        # Comparação entre nomes com palavras
        if is_word_name1 and is_word_name2:
            word_match1 = re.search(r'\b(\w+)\b$', name1)
            word1 = word_match1.group(1) if word_match1 else ""
            word_match2 = re.search(r'\b(\w+)\b$', name2)
            word2 = word_match2.group(1) if word_match2 else ""
            
            # Prioridade 1: Ordenar pela palavra no final do nome (Z-A)
            if word1 != word2:
                return -1 if word1 > word2 else 1
            
            # Prioridade 2: Ordenar pela sequência de emojis (prioridade definida)
            key1 = get_emoji_sort_key(name1)
            key2 = get_emoji_sort_key(name2)
            
            if key1 != key2:
                return 1 if key1 > key2 else -1
            
            # Prioridade 3: URL como desempate (Z-A)
            return -1 if url1 > url2 else 1

        # Regra 4: Nomes puros de emoji
        key1 = get_emoji_sort_key(name1)
        key2 = get_emoji_sort_key(name2)
        
        if key1 != key2:
            return 1 if key1 > key2 else -1
        
        return -1 if url1 > url2 else 1

    return sorted(users_list, key=cmp_to_key(compare_users))


st.set_page_config(page_title="Organizador de Logins", layout="centered")
st.title("Organizador de Logins .dev")
st.markdown("Faça o upload do seu arquivo de backup `.dev` para organizar a lista de logins.")

uploaded_file = st.file_uploader("Escolha um arquivo .dev", type="dev")

if uploaded_file is not None:
    try:
        file_content = uploaded_file.getvalue().decode("utf-8")
        data = json.loads(file_content)

        if "multi_users" in data:
            st.success("Arquivo lido com sucesso! Processando...")

            original_users = data["multi_users"]
            organized_users = sort_users(original_users)

            new_data = {"multi_users": organized_users}

            organized_content = json.dumps(new_data, indent=2, ensure_ascii=False)

            original_file_name, file_extension = os.path.splitext(uploaded_file.name)
            download_file_name = f"{original_file_name}_organized{file_extension}"

            with st.expander("Clique para ver o conteúdo organizado"):
                st.json(new_data)

            st.download_button(
                label="Clique para Baixar o Arquivo Organizado",
                data=organized_content,
                file_name=download_file_name,
                mime="application/octet-stream"
            )

            st.info("Seu novo arquivo `.dev` foi gerado e está pronto para ser baixado. Você pode usá-lo para substituir o arquivo de backup original.")

        else:
            st.error("O arquivo `.dev` não contém a chave 'multi_users'. Por favor, verifique se o arquivo está no formato correto.")

    except json.JSONDecodeError:
        st.error("Erro ao decodificar o arquivo JSON. Certifique-se de que é um arquivo JSON válido.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
