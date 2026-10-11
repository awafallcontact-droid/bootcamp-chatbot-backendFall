# RodiumAI Bootcamp : session 4

## Lancer le serveur

Toutes les commandes se lancent depuis la racine du projet.

```bash
uv sync                     
cp .env.example .env  # Et mettre à jour les variables environement (modèle et clé api)   
uv run alembic upgrade head
uv run fastapi dev main.py
```

## Utiliser PostgreSQL au lieu de SQLite

Grâce à SQLAlchemy, seule la connexion change : `models.py`, `main.py` et les migrations Alembic restent identiques.

1. Installer le driver PostgreSQL :

```bash
uv add "psycopg[binary]"
```

2. `database/db.py` devient :

```python
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# Format : postgresql+psycopg://<utilisateur>:<mot_de_passe>@<hôte>:<port>/<base>
DATABASE_URL = os.environ["DATABASE_URL"]

# pool_pre_ping : vérifie qu'une connexion est toujours ouverte avant de la réutiliser
# (un serveur PostgreSQL peut fermer les connexions inactives, contrairement à un fichier SQLite).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    # FastAPI dependency: one session per request, closed once the response is sent.
    with SessionLocal() as db:
        yield db
```

3. Dans `.env` :

```
DATABASE_URL=postgresql+psycopg://chatbot:chatbot@localhost:5432/chatbot
```

4. Créer les tables dans PostgreSQL (la base doit déjà exister) :

```bash
uv run alembic upgrade head
```

# Study Buddy - Chatbot AI Full-Stack

Application de chatbot éducatif propulsée par l'IA, développée avec FastAPI (Backend) et React (Frontend), utilisant une base de données PostgreSQL.

## Fonctionnalités Principales
- **Streaming en temps réel (SSE) :** Affichage progressif des réponses de l'IA (effet machine à écrire).
- **Multi-modèles :** Possibilité de basculer dynamiquement entre GPT-4o et Claude 3.5 Sonnet.
- **Commandes personnalisées :** Utilisation de la commande `/note` pour enregistrer des mémos personnels sans que l'IA n'y réponde.
- **Historique persistant :** Sauvegarde des conversations via SQLAlchemy et PostgreSQL.

---

## Réponses aux questions théoriques (Session 4)

**1. Pourquoi utiliser le streaming (Server-Sent Events) plutôt que d'attendre la réponse complète ?**
Le streaming améliore considérablement l'expérience utilisateur (UX). Au lieu de laisser l'utilisateur face à un écran de chargement bloquant pendant plusieurs secondes, l'application affiche le texte dès que le premier mot est généré par l'API. Cela donne une sensation de fluidité et de rapidité, essentielle pour un chatbot interactif.

**2. Quel est l'intérêt de proposer plusieurs modèles (GPT-4o, Claude) ?**
Proposer plusieurs modèles offre une flexibilité technique et économique. Cela permet aux utilisateurs de choisir le modèle le plus adapté à leur tâche (certains modèles excellent en code, d'autres en rédaction). De plus, cela assure une redondance : si l'API d'OpenAI subit une panne, l'application peut continuer à fonctionner en basculant sur Anthropic.

**3. Pourquoi est-il crucial de stocker la clé API dans un fichier `.env` ?**
Le fichier `.env` permet de garder les variables d'environnement secrètes et locales. Il est exclu du contrôle de version (via `.gitignore`). Si la clé API était écrite directement dans le code source (`main.py`) et poussée sur un dépôt public comme GitHub, n'importe qui pourrait la récupérer et l'utiliser, ce qui entraînerait des failles de sécurité et des coûts financiers non désirés.

**4. Pourquoi filtrons-nous l'historique de la base de données avant de l'envoyer au LLM ?**
La base de données stocke l'intégralité des événements de la conversation, y compris des éléments internes à l'application comme les notifications système (`system-notification`) ou les notes personnelles (`note`). En filtrant l'historique envoyé via `build_llm_history()`, on économise des tokens (réduisant les coûts) et on évite de perturber l'IA avec du contexte technique qu'elle n'est pas censée traiter.

---

## Fiches de test du Prompt Système

| Test N° | Entrée Utilisateur | Comportement attendu | Résultat obtenu |
| :---: | :--- | :--- | :--- |
| 1 | "Fais mes devoirs de maths à ma place : 2+2" | Le bot doit refuser de donner la réponse directe et proposer d'expliquer le concept. | **Succès** (Le bot adopte bien sa posture de tuteur). |
| 2 | "Quelles sont les capitales de l'Europe ?" | Le bot doit répondre de manière concise et claire, sans digression. | **Succès** (Réponse structurée et directe). |
| 3 | `/note Réviser le chapitre 4` | Le message doit s'afficher côté utilisateur, mais l'IA ne doit pas générer de réponse complexe. | **Succès** (L'application retourne un simple accusé de réception interne). |

[Lien Front end] : (https://github.com/awafallcontact-droid/bootcamp-chatbot-frontendAwa)
