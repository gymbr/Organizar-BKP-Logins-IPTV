import streamlit as st
import json
import re
import os
import pandas as pd
import requests
import urllib3
import ssl
import urllib.request
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# Desabilitar avisos de segurança SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LegacySslAdapter(requests.adapters.HTTPAdapter):
    """Adaptador SSL para compatibilidade máxima com cifras antigas e servidores legados."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers('ALL:@SECLEVEL=0')  # Permite qualquer cifra e reduz nível de segurança ao mínimo
        except:
            pass
        try:
            ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        except:
            pass
        kwargs['ssl_context'] = ctx
        return super(LegacySslAdapter, self).init_poolmanager(*args, **kwargs)

def test_single_user(user):
    """Testa se o usuário está ativo ou offline via Xtream API com múltiplos fallbacks de agentes e bibliotecas."""
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
    retorno_code = "Erro/Timeout"

    # Executa o teste caso possua todos os dados necessários
    if username and password and base:
        api_url = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
        
        # Lista de variações de protocolos para testar alternadamente
        urls_to_test = [api_url]
        if api_url.startswith("https://"):
            urls_to_test.append(api_url.replace("https://", "http://", 1))
        elif api_url.startswith("http://"):
            urls_to_test.append(api_url.replace("http://", "https://", 1))

        # Lista de User-Agents: Navegador Padrão vs Players de Mídia (frequentemente em Whitelist de WAFs)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "VLC/3.0.18 LibVLC/3.0.18",
            "IPTVSmartersPlayer"
        ]

        found_active = False

        for target_url in urls_to_test:
            if found_active:
                break

            for ua in user_agents:
                headers = {
                    "User-Agent": ua,
                    "Accept": "*/*",
                    "Connection": "keep-alive"
                }

                # MÉTODO 1: Requests com tratamento permissivo de resposta e SSL
                try:
                    with requests.Session() as session:
                        session.mount("https://", LegacySslAdapter())
                        resp = session.get(target_url, headers=headers, verify=False, timeout=10)
                        retorno_code = str(resp.status_code)
                        resp.encoding = resp.apparent_encoding
                        content = resp.text

                        if "user_info" in content:
                            if '"status":"Expired"' in content.replace(" ", "") or '"status":"expired"' in content.replace(" ", ""):
                                status = "offline"
                            else:
                                status = "active"
                            found_active = True
                            break
                except:
                    pass

                # MÉTODO 2: Fallback para urllib nativo
                if not found_active:
                    try:
                        ssl_ctx = ssl._create_unverified_context()
                        try:
                            ssl_ctx.set_ciphers('ALL:@SECLEVEL=0')
                        except:
                            pass
                        req = urllib.request.Request(target_url, headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as response:
                            retorno_code = str(response.getcode())
                            content = response.read().decode('utf-8', errors='ignore')
                            if "user_info" in content:
                                if '"status":"Expired"' in content.replace(" ", "") or '"status":"expired"' in content.replace(" ", ""):
                                    status = "offline"
                                else:
                                    status = "active"
                                found_active = True
                                break
                    except urllib.error.HTTPError as e:
                        retorno_code = str(e.code)
                    except:
                        pass

    # Define o novo emoji com base no status atualizado
    user['name'] = f"✅{name}" if status == "active" else f"❌{name}"
    user['retorno'] = retorno_code
    
    # Monta a URL JSON final para a tabela clicável
    if username and password and base:
        user['json_link'] = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
    else:
        user['json_link'] = ""
        
    return user

def sort_users(users_list):
    """Organiza a lista de usuários com base na hierarquia estipulada."""
    def get_sort_key(user):
        name = user.get('name', '')
        
        if '✅' in name: r1 = 0
        elif '❌' in name: r1 = 1
        else: r1 = 2
            
        if '🔥' in name: r2 = 0
        elif '💧' in name: r2 = 1
        else: r2 = 2
            
        if '🟢' in name: r3 = 0
        elif '🔞' in name: r3 = 1
        else: r3 = 2
            
        if '📺' in name: r4 = 0
        elif '📱' in name: r4 = 1
        else: r4 = 2
            
        r5 = name.lower()
        return (r1, r2, r3, r4, r5)

    return sorted(users_list, key=get_sort_key)


st.set_page_config(page_title="Organizador de Logins", layout="centered")
st.subheader("Organizador de Logins .dev")

uploaded_file = st.file_uploader("Escolha um arquivo .dev", type="dev")

if uploaded_file is not None:
    try:
        # Inicializa o estado dos dados se o arquivo acabou de ser carregado
        file_id = f"data_{uploaded_file.name}_{uploaded_file.size}"
        if "file_id" not in st.session_state or st.session_state.file_id != file_id:
            file_content = uploaded_file.getvalue().decode("utf-8")
            data = json.loads(file_content)

            if "multi_users" in data:
                with st.spinner("⚡ Testando status dos servidores de IPTV..."):
                    tested_users = []
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = [executor.submit(test_single_user, user) for user in data["multi_users"]]
                        for future in as_completed(futures):
                            tested_users.append(future.result())

                st.success("Análise de status concluída com sucesso!")
                
                # Cria o DataFrame inicial ordenado
                df_initial = pd.DataFrame(sort_users(tested_users))
                
                # Reorganiza as colunas
                cols = list(df_initial.columns)
                for c in ['name', 'retorno', 'url', 'json_link']:
                    if c in cols: cols.remove(c)
                
                ordered_cols = []
                if 'name' in df_initial.columns: ordered_cols.append('name')
                if 'retorno' in df_initial.columns: ordered_cols.append('retorno')
                if 'url' in df_initial.columns: ordered_cols.append('url')
                ordered_cols.extend(cols)
                if 'json_link' in df_initial.columns: ordered_cols.append('json_link')
                
                st.session_state.df_users = df_initial[ordered_cols]
                st.session_state.file_id = file_id
            else:
                st.error("O arquivo `.dev` não contém a chave 'multi_users'.")
                st.stop()

        # Renderiza e captura edições da tabela de forma reativa
        if "df_users" in st.session_state:
            edited_df = st.data_editor(
                st.session_state.df_users, 
                num_rows="dynamic", 
                use_container_width=True,
                column_config={
                    "userid": None,
                    "type": None,
                    "retorno": st.column_config.TextColumn("Retorno HTTP", help="Código de status HTTP retornado pelo servidor"),
                    "json_link": st.column_config.LinkColumn("Link JSON", help="URL gerada para a API do Player")
                },
                disabled=["json_link", "retorno"]
            )

            # Verifica se houve alguma alteração estrutural ou de valores
            if not edited_df.equals(st.session_state.df_users):
                # Converte o DataFrame de volta para lista de dicionários para reordenar
                updated_list = edited_df.to_dict(orient="records")
                sorted_list = sort_users(updated_list)
                
                # Atualiza o Session State com a nova ordem e recarrega a página
                st.session_state.df_users = pd.DataFrame(sorted_list)
                st.rerun()

            st.subheader("Lista Organizada")

            # Prepara dados para o download final limpando chaves temporárias
            edited_users = st.session_state.df_users.to_dict(orient="records")
            for user in edited_users:
                user.pop('json_link', None)
                user.pop('retorno', None)

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

    except json.JSONDecodeError:
        st.error("Erro ao decodificar o arquivo JSON. Certifique-se de que é um arquivo JSON válido.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
