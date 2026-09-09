import asyncio
from datetime import datetime
from itertools import cycle
import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
import psycopg2
import pytz

# ==========================================
# CONFIGURATION
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")

# IDs des rôles autorisés à utiliser les commandes admin
WHITELIST_ROLES = [
    1534255113806286922, 1521132294360924294, 1521132533369016330,
    1521132636813262958, 1521132747735826545, 1521132820385235004,
    1521132894104322188, 1521132972731007036
]

# ID du rôle automatique attribué aux nouveaux arrivants (0 pour désactiver)
AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "1528963080900317315"))

# ID du salon de logs (0 pour désactiver)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1546764469143863377"))

# ID de la catégorie pour les tickets
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1534251260310458418"))

# ID du salon pour le message programmé du vendredi après-midi
SCHEDULED_CHANNEL_ID = int(os.getenv("SCHEDULED_CHANNEL_ID", "0"))

# Configuration Twitch
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "bnuvv5q05hd6g28wh9t2k5edztiws5")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "f3og2xaiezsjegbbtvq2bpiy6zc9ot")
TWITCH_STREAMER_NAME = os.getenv("TWITCH_STREAMER_NAME", "jerushenpuntoo")
TWITCH_DISCORD_CHANNEL_ID = int(os.getenv("TWITCH_DISCORD_CHANNEL_ID", "1547199636660555796"))

# Fuseau horaire Paris/Europe
PARIS_TZ = pytz.timezone("Europe/Paris")

