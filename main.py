import streamlit as st
import json
import re
import os
import pandas as pd
import requests
import urllib3
import ssl
import urllib.request
import unicodedata
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# Desabilitar avisos de segurança SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurações Globais de Rede
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "VLC/3.0.18 LibVLC/3.0.18",
    "IPTVSmartersPlayer"
]

class LegacySslAdapter(requests.adapters.HTTPAdapter):
    """Adaptador SSL para compatibilidade máxima com cifras antigas e servidores legados."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers('ALL:@SECLEVEL=0')
        except:
            pass
        try:
            ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        except:
            pass
        kwargs['ssl_context'] = ctx
        return super(LegacySslAdapter, self).init_poolmanager(*args, **kwargs)

def normalize_text(text):
    """Normaliza strings removendo acentos e convertendo para minúsculas para busca precisa."""
    if not isinstance(text, str): return ""
    text = text.lower()
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')

def get_series_details(base_url, username, password, series_id):
    """Busca informações da série para identificar a última temporada e o último episódio."""
    try:
        url = f"{base_url}/player_api.php?username={quote(username)}&password={quote(password)}&action=get_series_info&series_id={series_id}"
        with requests.Session() as session:
            session.mount("https://", LegacySslAdapter())
            resp = session.get(url, headers={"User-Agent": USER_AGENTS[0], "Accept": "*/*"}, verify=False, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                episodes = data.get("episodes", {})
                if not episodes: return None
                valid_seasons = [int(k) for k in episodes.keys() if k.isdigit()]
                if not valid_seasons: return None
                last_season_num = max(valid_seasons)
                last_ep_list = episodes[str(last_season_num)]
                if not last_ep_list: return None
                last_episode = last_ep_list[-1]
                title = last_episode.get("title", "")
                match = re.search(r"S(\d+)E(\d+)", title, re.IGNORECASE)
                return match.group(0).upper() if match else f"S{last_season_num:02d}E{len(last_ep_list):02d}"
    except:
        pass
    return None

def test_single_user(user, search_query=""):
    """Testa status do usuário e coleta estatísticas de conteúdo em paralelo."""
    name = user.get('name', '')
    url = user.get('url', '')

    name = re.sub(r'^[✅❌]\s*', '', name)

    username = user.get('username') or user.get('user', '')
    if not username:
        user_match = re.search(r"username=([^&]+)", url, re.IGNORECASE)
        username = unquote(user_match.group(1)) if user_match else ""
    else:
        username = unquote(str(username))

    password = user.get('password') or user.get('pass', '')
    if not password:
        pass_match = re.search(r"password=([^&]+)", url, re.IGNORECASE)
        password = unquote(pass_match.group(1)) if pass_match else ""
    else:
        password = unquote(str(password))

    base_match = re.search(r"(https?://[^/]+)", url)
    base = base_match.group(1) if base_match else url
    if base:
        base = base.rstrip('/')
        if not base.startswith(('http://', 'https://')):
            base = 'http://' + base

    status = "offline"
    retorno_code = "Erro/Timeout"
    live_count, vod_count, series_count = 0, 0, 0
    search_matches = {"Canais": [], "Filmes": [], "Séries": []}

    if username and password and base:
        api_url = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
        
        urls_to_test = [api_url]
        if api_url.startswith("https://"):
            urls_to_test.append(api_url.replace("https://", "http://", 1))
        elif api_url.startswith("http://"):
            urls_to_test.append(api_url.replace("http://", "https://", 1))

        found_active = False

        for target_url in urls_to_test:
            if found_active:
                break

            for ua in USER_AGENTS:
                headers = {
                    "User-Agent": ua,
                    "Accept": "*/*",
                    "Connection": "keep-alive"
                }

                try:
                    with requests.Session() as session:
                        session.mount("https://", LegacySslAdapter())
                        resp = session.get(target_url, headers=headers, verify=False, timeout=4)
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
                except requests.exceptions.Timeout:
                    retorno_code = "Timeout"
                    break
                except requests.exceptions.ConnectionError:
                    retorno_code = "Erro Conexão"
                    break
                except:
                    pass

                if not found_active:
                    try:
                        ssl_ctx = ssl._create_unverified_context()
                        try:
                            ssl_ctx.set_ciphers('ALL:@SECLEVEL=0')
                        except:
                            pass
                        req = urllib.request.Request(target_url, headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=4) as response:
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

        if status == "active":
            actions_url = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
            s_norm = normalize_text(search_query) if search_query else ""

            actions = {
                "Canais": "get_live_streams",
                "Filmes": "get_vod_streams",
                "Séries": "get_series"
            }

            def fetch_content_action(category, action_name):
                url = f"{actions_url}&action={action_name}"
                try:
                    with requests.Session() as session:
                        session.mount("https://", LegacySslAdapter())
                        r = session.get(url, headers={"User-Agent": USER_AGENTS[0], "Accept": "*/*"}, verify=False, timeout=8)
                        if r.status_code == 200:
                            return category, r.json()
                except:
                    pass
                return category, None

            with ThreadPoolExecutor(max_workers=3) as inner_executor:
                future_to_cat = {inner_executor.submit(fetch_content_action, cat, act): cat for cat, act in actions.items()}
                for future in as_completed(future_to_cat):
                    cat, res_list = future.result()
                    if isinstance(res_list, list):
                        if cat == "Canais":
                            live_count = len(res_list)
                            if s_norm:
                                search_matches["Canais"] = [i.get("name", "") for i in res_list if i.get("name") and s_norm in normalize_text(i.get("name"))]
                        elif cat == "Filmes":
                            vod_count = len(res_list)
                            if s_norm:
                                search_matches["Filmes"] = [i.get("name", "") for i in res_list if i.get("name") and s_norm in normalize_text(i.get("name"))]
                        elif cat == "Séries":
                            series_count = len(res_list)
                            if s_norm:
                                matched_items = [i for i in res_list if i.get("name") and s_norm in normalize_text(i.get("name"))]
                                if matched_items:
                                    def fetch_detail(item):
                                        s_id = item.get("series_id")
                                        s_name = item.get("name", "")
                                        info = get_series_details(base, username, password, s_id)
                                        return f"{s_name} ({info})" if info else s_name

                                    with ThreadPoolExecutor(max_workers=5) as series_executor:
                                        results = list(series_executor.map(fetch_detail, matched_items[:10]))
                                    search_matches["Séries"] = results

    user['name'] = f"✅{name}" if status == "active" else f"❌{name}"
    user['retorno'] = retorno_code
    user['Canais'] = live_count
    user['Filmes'] = vod_count
    user['Séries'] = series_count
    
    if search_query:
        match_segments = []
        if search_matches["Canais"]: 
            match_segments.append(f"Canais ({len(search_matches['Canais'])})")
        if search_matches["Filmes"]: 
            filmes_inline = ", ".join(search_matches["Filmes"][:2])
            if len(search_matches["Filmes"]) > 2:
                filmes_inline += f" (+{len(search_matches['Filmes']) - 2})"
            match_segments.append(f"Filmes: {filmes_inline}")
        if search_matches["Séries"]: 
            series_inline = ", ".join(search_matches["Séries"][:2])
            if len(search_matches["Séries"]) > 2:
                series_inline += f" (+{len(search_matches['Séries']) - 2})"
            match_segments.append(f"Séries: {series_inline}")
            
        user['Resultados Busca'] = " | ".join(match_segments) if match_segments else "Nenhum"
        user['_search_details'] = search_matches
    else:
        user['Resultados Busca'] = "-"
        user['_search_details'] = {"Canais": [], "Filmes": [], "Séries": []}

    if username and password and base:
        user['json_link'] = f"{base}/player_api.php?username={quote(username)}&password={quote(password)}"
        user['m3u_link'] = f"{base}/get.php?username={quote(username)}&password={quote(password)}&type=m3u_plus"
    else:
        user['json_link'] = ""
        user['m3u_link'] = ""
        
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


st.set_page_config(page_title="Organizador de Logins", layout="wide")
st.subheader("Organizador de Logins .dev")

uploaded_file = st.file_uploader("Escolha um arquivo .dev", type="dev")
search_query = st.text_input("🔍 Buscar conteúdo específico nos servidores (Canais, Filmes ou Séries)", value="", key="search_query_input")

if uploaded_file is not None:
    try:
        file_id = f"data_{uploaded_file.name}_{uploaded_file.size}_{search_query}"
        btn_update = st.button("🚀 Testar / Atualizar Todos os Logins")
        
        if btn_update or "file_id" not in st.session_state or st.session_state.file_id != file_id:
            file_content = uploaded_file.getvalue().decode("utf-8")
            data = json.loads(file_content)

            if "multi_users" in data:
                with st.spinner("⚡ Analisando credenciais e consultando acervo de mídias simultaneamente..."):
                    tested_users = []
                    with ThreadPoolExecutor(max_workers=15) as executor:
                        futures = [executor.submit(test_single_user, user, search_query) for user in data["multi_users"]]
                        for future in as_completed(futures):
                            tested_users.append(future.result())

                st.success("Análise de status e conteúdo concluída com sucesso!")
                
                df_initial = pd.DataFrame(sort_users(tested_users))
                
                fixed_start = ['name', 'retorno', 'url', 'username', 'password', 'Canais', 'Filmes', 'Séries', 'Resultados Busca']
                fixed_end = ['json_link', 'm3u_link']
                
                cols = list(df_initial.columns)
                for c in fixed_start + fixed_end + ['userid', 'type', '_search_details']:
                    if c in cols: cols.remove(c)
                
                ordered_cols = [c for c in fixed_start if c in df_initial.columns]
                ordered_cols.extend(cols)
                ordered_cols.extend([c for c in fixed_end if c in df_initial.columns])
                
                st.session_state.df_users = df_initial[ordered_cols]
                st.session_state.file_id = file_id
            else:
                st.error("O arquivo `.dev` não contém a chave 'multi_users'.")
                st.stop()

        if "df_users" in st.session_state:
            st.subheader("Lista Organizada")

            edited_df = st.data_editor(
                st.session_state.df_users, 
                num_rows="dynamic", 
                use_container_width=True,
                column_config={
                    "userid": None, "type": None, "_search_details": None,
                    "name": st.column_config.TextColumn("Nome"),
                    "retorno": st.column_config.TextColumn("Retorno HTTP"),
                    "Canais": st.column_config.NumberColumn("📺 Canais"),
                    "Filmes": st.column_config.NumberColumn("🎬 Filmes"),
                    "Séries": st.column_config.NumberColumn("🍿 Séries"),
                    "Resultados Busca": st.column_config.TextColumn("🔎 Resultado Busca"),
                    "json_link": st.column_config.LinkColumn("Link JSON"),
                    "m3u_link": st.column_config.TextColumn("Link M3U")
                },
                disabled=["json_link", "retorno", "Canais", "Filmes", "Séries", "Resultados Busca"]
            )

            if not edited_df.equals(st.session_state.df_users):
                updated_list = edited_df.to_dict(orient="records")
                st.session_state.df_users = pd.DataFrame(sort_users(updated_list))
                st.rerun()

            edited_users = st.session_state.df_users.to_dict(orient="records")
            for user in edited_users:
                user.pop('json_link', None)
                user.pop('retorno', None)
                user.pop('m3u_link', None)
                user.pop('Canais', None)
                user.pop('Filmes', None)
                user.pop('Séries', None)
                user.pop('Resultados Busca', None)
                user.pop('_search_details', None)

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

            if search_query and '_search_details' in st.session_state.df_users.columns:
                st.markdown("### 🍿 Detalhes dos Itens Encontrados")
                encontrou_algo = False
                
                for _, row in st.session_state.df_users.iterrows():
                    details = row.get('_search_details')
                    if details and any(details.values()):
                        encontrou_algo = True
                        with st.expander(f"📦 {row['name']} | Usuário: {row.get('username', 'N/A')}"):
                            for cat, matches in details.items():
                                if matches:
                                    st.markdown(f"**{cat}:**")
                                    for item in matches[:15]:
                                        st.write(f"- {item}")
                                    if len(matches) > 15:
                                        st.write(f"... e mais {len(matches)-15} correspondências.")
                if not encontrou_algo:
                    st.info(f"Nenhum título correspondente a '{search_query}' foi localizado nos servidores ativos.")

    except json.JSONDecodeError:
        st.error("Erro ao decodificar o arquivo JSON. Certifique-se de que é um arquivo JSON válido.")
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
