def generer_loot(discord_id: int):
    base_loots = {
        "Commun": [
            ("Gilet Porte-Plaques", "Gilet", "Commun", "blindage", 5),
            ("Silencieux Tactique", "Accessoire", "Commun", "furtivite", 4),
            ("Viseur Red Dot", "Accessoire", "Commun", "precision", 3)
        ],
        "Rare": [
            ("Viseur Holo EOTech", "Accessoire", "Rare", "precision", 5),
            ("HK416 A5", "Arme", "Rare", "precision", 10),
            ("Casque Ops-Core FAST", "Gilet", "Rare", "blindage", 8),
            ("Tenue Camouflage Ghillie", "Accessoire", "Rare", "furtivite", 7)
        ],
        "Épique": [
            ("FN SCAR-H", "Arme", "Épique", "precision", 15),
            ("Gilet Tactique Lourd", "Gilet", "Épique", "blindage", 14),
            ("Micro-Drone Recon", "Accessoire", "Épique", "furtivite", 12)
        ],
        "Légendaire": [
            ("PGM Hécate II", "Arme", "Légendaire", "precision", 20),
            ("Lunettes NVG GPNVG-18", "Accessoire", "Légendaire", "furtivite", 15)
        ],
        "Mythique": [
            ("Exosquelette GCP Prototype", "Gilet", "Mythique", "blindage", 30),
            ("Lance-Roquettes NLAW", "Arme", "Mythique", "precision", 35)
        ]
    }

    raretes = ["Commun", "Rare", "Épique", "Légendaire", "Mythique"]
    poids = [50, 35, 15, 5, 0.5]

    # Tirage de la rareté selon tes pondérations
    rarete_choisie = random.choices(raretes, weights=poids, k=1)[0]
    item = random.choice(base_loots[rarete_choisie])
    nom, type_i, rarete, stat, bonus = item

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO inventaire_joueurs (discord_id, nom_item, type_item, rarete, bonus_stat, valeur_bonus) VALUES (%s, %s, %s, %s, %s, %s)",
        (str(discord_id), nom, type_i, rarete, stat, bonus)
    )
    conn.commit()
    conn.close()
    return item