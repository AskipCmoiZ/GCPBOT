import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")

# IDs des rôles autorisés à utiliser les commandes admin
# Exemple : WHITELIST_ROLES = [123456789, 987654321]
# Laisser vide [] pour utiliser manage_roles par défaut
WHITELIST_ROLES = [1534255113806286922, 1521132294360924294, 1521132533369016330, 1521132636813262958, 1521132747735826545, 1521132820385235004, 1521132894104322188, 1521132972731007036, 1521131198624305243]

# ID du salon où poster les logs automatiques
# Mettre 0 pour désactiver
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1546764469143863377"))

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

def is_admin(interaction: discord.Interaction) -> bool:
    if WHITELIST_ROLES:
        user_role_ids = [r.id for r in interaction.user.roles]
        return any(role_id in user_role_ids for role_id in WHITELIST_ROLES)
    return interaction.user.guild_permissions.manage_roles

async def send_log(bot, message: str):
    if LOG_CHANNEL_ID:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="📋 Log GCP Bot",
                description=message,
                color=0x2C2F33,
                timestamp=datetime.now()
            )
            await channel.send(embed=embed)

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
            f"❌ {membre.display_name} n'est pas encore enregistré.",
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
@app_commands.describe(membre="Le membre à enregistrer", nom="Nom complet (ex: Jean DUPONT)")
async def enregistrer(interaction: discord.Interaction, membre: discord.Member, nom: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    create_membre(membre.id, nom)
    await interaction.response.send_message(f"✅ **{nom}** a été enregistré dans la base de données GCP.")
    await send_log(bot, f"➕ **{interaction.user.display_name}** a enregistré **{nom}**")

# /modifier
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

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()

    changements = []

    if grade:
        c.execute("UPDATE membres SET grade = ? WHERE discord_id = ?", (grade, str(membre.id)))
        changements.append(f"Grade → **{grade}**")
    if specialite:
        c.execute("UPDATE membres SET specialite = ? WHERE discord_id = ?", (specialite, str(membre.id)))
        changements.append(f"Spécialité → **{specialite}**")
    if distinctions:
        c.execute("UPDATE membres SET distinctions = ? WHERE discord_id = ?", (distinctions, str(membre.id)))
        changements.append(f"Distinctions → **{distinctions}**")
    if date_entree:
        c.execute("UPDATE membres SET date_entree = ? WHERE discord_id = ?", (date_entree, str(membre.id)))
        changements.append(f"Date d'entrée → **{date_entree}**")
    if opex_count is not None:
        c.execute("UPDATE membres SET opex_count = ? WHERE discord_id = ?", (opex_count, str(membre.id)))
        changements.append(f"Opex effectuées → **{opex_count}**")

    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Profil de **{membre.display_name}** mis à jour.")
    if changements:
        await send_log(bot, f"✏️ **{interaction.user.display_name}** a modifié le profil de **{membre.display_name}** :\n" + "\n".join(changements))

# /ajouter_distinction
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
    if distinctions_actuelles:
        nouvelles = distinctions_actuelles + f", {distinction}"
    else:
        nouvelles = distinction

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    c.execute("UPDATE membres SET distinctions = ? WHERE discord_id = ?", (nouvelles, str(membre.id)))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Distinction **{distinction}** ajoutée à **{membre.display_name}**.")
    await send_log(bot, f"🏅 **{interaction.user.display_name}** a ajouté la distinction **{distinction}** à **{membre.display_name}**")

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

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()
    date = datetime.now().strftime("%d/%m/%Y")

    c.execute("INSERT INTO opex (discord_id, nom_opex, note, commentaire, date, noter_par) VALUES (?, ?, ?, ?, ?, ?)",
              (str(membre.id), opex, note, commentaire, date, str(interaction.user.display_name)))

    c.execute("UPDATE membres SET opex_count = opex_count + 1, note_total = note_total + ?, note_count = note_count + 1 WHERE discord_id = ?",
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

# /supprimer_note
@tree.command(name="supprimer_note", description="Supprimer la dernière notation d'un membre")
@app_commands.describe(membre="Le membre dont supprimer la dernière note")
async def supprimer_note(interaction: discord.Interaction, membre: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Tu n'as pas la permission de faire ça.", ephemeral=True)
        return

    conn = sqlite3.connect("gcp.db")
    c = conn.cursor()

    c.execute("SELECT id, note FROM opex WHERE discord_id = ? ORDER BY id DESC LIMIT 1", (str(membre.id),))
    row = c.fetchone()

    if not row:
        await interaction.response.send_message("❌ Aucune notation trouvée pour ce membre.", ephemeral=True)
        conn.close()
        return

    opex_id, note = row
    c.execute("DELETE FROM opex WHERE id = ?", (opex_id,))
    c.execute("UPDATE membres SET opex_count = opex_count - 1, note_total = note_total - ?, note_count = note_count - 1 WHERE discord_id = ?",
              (note, str(membre.id)))

    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ Dernière notation de **{membre.display_name}** supprimée.")
    await send_log(bot, f"🗑️ **{interaction.user.display_name}** a supprimé la dernière notation de **{membre.display_name}** (note : {note}/10)")

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

    embed = discord.Embed(title="🏆 Classement GCP — Note moyenne", color=0x2C2F33)
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

# /stats
@tree.command(name="stats", description="Statistiques globales de l'unité GCP")
async def stats(interaction: discord.Interaction):
    conn = sqlite3.connect("gcp.db")
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

# /config_whitelist
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

# /aide
@tree.command(name="aide", description="Liste toutes les commandes du bot GCP")
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 Commandes du Bot GCP", color=0x2C2F33)
    embed.add_field(name="👤 Commandes membres", value=
        "`/profil [@membre]` — Voir un profil\n"
        "`/historique [@membre]` — Historique opex\n"
        "`/classement` — Top membres\n"
        "`/stats` — Statistiques de l'unité",
        inline=False
    )
    embed.add_field(name="🔐 Commandes gradés", value=
        "`/enregistrer @membre nom` — Enregistrer un membre\n"
        "`/modifier @membre` — Modifier grade/spécialité/date/opex\n"
        "`/ajouter_distinction @membre distinction` — Ajouter une distinction\n"
        "`/noter @membre opex note` — Noter après une opex\n"
        "`/supprimer_note @membre` — Supprimer la dernière note",
        inline=False
    )
    embed.set_footer(text="GCP — Groupement de Commandos Parachutistes • Qui ose gagne.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# LANCEMENT
# ==========================================

bot.run(TOKEN)
