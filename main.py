import os
import sys
import json
import datetime
import re
from typing import Optional

# Força UTF-8 no terminal
if sys.platform.startswith('win'):
    os.system('chcp 65001 >nul')

import discord
from discord.ext import tasks, commands
import requests
from bs4 import BeautifulSoup

# =========================
# Configuração do TOKEN
# =========================

# Tenta obter TOKEN de múltiplas formas
TOKEN = (
    os.environ.get("TOKEN") or 
    os.environ.get("DISCORD_TOKEN") or
    os.environ.get("BOT_TOKEN")
)

# Debug para Railway
if not TOKEN:
    print("DEBUG: Variáveis disponíveis:")
    for key in sorted(os.environ.keys()):
        if 'TOKEN' in key.upper() or 'DISCORD' in key.upper():
            value = os.environ[key]
            print(f"  {key}: {value[:10]}{'...' if len(value) > 10 else ''}")
    
    print("TOKEN não encontrado nas variáveis de ambiente!")
    print("Configure TOKEN no Railway: Settings > Variables")
    sys.exit(1)

print(f"TOKEN carregado: {TOKEN[:10]}...")

# =========================
# Configuração do Bot
# =========================

PREFIX = "!"
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
BASE_PATCH_URL_PT = "https://www.leagueoflegends.com/pt-br/news/game-updates/patch-{}-notes/"
BASE_PATCH_URL_EN = "https://www.leagueoflegends.com/en-us/news/game-updates/patch-{}-notes/"

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Estado global
config = {"canal_id": None}
versao_atual = None
CONFIG_FILE = "config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# =========================
# Funções de Configuração
# =========================

def load_config():
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
    except Exception as e:
        print(f"Erro ao carregar config: {e}")

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")

# =========================
# Funções HTTP e Versão
# =========================

