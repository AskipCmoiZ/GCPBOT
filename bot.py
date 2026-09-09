# /retirer_distinction
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

    # Découpage et nettoyage de la liste des distinctions actuelles
    liste_distinctions = [d.strip() for d in distinctions_actuelles.split(",") if d.strip()]
    
    # Recherche insensible à la casse
    trouve = False
    nouvelle_liste = []
    for d in liste_distinctions:
        if not trouve and d.lower() == distinction.strip().lower():
            trouve = True  # On retire la première occurrence trouvée
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