# ==========================================
# BASE DE DONNÉES
# ==========================================

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("❌ La variable DATABASE_URL n'est pas configurée sur Railway.")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS membres (
        discord_id TEXT PRIMARY KEY, nom TEXT, grade TEXT DEFAULT 'Soldat',
        specialite TEXT DEFAULT 'Assaulteur', date_entree TEXT,
        opex_count INTEGER DEFAULT 0, note_total DOUBLE PRECISION DEFAULT 0,
        note_count INTEGER DEFAULT 0, distinctions TEXT DEFAULT ''
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS opex (
        id SERIAL PRIMARY KEY, discord_id TEXT, nom_opex TEXT,
        note DOUBLE PRECISION, commentaire TEXT, date TEXT, noter_par TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS absences (
        id SERIAL PRIMARY KEY, discord_id TEXT, raison TEXT,
        duree TEXT, date_declaration TEXT, actif BOOLEAN DEFAULT TRUE
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS opex_officielles (
        id SERIAL PRIMARY KEY, nom_opex TEXT UNIQUE,
        date_opex TEXT, cree_par TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS opex_inscriptions (
        id SERIAL PRIMARY KEY, nom_opex TEXT, discord_id TEXT,
        date_inscription TEXT, UNIQUE(nom_opex, discord_id)
    )""")
    
    conn.commit()
    conn.close()

def get_membre(discord_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM membres WHERE discord_id = %s", (str(discord_id),))
    row = c.fetchone()
    conn.close()
    return row

def create_membre(discord_id, nom):
    conn = get_db_connection()
    c = conn.cursor()
    date_entree = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")
    c.execute("INSERT INTO membres (discord_id, nom, date_entree) VALUES (%s, %s, %s) ON CONFLICT (discord_id) DO NOTHING", (str(discord_id), nom, date_entree))
    conn.commit()
    conn.close()

def get_absence_active(discord_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT raison, duree, date_declaration FROM absences WHERE discord_id = %s AND actif = TRUE ORDER BY id DESC LIMIT 1", (str(discord_id),))
    row = c.fetchone()
    conn.close()
    return row

def is_admin(ctx_or_interaction) -> bool:
    user = ctx_or_interaction.user if hasattr(ctx_or_interaction, "user") else ctx_or_interaction.author
    if WHITELIST_ROLES:
        user_role_ids = [r.id for r in user.roles]
        return any(role_id in user_role_ids for role_id in WHITELIST_ROLES)
    return user.guild_permissions.manage_roles

async def send_log(bot_instance, message: str):
    if LOG_CHANNEL_ID:
        channel = bot_instance.get_channel(LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="📋 Log GCP Bot",
                description=message,
                color=0x2C2F33,
                timestamp=datetime.now(PARIS_TZ)
            )
            await channel.send(embed=embed)

# ==========================================
# BOT & INITIALISATION
# ==========================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# STATUTS ROTATIFS
status_list = cycle([
    discord.Game(name="GCP | /aide"),
    discord.Activity(type=discord.ActivityType.watching, name="Kain FAVEL le meilleur Colonel"),
    discord.Game(name="Qui ose gagne 🇫🇷")
])

twitch_is_live = False

# ==========================================
# ÉVÉNEMENTS & TÂCHES
# ==========================================

@bot.event
async def on_member_join(member: discord.Member):
    if AUTO_ROLE_ID:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
                await send_log(bot, f"👤 **{member.display_name}** a rejoint le serveur et a reçu le rôle **{role.name}**.")
            except discord.Forbidden:
                print(f"❌ Impossible d'attribuer le rôle à {member.display_name} (permissions insuffisantes).")

@tasks.loop(minutes=5)
async def rotate_status():
    await bot.change_presence(activity=next(status_list))

@tasks.loop(hours=1)
async def scheduled_friday_message():
    now = datetime.now(PARIS_TZ)
    if now.weekday() == 4 and now.hour == 17:
        if SCHEDULED_CHANNEL_ID:
            channel = bot.get_channel(SCHEDULED_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="📢 Briefing du Week-End — GCP",
                    description=(
                        "Opérateurs du GCP,\n\n"
                        "C'est le début du week-end ! Pensez à vérifier vos inscriptions aux OPEX à venir via `/liste_inscrits` "
                        "et à vous inscrire avec `/inscrire_opex` si ce n'est pas déjà fait.\n\n"
                        "Restez vigilants et tenez-vous prêts pour les déploiements !"
                    ),
                    color=0x00FF00
                )
                embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
                await channel.send(embed=embed)

async def get_twitch_access_token(session):
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    url = f"https://id.twitch.tv/oauth2/token?client_id={TWITCH_CLIENT_ID}&client_secret={TWITCH_CLIENT_SECRET}&grant_type=client_credentials"
    async with session.post(url) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("access_token")
    return None

@tasks.loop(minutes=2)
async def check_twitch_live():
    global twitch_is_live
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET and TWITCH_STREAMER_NAME and TWITCH_DISCORD_CHANNEL_ID):
        return

    async with aiohttp.ClientSession() as session:
        token = await get_twitch_access_token(session)
        if not token:
            return

        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}"
        }
        url = f"https://api.twitch.tv/helix/streams?user_login={TWITCH_STREAMER_NAME}"
        
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    streams = data.get("data", [])
                    if streams:
                        if not twitch_is_live:
                            twitch_is_live = True
                            stream_data = streams[0]
                            title = stream_data.get("title", "En live !")
                            game_name = stream_data.get("game_name", "Jeu non spécifié")
                            
                            channel = bot.get_channel(TWITCH_DISCORD_CHANNEL_ID)
                            if channel:
                                embed = discord.Embed(
                                    title=f"🔴 {TWITCH_STREAMER_NAME} est en LIVE sur Twitch !",
                                    url=f"https://twitch.tv/{TWITCH_STREAMER_NAME}",
                                    description=f"**{title}**\n\n🎮 **Jeu :** {game_name}",
                                    color=0x9146FF,
                                    timestamp=datetime.now(PARIS_TZ)
                                )
                                embed.set_footer(text="GCP Twitch Alert • Qui ose gagne.")
                                await channel.send(content=f"📢 **Alerte Live !** Retrouvez le stream ici : https://twitch.tv/{TWITCH_STREAMER_NAME}", embed=embed)
                    else:
                        twitch_is_live = False
        except Exception as e:
            print(f"Erreur vérification Twitch : {e}")

@bot.event
async def on_ready():
    init_db()
    if not scheduled_friday_message.is_running():
        scheduled_friday_message.start()
    if not rotate_status.is_running():
        rotate_status.start()
    if not check_twitch_live.is_running():
        check_twitch_live.start()
    await tree.sync()
    print(f"✅ Bot GCP connecté : {bot.user}")

# ==========================================
# COMMANDES DU BOT
# ==========================================

@bot.command()
async def sync(ctx):
    if not is_admin(ctx):
        return
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ **{len(synced)}** commandes slash synchronisées instantanément sur ce serveur !")

@tree.command(name="en dev", description="en dev")
@app_commands.describe(membre="Le membre à qui adresser le guide")
async def guide(interaction: discord.Interaction, membre: discord.Member):
    embed = discord.Embed(
        title="en dev",
        description=(
            f"en dev"
            
        ),
        color=0x3498DB
    )
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(content=f"👋 {membre.mention}, voici le guide de l'unité :", embed=embed)

@tree.command(name="en dev", description="en dev")
@app_commands.describe(membre="Le membre concerné")
async def reglement(interaction: discord.Interaction, membre: discord.Member):
    embed = discord.Embed(
        title="en dev",
        description=(
            f"en dev"
            
        ),
        color=0xE74C3C
    )
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(content=f"📢 {membre.mention}, merci de relire le règlement :", embed=embed)

@tree.command(name="profil", description="Affiche le profil d'un membre du GCP")
@app_commands.describe(membre="Le membre dont tu veux voir le profil")
async def profil(interaction: discord.Interaction, membre: discord.Member = None):
    if membre is None:
        membre = interaction.user

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message(f"❌ {membre.display_name} n'est pas encore enregistré.", ephemeral=True)
        return

    discord_id, nom, grade, specialite, date_entree, opex_count, note_total, note_count, distinctions = row
    note_moyenne = round(note_total / note_count, 2) if note_count > 0 else "Aucune note"
    distinctions_list = distinctions if distinctions else "Aucune"

    embed = discord.Embed(title=f"🪖 Dossier Opérationnel — {nom}", color=0x2C2F33)
    embed.set_thumbnail(url=membre.display_avatar.url)
    
    absence = get_absence_active(membre.id)
    if absence:
        raison, duree, date_decl = absence
        embed.add_field(
            name="🚨 Statut Opérationnel",
            value=f"**ABSENT**\n**Raison :** {raison}\n**Durée :** {duree}\n*(Déclarée le {date_decl})*",
            inline=False
        )
    else:
        embed.add_field(name="🚨 Statut Opérationnel", value="🟢 **ACTIF**", inline=False)

    embed.add_field(name="🎖️ Grade", value=grade, inline=True)
    embed.add_field(name="⚔️ Spécialité", value=specialite, inline=True)
    embed.add_field(name="📅 Entrée dans l'unité", value=date_entree, inline=True)
    embed.add_field(name="🗺️ Opex effectuées", value=str(opex_count), inline=True)
    embed.add_field(name="⭐ Note moyenne", value=str(note_moyenne), inline=True)
    embed.add_field(name="🏅 Distinctions", value=distinctions_list, inline=False)
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")

    await interaction.response.send_message(embed=embed)

@tree.command(name="enregistrer", description="Enregistre un nouveau membre dans la base GCP")
@app_commands.describe(membre="Le membre à enregistrer", nom="Nom complet (ex: Jean DUPONT)")
async def enregistrer(interaction: discord.Interaction, membre: discord.Member, nom: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    create_membre(membre.id, nom)
    await interaction.response.send_message(f"✅ **{nom}** a été enregistré dans la base de données GCP.")
    await send_log(bot, f"➕ **{interaction.user.display_name}** a enregistré **{nom}**")

@tree.command(name="modifier", description="Modifier le profil d'un membre")
@app_commands.describe(
    membre="Le membre à modifier",
    grade="Nouveau grade",
    specialite="Nouvelle spécialité",
    distinctions="Distinctions (remplace les existantes)",
    date_entree="Date d'entrée (format JJ/MM/AAAA)",
    opex_count="Nombre d'opex effectuées"
)
async def modifier(interaction: discord.Interaction, membre: discord.Member,
                   grade: str = None, specialite: str = None, distinctions: str = None,
                   date_entree: str = None, opex_count: int = None):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    changements = []

    if grade:
        c.execute("UPDATE membres SET grade = %s WHERE discord_id = %s", (grade, str(membre.id)))
        changements.append(f"Grade → **{grade}**")
    if specialite:
        c.execute("UPDATE membres SET specialite = %s WHERE discord_id = %s", (specialite, str(membre.id)))
        changements.append(f"Spécialité → **{specialite}**")
    if distinctions:
        c.execute("UPDATE membres SET distinctions = %s WHERE discord_id = %s", (distinctions, str(membre.id)))
        changements.append(f"Distinctions → **{distinctions}**")
    if date_entree:
        c.execute("UPDATE membres SET date_entree = %s WHERE discord_id = %s", (date_entree, str(membre.id)))
        changements.append(f"Date d'entrée → **{date_entree}**")
    if opex_count is not None:
        c.execute("UPDATE membres SET opex_count = %s WHERE discord_id = %s", (opex_count, str(membre.id)))
        changements.append(f"Opex effectuées → **{opex_count}**")

    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Profil de **{membre.display_name}** mis à jour.")
    if changements:
        await send_log(bot, f"✏️ **{interaction.user.display_name}** a modifié le profil de **{membre.display_name}** :\n" + "\n".join(changements))

@tree.command(name="ajouter_distinction", description="Ajouter une distinction sans écraser les existantes")
@app_commands.describe(membre="Le membre", distinction="La distinction à ajouter")
async def ajouter_distinction(interaction: discord.Interaction, membre: discord.Member, distinction: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    distinctions_actuelles = row[8]
    nouvelles = f"{distinctions_actuelles}, {distinction}" if distinctions_actuelles else distinction

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE membres SET distinctions = %s WHERE discord_id = %s", (nouvelles, str(membre.id)))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Distinction **{distinction}** ajoutée à **{membre.display_name}**.")
    await send_log(bot, f"🏅 **{interaction.user.display_name}** a ajouté la distinction **{distinction}** à **{membre.display_name}**")

@tree.command(name="retirer_distinction", description="Retirer une distinction spécifique à un membre")
@app_commands.describe(membre="Le membre concerné", distinction="La distinction à retirer")
async def retirer_distinction(interaction: discord.Interaction, membre: discord.Member, distinction: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    distinctions_actuelles = row[8]
    if not distinctions_actuelles:
        await interaction.response.send_message(f"❌ **{membre.display_name}** n'a aucune distinction enregistrée.", ephemeral=True)
        return

    liste_distinctions = [d.strip() for d in distinctions_actuelles.split(",") if d.strip()]
    trouve = False
    nouvelle_liste = []
    for d in liste_distinctions:
        if not trouve and d.lower() == distinction.strip().lower():
            trouve = True
        else:
            nouvelle_liste.append(d)

    if not trouve:
        await interaction.response.send_message(
            f"❌ La distinction **{distinction}** n'a pas été trouvée pour **{membre.display_name}**.\n"
            f"**Distinctions actuelles :** {distinctions_actuelles}",
            ephemeral=True
        )
        return

    nouvelles = ", ".join(nouvelle_liste)

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE membres SET distinctions = %s WHERE discord_id = %s", (nouvelles, str(membre.id)))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Distinction **{distinction}** retirée à **{membre.display_name}**.")
    await send_log(bot, f"🗑️ **{interaction.user.display_name}** a retiré la distinction **{distinction}** à **{membre.display_name}**")

@tree.command(name="noter", description="Noter un membre après une opex")
@app_commands.describe(membre="Le membre à noter", opex="Nom de l'opération", note="Note de 0 à 10", commentaire="Commentaire optionnel")
async def noter(interaction: discord.Interaction, membre: discord.Member, opex: str, note: float, commentaire: str = ""):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    if note < 0 or note > 10:
        await interaction.response.send_message("❌ La note doit être entre 0 et 10.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    date = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")

    c.execute("INSERT INTO opex (discord_id, nom_opex, note, commentaire, date, noter_par) VALUES (%s, %s, %s, %s, %s, %s)",
              (str(membre.id), opex, note, commentaire, date, str(interaction.user.display_name)))
    c.execute("UPDATE membres SET opex_count = opex_count + 1, note_total = note_total + %s, note_count = note_count + 1 WHERE discord_id = %s",
              (note, str(membre.id)))

    conn.commit()
    conn.close()

    embed = discord.Embed(title="📋 Notation enregistrée", color=0x2C2F33)
    embed.add_field(name="Membre", value=membre.display_name, inline=True)
    embed.add_field(name="Opération", value=opex, inline=True)
    embed.add_field(name="Note", value=f"{note}/10", inline=True)
    if commentaire:
        embed.add_field(name="Commentaire", value=commentaire, inline=False)
    embed.set_footer(text=f"Noté par {interaction.user.display_name} • {date}")

    await interaction.response.send_message(embed=embed)
    await send_log(bot, f"⭐ **{interaction.user.display_name}** a noté **{membre.display_name}** — {opex} : **{note}/10**" + (f"\n_{commentaire}_" if commentaire else ""))

@tree.command(name="supprimer_note", description="Supprimer la dernière notation d'un membre")
@app_commands.describe(membre="Le membre dont supprimer la dernière note")
async def supprimer_note(interaction: discord.Interaction, membre: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, note FROM opex WHERE discord_id = %s ORDER BY id DESC LIMIT 1", (str(membre.id),))
    row = c.fetchone()

    if not row:
        await interaction.response.send_message("❌ Aucune notation trouvée pour ce membre.", ephemeral=True)
        conn.close()
        return

    opex_id, note = row
    c.execute("DELETE FROM opex WHERE id = %s", (opex_id,))
    c.execute("UPDATE membres SET opex_count = opex_count - 1, note_total = note_total - %s, note_count = note_count - 1 WHERE discord_id = %s",
              (note, str(membre.id)))

    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Dernière notation de **{membre.display_name}** supprimée.")
    await send_log(bot, f"🗑️ **{interaction.user.display_name}** a supprimé la dernière notation de **{membre.display_name}** (note : {note}/10)")

@tree.command(name="historique", description="Voir l'historique des opex d'un membre")
@app_commands.describe(membre="Le membre dont tu veux voir l'historique")
async def historique(interaction: discord.Interaction, membre: discord.Member = None):
    if membre is None:
        membre = interaction.user

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nom_opex, note, commentaire, date, noter_par FROM opex WHERE discord_id = %s ORDER BY id DESC LIMIT 10", (str(membre.id),))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(f"Aucune opex enregistrée pour {membre.display_name}.")
        return

    embed = discord.Embed(title=f"🗺️ Historique opex — {membre.display_name}", color=0x2C2F33)
    for r in rows:
        nom_opex, note, commentaire, date, noter_par = r
        valeur = f"Note : **{note}/10**"
        if commentaire:
            valeur += f"\n_{commentaire}_"
        valeur += f"\nNoté par {noter_par} le {date}"
        embed.add_field(name=f"🔴 {nom_opex}", value=valeur, inline=False)

    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed)

@tree.command(name="classement", description="Affiche le classement des membres par note moyenne")
async def classement(interaction: discord.Interaction):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT nom, grade, opex_count,
        CASE WHEN note_count > 0 THEN ROUND(note_total / note_count, 2) ELSE 0 END as moyenne
        FROM membres
        WHERE note_count > 0
        ORDER BY moyenne DESC
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("Aucun membre noté pour le moment.")
        return

    embed = discord.Embed(title="🏆 Classement GCP — Note moyenne", color=0x2C2F33)
    medals = ["🥇", "🥈", "🥉"]

    for i, (nom, grade, opex_count, moyenne) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        embed.add_field(name=f"{prefix} {nom}", value=f"**{grade}** • {opex_count} opex • Moyenne : **{moyenne}/10**", inline=False)

    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed)

@tree.command(name="stats", description="Statistiques globales de l'unité GCP")
async def stats(interaction: discord.Interaction):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM membres")
    nb_membres = c.fetchone()[0]
    c.execute("SELECT SUM(opex_count) FROM membres")
    nb_opex = c.fetchone()[0] or 0
    c.execute("SELECT ROUND(AVG(note_total / note_count), 2) FROM membres WHERE note_count > 0")
    moyenne_generale = c.fetchone()[0] or "N/A"
    c.execute("SELECT nom, grade FROM membres WHERE note_count > 0 ORDER BY (note_total / note_count) DESC LIMIT 1")
    meilleur = c.fetchone()
    conn.close()

    embed = discord.Embed(title="📊 Statistiques GCP", color=0x2C2F33)
    embed.add_field(name="👥 Membres enregistrés", value=str(nb_membres), inline=True)
    embed.add_field(name="🗺️ Opex totales", value=str(nb_opex), inline=True)
    embed.add_field(name="⭐ Moyenne générale", value=str(moyenne_generale), inline=True)
    if meilleur:
        embed.add_field(name="🏆 Meilleur opérateur", value=f"{meilleur[0]} ({meilleur[1]})", inline=False)
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")

    await interaction.response.send_message(embed=embed)

@tree.command(name="absent", description="Déclarer une absence officielle, visible sur le profil")
@app_commands.describe(raison="Motif de l'absence", duree="Durée estimée (ex: 3 jours, 1 semaine)", membre="Membre concerné (Laissez vide pour vous-même)")
async def absent(interaction: discord.Interaction, raison: str, duree: str, membre: discord.Member = None):
    target = membre if membre else interaction.user
    if membre and membre != interaction.user and not is_admin(interaction):
        await interaction.response.send_message("❌ Seul un administrateur peut déclarer l'absence d'un autre membre.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE absences SET actif = FALSE WHERE discord_id = %s", (str(target.id),))
    date_now = datetime.now(PARIS_TZ).strftime("%d/%m/%Y %H:%M")
    c.execute("INSERT INTO absences (discord_id, raison, duree, date_declaration, actif) VALUES (%s, %s, %s, %s, TRUE)",
              (str(target.id), raison, duree, date_now))
    conn.commit()
    conn.close()

    embed = discord.Embed(title="📌 Absence Officielle Déclarée", color=0xE74C3C)
    embed.add_field(name="Opérateur", value=target.mention, inline=True)
    embed.add_field(name="Durée", value=duree, inline=True)
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.set_footer(text=f"Déclarée le {date_now}")

    await interaction.response.send_message(embed=embed)
    await send_log(bot, f"🚨 **{interaction.user.display_name}** a déclaré une absence pour **{target.display_name}** (Raison: {raison}, Durée: {duree})")

@tree.command(name="fin_absence", description="Met fin à une absence officielle")
@app_commands.describe(membre="Membre concerné (Laissez vide pour vous-même)")
async def fin_absence(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre if membre else interaction.user
    if membre and membre != interaction.user and not is_admin(interaction):
        await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE absences SET actif = FALSE WHERE discord_id = %s", (str(target.id),))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ L'absence de **{target.display_name}** a été clôturée.")
    await send_log(bot, f"🟢 **{interaction.user.display_name}** a mis fin à l'absence de **{target.display_name}**")

@tree.command(name="creer_opex", description="Créer une opex officielle avec une fiche dédiée")
@app_commands.describe(nom="Nom officiel de l'OPEX", date="Date et heure prévues (ex: 15/10 à 2100h)")
async def creer_opex(interaction: discord.Interaction, nom: str, date: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        return

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO opex_officielles (nom_opex, date_opex, cree_par) VALUES (%s, %s, %s)",
                  (nom, date, str(interaction.user.display_name)))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.close()
        await interaction.response.send_message("❌ Une OPEX portant ce nom existe déjà.", ephemeral=True)
        return
    conn.close()

    embed = discord.Embed(title=f"🗺️ Nouvelle OPEX Créée : {nom}", color=0x3498DB)
    embed.add_field(name="📅 Date prévue", value=date, inline=True)
    embed.add_field(name="Créée par", value=interaction.user.display_name, inline=True)
    embed.set_footer(text="Inscrivez-vous via /inscrire_opex")

    await interaction.response.send_message(embed=embed)
    await send_log(bot, f"📌 **{interaction.user.display_name}** a créé l'OPEX officielle **{nom}** pour le {date}")

@tree.command(name="inscrire_opex", description="S'inscrire à une opex à venir")
@app_commands.describe(nom_opex="Nom de l'OPEX officielle")
async def inscrire_opex(interaction: discord.Interaction, nom_opex: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM opex_officielles WHERE nom_opex = %s", (nom_opex,))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message("❌ Cette OPEX n'existe pas.", ephemeral=True)
        return

    date_insc = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")
    try:
        c.execute("INSERT INTO opex_inscriptions (nom_opex, discord_id, date_inscription) VALUES (%s, %s, %s)",
                  (nom_opex, str(interaction.user.id), date_insc))
        conn.commit()
        await interaction.response.send_message(f"✅ Tu es bien inscrit à l'OPEX **{nom_opex}**.", ephemeral=True)
    except psycopg2.IntegrityError:
        await interaction.response.send_message("❌ Tu es déjà inscrit à cette OPEX.", ephemeral=True)
    finally:
        conn.close()

@tree.command(name="liste_inscrits", description="Voir qui est inscrit pour une opex")
@app_commands.describe(nom_opex="Nom de l'OPEX officielle")
async def liste_inscrits(interaction: discord.Interaction, nom_opex: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT discord_id, date_inscription FROM opex_inscriptions WHERE nom_opex = %s", (nom_opex,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(f"Aucun inscrit trouvé pour l'OPEX **{nom_opex}**.")
        return

    embed = discord.Embed(title=f"📋 Liste des inscrits — OPEX {nom_opex}", color=0x2C2F33)
    inscrits_text = ""
    for idx, (disc_id, date_i) in enumerate(rows, 1):
        membre = interaction.guild.get_member(int(disc_id))
        nom_aff = membre.display_name if membre else f"ID: {disc_id}"
        inscrits_text += f"**{idx}.** {nom_aff} *(Inscrit le {date_i})*\n"

    embed.description = inscrits_text
    embed.set_footer(text=f"Total inscrits : {len(rows)}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="recap_opex", description="Afficher toutes les notes d'une opex spécifique")
@app_commands.describe(nom_opex="Nom de l'OPEX")
async def recap_opex(interaction: discord.Interaction, nom_opex: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT discord_id, note, commentaire, noter_par, date FROM opex WHERE nom_opex = %s", (nom_opex,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(f"Aucune note enregistrée pour l'OPEX **{nom_opex}**.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📊 Récapitulatif des notes — {nom_opex}", color=0xF1C40F)
    for disc_id, note, comm, noter_par, date in rows:
        m = interaction.guild.get_member(int(disc_id))
        nom = m.display_name if m else f"ID {disc_id}"
        valeur = f"Note : **{note}/10**\nNoté par : {noter_par} le {date}"
        if comm:
            valeur += f"\n_{comm}_"
        embed.add_field(name=f"👤 {nom}", value=valeur, inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="ticket", description="Ouvrir un ticket auprès du staff")
@app_commands.describe(raison="Description succincte de la demande")
async def ticket(interaction: discord.Interaction, raison: str):
    guild = interaction.guild
    category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    for role_id in WHITELIST_ROLES:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel_name = f"ticket-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(
        name=channel_name, category=category, overwrites=overwrites, reason=f"Ticket ouvert par {interaction.user.name}"
    )

    embed = discord.Embed(
        title=f"🎟️ Ticket de {interaction.user.display_name}",
        description=f"**Raison :** {raison}\n\nUn membre du Staff prendra en charge votre demande sous peu.",
        color=0x1ABC9C, timestamp=datetime.now(PARIS_TZ)
    )
    embed.set_footer(text="Utilisez /fermer_ticket pour clôturer le salon.")
    
    await ticket_channel.send(content=f"{interaction.user.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Ticket créé avec succès : {ticket_channel.mention}", ephemeral=True)
    await send_log(bot, f"🎟️ **{interaction.user.display_name}** a ouvert un ticket : {ticket_channel.mention} (Raison: {raison})")

@tree.command(name="fermer_ticket", description="Fermer et supprimer le ticket actuel")
async def fermer_ticket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ Cette commande ne peut être exécutée que dans un salon de ticket.", ephemeral=True)
        return

    await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
    await send_log(bot, f"🔒 Ticket **{interaction.channel.name}** fermé par **{interaction.user.display_name}**")
    await asyncio.sleep(5)
    await interaction.channel.delete()

@tree.command(name="config_whitelist", description="Affiche les rôles autorisés à utiliser les commandes admin")
async def config_whitelist(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrateur uniquement.", ephemeral=True)
        return

    if not WHITELIST_ROLES:
        msg = "Aucune whitelist configurée — les commandes admin sont accessibles aux membres avec **Gérer les rôles**."
    else:
        roles = [f"<@&{r}>" for r in WHITELIST_ROLES]
        msg = "Rôles autorisés : " + ", ".join(roles)

    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="aide", description="Liste toutes les commandes du bot GCP")
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 Commandes du Bot GCP", color=0x2C2F33)
    embed.add_field(
        name="👤 Membres",
        value=(
            "`/profil [@membre]` — Voir un profil\n"
            "`/guide @membre` — Envoyer le guide d'accueil\n"
            "`/reglement @membre` — Rappeler le règlement\n"
            "`/absent raison durée [@membre]` — Déclarer une absence\n"
            "`/fin_absence [@membre]` — Reprendre le service\n"
            "`/inscrire_opex nom_opex` — S'inscrire à une OPEX\n"
            "`/liste_inscrits nom_opex` — Inscrits à une OPEX\n"
            "`/ticket raison` — Ouvrir un ticket au Staff\n"
            "`/historique [@membre]` — Historique opex\n"
            "`/classement` — Top membres\n"
            "`/stats` — Statistiques de l'unité"
        ),
        inline=False
    )
    embed.add_field(
        name="🔐 Gradés / Staff",
        value=(
            "`!sync` — Synchroniser instantanément les commandes slash\n"
            "`/creer_opex nom date` — Créer une OPEX officielle\n"
            "`/recap_opex nom_opex` — Résumé des notes d'une OPEX\n"
            "`/enregistrer @membre nom` — Enregistrer un membre\n"
            "`/modifier @membre` — Modifier grade/spécialité/date/opex\n"
            "`/ajouter_distinction @membre distinction` — Ajouter une distinction\n"
            "`/retirer_distinction @membre distinction` — Retirer une distinction\n"
            "`/noter @membre opex note` — Noter après une opex\n"
            "`/supprimer_note @membre` — Supprimer la dernière note\n"
            "`/fermer_ticket` — Clôturer un ticket"
        ),
        inline=False
    )
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# LANCEMENT
# ==========================================

bot.run(TOKEN)