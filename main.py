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
from dotenv import load_dotenv

# =========================
# Configuração
# =========================

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("❌ TOKEN não encontrado!")
    print("📝 Configure a variável TOKEN nas configurações do Railway")
    exit(1)

# URLs
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
BASE_PATCH_URL_PT = "https://www.leagueoflegends.com/pt-br/news/game-updates/patch-{}-notes/"
BASE_PATCH_URL_EN = "https://www.leagueoflegends.com/en-us/news/game-updates/patch-{}-notes/"

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Estado
config = {"canal_id": None}
versao_atual = None
CONFIG_FILE = "config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# =========================
# Funções Básicas
# =========================

def load_config():
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
    except:
        pass

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except:
        pass

def http_get(url: str) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        return response if response.status_code == 200 else None
    except:
        return None

def get_latest_version() -> str:
    try:
        response = http_get(VERSIONS_URL)
        if response:
            versions = response.json()
            if versions:
                old_version = versions[0]
                parts = old_version.split(".")
                if len(parts) >= 2:
                    patch_num = parts[1]
                    return f"25-{patch_num.zfill(2)}"
        return "25-16"  # fallback
    except:
        return "25-16"

# =========================
# Busca da Imagem de Resumo
# =========================

def find_riot_summary_image(soup: BeautifulSoup) -> Optional[str]:
    """Encontra ESPECIFICAMENTE a imagem de resumo oficial da Riot"""
    
    print("[IMAGE] Procurando imagem de resumo...")
    
    # Lista todas as imagens da página
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
        
        # Verifica se é uma imagem de alta qualidade (resolução grande)
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
        if "champion" not in src.lower():  # Evita imagens individuais de campeões
            score += 1
            
        if score > 0:
            candidates.append((score, src, alt))
            print(f"[IMAGE] Candidata encontrada (score {score}): {src}")
    
    # Ordena por pontuação (maior primeiro)
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
    
    # Mensagem simples sem embed para evitar preview automático
    message = f"**🎮 Patch {patch_info['version']} - League of Legends**\n\n"
    
    # Envia a imagem diretamente
    await channel.send(message)
    await channel.send(patch_info["image"])
    
    # Link separado para evitar preview
    link_msg = f"📋 **Ver patch completo:** <{patch_info['url']}>\n"
    link_msg += f"🌐 Idioma: {patch_info['lang']}"
    
    await channel.send(link_msg)

# =========================
# Eventos e Comandos
# =========================

@bot.event
async def on_ready():
    global versao_atual
    
    print(f"[BOT] Conectado como {bot.user}")
    load_config()
    versao_atual = get_latest_version()
    print(f"[BOT] Versão atual: {versao_atual}")
    
    if config.get("canal_id"):
        if not monitor_patches.is_running():
            monitor_patches.start()
        print("[BOT] Monitoramento ativo")
    
    print(f"[BOT] Pronto! Use {PREFIX}patch para testar")

@bot.command(name="patch")
async def cmd_patch(ctx):
    """Busca patch mais recente"""
    await ctx.send("🔍 Buscando patch...")
    
    version = get_latest_version()
    patch_info = get_patch_info(version)
    
    if patch_info:
        await send_patch_simple(ctx.channel, patch_info)
    else:
        await ctx.send(f"❌ Patch {version} não encontrado!")

@bot.command(name="teste")
@commands.has_permissions(administrator=True)
async def cmd_test(ctx, version: str = None):
    """Testa versão específica"""
    if not version:
        version = get_latest_version()
        
    await ctx.send(f"🧪 Testando {version}...")
    
    patch_info = get_patch_info(version)
    if patch_info:
        await send_patch_simple(ctx.channel, patch_info)
    else:
        await ctx.send(f"❌ Patch {version} não encontrado!")

@bot.command(name="config")
@commands.has_permissions(administrator=True) 
async def cmd_config(ctx, canal: discord.TextChannel):
    """Configura canal automático"""
    config["canal_id"] = canal.id
    save_config()
    
    await ctx.send(f"✅ Canal configurado: {canal.mention}")
    
    if not monitor_patches.is_running():
        monitor_patches.start()
        await ctx.send("🤖 Monitoramento iniciado!")

@bot.command(name="versao")
async def cmd_version(ctx):
    """Versão atual"""
    version = get_latest_version()
    await ctx.send(f"📌 Versão: **{version}**")

@bot.command(name="help")
async def cmd_help(ctx):
    """Comandos disponíveis"""
    help_text = f"""**🤖 Bot Patch Notes LoL**

**Comandos:**
• `{PREFIX}patch` - Busca patch mais recente
• `{PREFIX}versao` - Versão atual do jogo  
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
    
    canal_id = config.get("canal_id")
    if not canal_id:
        return
        
    canal = bot.get_channel(canal_id)
    if not canal:
        return
    
    nova_versao = get_latest_version()
    if versao_atual != nova_versao:
        print(f"[MONITOR] Nova versão: {nova_versao}")
        
        patch_info = get_patch_info(nova_versao)
        if patch_info:
            await canal.send("🎉 **Novo patch detectado!**")
            await send_patch_simple(canal, patch_info)
            versao_atual = nova_versao

@monitor_patches.before_loop
async def before_monitor():
    await bot.wait_until_ready()

# =========================
# Execução
# =========================

if __name__ == "__main__":
    try:
        print("🚀 Iniciando bot simplificado...")
        print(f"Comandos: {PREFIX}patch, {PREFIX}config #canal")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erro: {e}")
