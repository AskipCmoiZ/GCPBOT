import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")  # Token du bot depuis variable d'environnement
GRADE_ROLE_IDS = []  # Optionnel : IDs des rôles autorisés à noter (laisser vide = tous les admins)

# ==========================================
# BASE DE DONNÉES
# ==========================================

def init_db():
    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS membres (
        discord_id TEXT PRIMARY KEY,
        nom TEXT,
        grade TEXT DEFAULT 'Soldat',
        specialite TEXT DEFAULT 'Assaulteur',
        date_entree TEXT,
        opex_count INTEGER DEFAULT 0,
        note_total REAL DEFAULT 0,
        note_count INTEGER DEFAULT 0,
        distinctions TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS opex (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id TEXT,
        nom_opex TEXT,
        note REAL,
        commentaire TEXT,
        date TEXT,
        noter_par TEXT
    )''')

    conn.commit()
    conn.close()

def get_membre(discord_id):
    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    c.execute("SELECT * FROM membres WHERE discord_id = ?", (str(discord_id),))
    row = c.fetchone()
    conn.close()
    return row

def create_membre(discord_id, nom):
    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    date_entree = datetime.now().strftime("%d/%m/%Y")
    c.execute("INSERT OR IGNORE INTO membres (discord_id, nom, date_entree) VALUES (?, ?, ?)",
              (str(discord_id), nom, date_entree))
    conn.commit()
    conn.close()

# ==========================================
# BOT
# ==========================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f"✅ Bot GCP connecté : {bot.user}")

# ==========================================
# COMMANDES
# ==========================================

# /profil
@tree.command(name="profil", description="Affiche le profil d'un membre du GCP")
@app_commands.describe(membre="Le membre dont tu veux voir le profil")
async def profil(interaction: discord.Interaction, membre: discord.Member = None):
    if membre is None:
        membre = interaction.user

    row = get_membre(membre.id)

    if not row:
        await interaction.response.send_message(
            f"❌ {membre.display_name} n'est pas encore enregistré. Utilise `/enregistrer` d'abord.",
            ephemeral=True
        )
        return

    discord_id, nom, grade, specialite, date_entree, opex_count, note_total, note_count, distinctions = row

    note_moyenne = round(note_total / note_count, 2) if note_count > 0 else "Aucune note"
    distinctions_list = distinctions if distinctions else "Aucune"

    embed = discord.Embed(
        title=f"🪖 Dossier Opérationnel — {nom}",
        color=0x2C2F33
    )
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="🎖️ Grade", value=grade, inline=True)
    embed.add_field(name="⚔️ Spécialité", value=specialite, inline=True)
    embed.add_field(name="📅 Entrée dans l'unité", value=date_entree, inline=True)
    embed.add_field(name="🗺️ Opex effectuées", value=str(opex_count), inline=True)
    embed.add_field(name="⭐ Note moyenne", value=str(note_moyenne), inline=True)
    embed.add_field(name="🏅 Distinctions", value=distinctions_list, inline=False)
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")

    await interaction.response.send_message(embed=embed)

# /enregistrer
@tree.command(name="enregistrer", description="Enregistre un nouveau membre dans la base GCP")
@app_commands.describe(membre="Le membre à enregistrer", nom="Nom complet du membre (ex: Jean DUPONT)")
async def enregistrer(interaction: discord.Interaction, membre: discord.Member, nom: str):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    create_membre(membre.id, nom)
    await interaction.response.send_message(f"✅ **{nom}** a été enregistré dans la base de données GCP.")

# /modifier
@tree.command(name="modifier", description="Modifier le profil d'un membre")
@app_commands.describe(
    membre="Le membre à modifier",
    grade="Nouveau grade",
    specialite="Nouvelle spécialité",
    distinctions="Distinctions (séparées par des virgules)"
)
async def modifier(interaction: discord.Interaction, membre: discord.Member,
                   grade: str = None, specialite: str = None, distinctions: str = None):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()

    if grade:
        c.execute("UPDATE membres SET grade = ? WHERE discord_id = ?", (grade, str(membre.id)))
    if specialite:
        c.execute("UPDATE membres SET specialite = ? WHERE discord_id = ?", (specialite, str(membre.id)))
    if distinctions:
        c.execute("UPDATE membres SET distinctions = ? WHERE discord_id = ?", (distinctions, str(membre.id)))

    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Profil de **{membre.display_name}** mis à jour.")

# /noter
@tree.command(name="noter", description="Noter un membre après une opex")
@app_commands.describe(
    membre="Le membre à noter",
    opex="Nom de l'opération",
    note="Note de 0 à 10",
    commentaire="Commentaire optionnel"
)
async def noter(interaction: discord.Interaction, membre: discord.Member,
                opex: str, note: float, commentaire: str = ""):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    if note < 0 or note > 10:
        await interaction.response.send_message("❌ La note doit être entre 0 et 10.", ephemeral=True)
        return

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    date = datetime.now().strftime("%d/%m/%Y")

    c.execute("INSERT INTO opex (discord_id, nom_opex, note, commentaire, date, noter_par) VALUES (?, ?, ?, ?, ?, ?)",
              (str(membre.id), opex, note, commentaire, date, str(interaction.user.display_name)))

    c.execute("UPDATE membres SET opex_count = opex_count + 1, note_total = note_total + ?, note_count = note_count + 1 WHERE discord_id = ?",
              (note, str(membre.id)))

    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="📋 Notation enregistrée",
        color=0x2C2F33
    )
    embed.add_field(name="Membre", value=membre.display_name, inline=True)
    embed.add_field(name="Opération", value=opex, inline=True)
    embed.add_field(name="Note", value=f"{note}/10", inline=True)
    if commentaire:
        embed.add_field(name="Commentaire", value=commentaire, inline=False)
    embed.set_footer(text=f"Noté par {interaction.user.display_name} • {date}")

    await interaction.response.send_message(embed=embed)

# /historique
@tree.command(name="historique", description="Voir l'historique des opex d'un membre")
@app_commands.describe(membre="Le membre dont tu veux voir l'historique")
async def historique(interaction: discord.Interaction, membre: discord.Member = None):
    if membre is None:
        membre = interaction.user

    row = get_membre(membre.id)
    if not row:
        await interaction.response.send_message("❌ Ce membre n'est pas enregistré.", ephemeral=True)
        return

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    c.execute("SELECT nom_opex, note, commentaire, date, noter_par FROM opex WHERE discord_id = ? ORDER BY id DESC LIMIT 10",
              (str(membre.id),))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(f"Aucune opex enregistrée pour {membre.display_name}.")
        return

    embed = discord.Embed(
        title=f"🗺️ Historique opex — {membre.display_name}",
        color=0x2C2F33
    )

    for r in rows:
        nom_opex, note, commentaire, date, noter_par = r
        valeur = f"Note : **{note}/10**"
        if commentaire:
            valeur += f"\n_{commentaire}_"
        valeur += f"\nNoté par {noter_par} le {date}"
        embed.add_field(name=f"🔴 {nom_opex}", value=valeur, inline=False)

    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed)

# /classement
@tree.command(name="classement", description="Affiche le classement des membres par note moyenne")
async def classement(interaction: discord.Interaction):
    conn = sqlite3.connect("gcp.db")
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

    embed = discord.Embed(
        title="🏆 Classement GCP — Note moyenne",
        color=0x2C2F33
    )

    medals = ["🥇", "🥈", "🥉"]
    for i, (nom, grade, opex_count, moyenne) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        embed.add_field(
            name=f"{prefix} {nom}",
            value=f"**{grade}** • {opex_count} opex • Moyenne : **{moyenne}/10**",
            inline=False
        )

    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed)

# /aide
@tree.command(name="aide", description="Liste toutes les commandes du bot GCP")
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Commandes du Bot GCP",
        color=0x2C2F33
    )
    embed.add_field(name="/profil [@membre]", value="Affiche le profil d'un membre", inline=False)
    embed.add_field(name="/enregistrer @membre nom", value="Enregistre un nouveau membre *(gradés)*", inline=False)
    embed.add_field(name="/modifier @membre", value="Modifie le grade, spécialité ou distinctions *(gradés)*", inline=False)
    embed.add_field(name="/noter @membre opex note commentaire", value="Note un membre après une opex *(gradés)*", inline=False)
    embed.add_field(name="/historique [@membre]", value="Voir l'historique des opex d'un membre", inline=False)
    embed.add_field(name="/classement", value="Classement des membres par note moyenne", inline=False)
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# LANCEMENT
# ==========================================

bot.run(TOKEN)
