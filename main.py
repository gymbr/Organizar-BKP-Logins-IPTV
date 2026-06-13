import streamlit as st
import json
import re
import os
import pandas as pd
from functools import cmp_to_key
import requests
import urllib3
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# Desabilitar avisos de segurança SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cabeçalhos para simular o navegador nas requisições de teste
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Connection": "keep-alive"
}

def test_single_user(user):
    """Testa se o usuário está ativo ou offline via Xtream API e atualiza o emoji no nome."""
    name = user.get('name', '')
    url = user.get('url', '')

    # Remove emoji de status antigo (✅ ou ❌) se já existir no início do nome
    name = re.sub(r'^[✅❌]\s*', '', name)

    # 1. Tenta obter usuário das chaves dedicadas ou extrai da URL se não existirem
    username = user.get('username') or user.get('user', '')
    if not username:
        user_match = re.search(r"username=([^&]+)", url, re.IGNORECASE)
        username = unquote(user_match.group(1)) if user_match else ""
    else:
        username = unquote(str(username))

    # 2. Tenta obter a senha das chaves dedicadas ou extrai da URL se não existirem
    password = user.get('password') or user.get('pass', '')
    if not password:
        pass_match = re.search(r"password=([^&]+)", url, re.IGNORECASE)
        password = unquote(pass_match.group(1)) if pass_match else ""
    else:
        password = unquote(str(password))

    # 3. Identifica e higieniza a URL base do servidor
    base_match = re.search(r"(https?://[^/]+)", url)
    base = base_match.group(1) if base_match else url
    if base:
        base = base.rstrip('/')
        if not base.startswith(('http://', 'https://')):
            base = 'http://' + base

    status = "offline"

    # Executa o teste caso possua todos os dados necessários
    if username and password and base:
        api_url = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
        try:
            resp = requests.get(api_url, headers=HEADERS, verify=False, timeout=12)
            data_json = resp.json()
            
            # Valida se retornou a estrutura correta de login ativo
            if isinstance(data_json, dict) and "user_info" in data_json:
                user_status = data_json.get("user_info", {}).get("status")
                if user_status != "Expired":
                    status = "active"
        except:
            pass

    # Define o novo emoji com base no status atualizado
    user['name'] = f"✅ {name}" if status == "active" else f"❌ {name}"
    return user

def sort_users(users_list):
    """Organiza a lista de usuários com base nas regras de ordenação."""
    def get_emoji_sort_key(name):
        priority_order = ['❌', '✅', '📺', '🔞', '🟢', '💧', '🔥']
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

        # Regra 2: Nomes com palavras
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
st.subheader("Organizador de Logins .dev")

uploaded_file = st.file_uploader("Escolha um arquivo .dev", type="dev")

if uploaded_file is not None:
    try:
        file_content = uploaded_file.getvalue().decode("utf-8")
        data = json.loads(file_content)

        if "multi_users" in data:
            original_users = data["multi_users"]

            # Processamento em paralelo para testar o status de todos os usuários
            with st.spinner("⚡ Testando status dos servidores de IPTV..."):
                tested_users = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(test_single_user, user) for user in original_users]
                    for future in as_completed(futures):
                        tested_users.append(future.result())

            st.success("Análise de status concluída com sucesso!")
            organized_users = sort_users(tested_users)

            st.subheader("Lista de Usuários Organizada")

            # Converte para DataFrame
            df_users = pd.DataFrame(organized_users)
            
            # Reorganiza as colunas: 'name' em primeiro e 'url' em segundo
            cols = list(df_users.columns)
            ordered_cols = []
            if 'name' in cols:
                ordered_cols.append('name')
                cols.remove('name')
            if 'url' in cols:
                ordered_cols.append('url')
                cols.remove('url')
            ordered_cols.extend(cols)
            df_users = df_users[ordered_cols]

            # Exibe a tabela editável e oculta as colunas 'userid' e 'type' da interface
            edited_df = st.data_editor(
                df_users, 
                num_rows="dynamic", 
                use_container_width=True,
                column_config={
                    "userid": None,
                    "type": None
                }
            )

            # Reconverte a tabela editada de volta para a estrutura JSON
            edited_users = edited_df.to_dict(orient="records")
            new_data = {"multi_users": edited_users}

            organized_content = json.dumps(new_data, indent=2, ensure_ascii=False)

            original_file_name, file_extension = os.path.splitext(uploaded_file.name)
            download_file_name = f"{original_file_name}_organized{file_extension}"

            st.download_button(
                label="Clique para Baixar o Arquivo Organizado",
                data=organized_content,
                file_name=download_file_name,
                mime="application/octet-stream"
            )

        else:
            st.error("O arquivo `.dev` não contém a chave 'multi_users'. Por favor, verifique se o arquivo está no formato correto.")

    except json.JSONDecodeError:
        st.error("Erro ao decodificar o arquivo JSON. Certifique-se de que é um arquivo JSON válido.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
