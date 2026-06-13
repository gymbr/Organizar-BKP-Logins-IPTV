import streamlit as st
import json
import re
import os
import pandas as pd
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
    
    # Monta a URL JSON final para a tabela clicável
    if username and password and base:
        user['json_link'] = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
    else:
        user['json_link'] = ""
        
    return user

def sort_users(users_list):
    """
    Organiza a lista de usuários com base na hierarquia estipulada:
    1. ✅ depois ❌
    2. 🔥 depois 💧
    3. 🟢 depois 🔞
    4. 📺 depois 📱
    5. Ordem alfabética
    """
    def get_sort_key(user):
        name = user.get('name', '')
        
        # 1- ✅ depois ❌
        if '✅' in name: r1 = 0
        elif '❌' in name: r1 = 1
        else: r1 = 2
            
        # 2- 🔥 depois 💧
        if '🔥' in name: r2 = 0
        elif '💧' in name: r2 = 1
        else: r2 = 2
            
        # 3- 🟢 depois 🔞
        if '🟢' in name: r3 = 0
        elif '🔞' in name: r3 = 1
        else: r3 = 2
            
        # 4- 📺 depois 📱
        if '📺' in name: r4 = 0
        elif '📱' in name: r4 = 1
        else: r4 = 2
            
        # 5- Ordem alfabética (case-insensitive)
        r5 = name.lower()
        
        return (r1, r2, r3, r4, r5)

    return sorted(users_list, key=get_sort_key)


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
            
            # Reorganiza as colunas manualmente colocando 'json_link' estritamente por último
            cols = list(df_users.columns)
            for c in ['name', 'url', 'json_link']:
                if c in cols:
                    cols.remove(c)
            
            ordered_cols = []
            if 'name' in df_users.columns:
                ordered_cols.append('name')
            if 'url' in df_users.columns:
                ordered_cols.append('url')
                
            ordered_cols.extend(cols) # adiciona colunas dinâmicas remanescentes
            
            if 'json_link' in df_users.columns:
                ordered_cols.append('json_link')
                
            df_users = df_users[ordered_cols]

            # Exibe a tabela editável, define o link como clicável e bloqueia edição na coluna do Link
            edited_df = st.data_editor(
                df_users, 
                num_rows="dynamic", 
                use_container_width=True,
                column_config={
                    "userid": None,
                    "type": None,
                    "json_link": st.column_config.LinkColumn("Link JSON", help="URL gerada para a API do Player")
                },
                disabled=["json_link"]
            )

            # Reconverte a tabela de volta e limpa a chave temporária de exibição do JSON link
            edited_users = edited_df.to_dict(orient="records")
            for user in edited_users:
                user.pop('json_link', None)

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
            st.error("O arquivo `.dev` não contém a chave 'multi_users'.")

    except json.JSONDecodeError:
        st.error("Erro ao decodificar o arquivo JSON. Certifique-se de que é um arquivo JSON válido.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