def http_get(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        return response if response.status_code == 200 else None
    except Exception as e:
        print(f"Erro HTTP {url}: {e}")
        return None

def get_latest_version() -> str:
    try:
        response = http_get(VERSIONS_URL, timeout=10)
        if response:
            versions = response.json()
            if versions and len(versions) > 0:
                old_version = versions[0]
                parts = old_version.split(".")
                if len(parts) >= 2:
                    patch_num = parts[1]
                    return f"25-{patch_num.zfill(2)}"
        
        # Fallback baseado na data
        now = datetime.datetime.now()
        month = now.month
        estimated_patch = min(month * 2, 24)
        return f"25-{estimated_patch:02d}"
        
    except Exception as e:
        print(f"Erro ao buscar versão: {e}")
        return "25-16"

# =========================
# Busca da Imagem de Resumo
# =========================

def find_riot_summary_image(soup: BeautifulSoup) -> Optional[str]:
    """Encontra especificamente a imagem de resumo oficial da Riot"""
    
    print("[IMAGE] Procurando imagem de resumo...")
    
    all_images = soup.find_all("img", src=True)
    print(f"[IMAGE] Encontradas {len(all_images)} imagens no total")
    
    candidates = []
    
    for img in all_images:
        src = img.get("src", "")
        alt = img.get("alt", "").lower()
        
        # Garante URL completa
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.leagueoflegends.com" + src
        elif not src.startswith("http"):
            continue
            
        # Palavras-chave que indicam imagem de resumo
        summary_keywords = [
            "summary", "resumo", "infographic", "infografia",
            "nerfs", "buffs", "ajustes", "changes", "patch-notes",
            "overview", "visao-geral", "highlights", "destaques"
        ]
        
        # Verifica se é uma imagem de alta qualidade
        is_high_res = any(res in src.lower() for res in ["1920", "1200", "1080", "large", "full"])
        
        # Verifica palavras-chave no src e alt
        has_keywords = any(keyword in src.lower() or keyword in alt for keyword in summary_keywords)
        
        # Verifica se é uma imagem relacionada ao patch
        is_patch_related = "patch" in src.lower() or "patch" in alt
        
        # Sistema de pontuação
        score = 0
        if has_keywords:
            score += 10
        if is_high_res:
            score += 5
        if is_patch_related:
            score += 3
        if ".png" in src.lower():
            score += 2
        if "champion" not in src.lower():
            score += 1
            
        if score > 0:
            candidates.append((score, src, alt))
    
    # Ordena por pontuação
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    if candidates:
        best_image = candidates[0][1]
        print(f"[IMAGE] Melhor imagem selecionada: {best_image}")
        return best_image
    
    print("[IMAGE] Nenhuma imagem de resumo encontrada")
    return None

def get_patch_info(version: str) -> Optional[dict]:
    """Busca informações do patch"""
    
    # Tenta PT-BR primeiro
    url_pt = BASE_PATCH_URL_PT.format(version)
    response = http_get(url_pt)
    
    if response:
        soup = BeautifulSoup(response.content, "html.parser")
        image = find_riot_summary_image(soup)
        return {
            "version": version,
            "url": url_pt,
            "image": image,
            "lang": "PT-BR"
        }
    
    # Tenta EN como fallback
    url_en = BASE_PATCH_URL_EN.format(version)
    response = http_get(url_en)
    
    if response:
        soup = BeautifulSoup(response.content, "html.parser")
        image = find_riot_summary_image(soup)
        return {
            "version": version,
            "url": url_en,
            "image": image,
            "lang": "EN"
        }
    
    return None

# =========================
# Envio de Mensagem
# =========================

async def send_patch_simple(channel, patch_info):
    """Envia patch de forma super simples - só imagem + link"""
    
    if not patch_info["image"]:
        await channel.send(f"**Patch {patch_info['version']} disponível!**\nVer patch: <{patch_info['url']}>")
        return
    
    # Mensagem simples sem embed
    message = f"**Patch {patch_info['version']} - League of Legends**\n\n"
    
    # Envia a imagem diretamente
    await channel.send(message)
    await channel.send(patch_info["image"])
    
    # Link separado
    link_msg = f"Ver patch completo: <{patch_info['url']}>\n"
    link_msg += f"Idioma: {patch_info['lang']}"
    
    await channel.send(link_msg)

# =========================
# Eventos do Bot
# =========================

@bot.event
async def on_ready():
    global versao_atual
    
    print(f"[BOT] Conectado como {bot.user}")
    print(f"[BOT] ID: {bot.user.id}")
    print(f"[BOT] Conectado a {len(bot.guilds)} servidor(es)")
    
    for guild in bot.guilds:
        print(f"  - {guild.name} (id: {guild.id})")
    
    load_config()
    versao_atual = get_latest_version()
    print(f"[BOT] Versão atual: {versao_atual}")
    
    if config.get("canal_id"):
        if not monitor_patches.is_running():
            monitor_patches.start()
        print("[BOT] Monitoramento automático ativo")
    else:
        print("[BOT] Canal não configurado - use !config #canal")
    
    print(f"[BOT] Pronto! Use {PREFIX}patch para testar")

@bot.event
async def on_command_error(ctx, error):
    """Trata erros de comandos"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Você não tem permissão para usar este comando!")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("Canal não encontrado!")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"Erro: {str(error)}")
        print(f"[ERROR] {error}")

# =========================
# Comandos
# =========================

@bot.command(name="patch")
async def cmd_patch(ctx):
    """Busca patch mais recente"""
    await ctx.send("Buscando patch mais recente...")
    
    version = get_latest_version()
    patch_info = get_patch_info(version)
    
    if patch_info:
        await send_patch_simple(ctx.channel, patch_info)
    else:
        await ctx.send(f"Patch {version} não encontrado!")

@bot.command(name="teste")
@commands.has_permissions(administrator=True)
async def cmd_test(ctx, version: str = None):
    """Testa versão específica"""
    if not version:
        version = get_latest_version()
        
    await ctx.send(f"Testando {version}...")
    
    patch_info = get_patch_info(version)
    if patch_info:
        await send_patch_simple(ctx.channel, patch_info)
    else:
        await ctx.send(f"Patch {version} não encontrado!")

@bot.command(name="config")
@commands.has_permissions(administrator=True) 
async def cmd_config(ctx, canal: discord.TextChannel):
    """Configura canal automático"""
    config["canal_id"] = canal.id
    save_config()
    
    await ctx.send(f"Canal configurado: {canal.mention}")
    
    if not monitor_patches.is_running():
        monitor_patches.start()
        await ctx.send("Monitoramento iniciado!")

@bot.command(name="versao")
async def cmd_version(ctx):
    """Versão atual"""
    version = get_latest_version()
    await ctx.send(f"Versão: **{version}**")

@bot.command(name="status")
async def cmd_status(ctx):
    """Status do bot"""
    canal_id = config.get("canal_id")
    canal_nome = "Não configurado"
    
    if canal_id:
        canal = bot.get_channel(canal_id)
        canal_nome = canal.mention if canal else f"ID {canal_id} (não encontrado)"
    
    status_msg = f"""**Status do Bot**
    
**Bot:** Online
**Servidores:** {len(bot.guilds)}
**Versão atual:** {versao_atual or 'N/A'}
**Canal configurado:** {canal_nome}
**Monitoramento:** {'Ativo' if monitor_patches.is_running() else 'Inativo'}

Use `!config #canal` para configurar"""
    
    await ctx.send(status_msg)

@bot.command(name="help")
async def cmd_help(ctx):
    """Comandos disponíveis"""
    help_text = f"""**Bot Patch Notes LoL**

**Comandos:**
• `{PREFIX}patch` - Busca patch mais recente
• `{PREFIX}versao` - Versão atual do jogo  
• `{PREFIX}status` - Status do bot
• `{PREFIX}config #canal` - Configura canal (Admin)
• `{PREFIX}teste [versao]` - Testa patch específico (Admin)

**Automático:**
• Monitora novos patches a cada 30 min
• Envia imagem de resumo + link"""
    
    await ctx.send(help_text)

# =========================
# Monitoramento Automático
# =========================

@tasks.loop(minutes=30)
async def monitor_patches():
    """Monitora patches automaticamente"""
    global versao_atual
    
    try:
        canal_id = config.get("canal_id")
        if not canal_id:
            return
            
        canal = bot.get_channel(canal_id)
        if not canal:
            print(f"[MONITOR] Canal {canal_id} não encontrado")
            return
        
        nova_versao = get_latest_version()
        if versao_atual != nova_versao:
            print(f"[MONITOR] Nova versão: {versao_atual} -> {nova_versao}")
            
            patch_info = get_patch_info(nova_versao)
            if patch_info:
                await canal.send("**Novo patch detectado!**")
                await send_patch_simple(canal, patch_info)
                versao_atual = nova_versao
                print(f"[MONITOR] Patch {nova_versao} enviado")
            else:
                print(f"[MONITOR] Falha ao buscar patch {nova_versao}")
                
    except Exception as e:
        print(f"[MONITOR] Erro: {e}")

@monitor_patches.before_loop
async def before_monitor():
    await bot.wait_until_ready()

# =========================
# Execução
# =========================

if __name__ == "__main__":
    try:
        print("Iniciando bot...")
        print(f"Comandos: {PREFIX}patch, {PREFIX}config #canal")
        print("="*50)
        
        bot.run(TOKEN)
        
    except KeyboardInterrupt:
        print("\nBot interrompido pelo usuário")
    except Exception as e:
        print(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Bot finalizado!")
