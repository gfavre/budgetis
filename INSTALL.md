# 🚀 Budgetis – Installation Guide

Budgetis est une application **Django** utilisée pour la gestion financière communale.
Vous pouvez l’installer **localement** (développement) ou via **Docker** (production recommandé).

---

## 1. Pré-requis

* **Python ≥ 3.12**
* [**uv**](https://github.com/astral-sh/uv) (gestion des dépendances Python)
* **PostgreSQL ≥ 15**
* **Redis ≥ 7**
* **Docker + Docker Compose** (optionnel mais recommandé pour production)

---

## 2. Installation avec Docker (recommandée)

### Étapes

1. Copier le fichier d’exemple et générer les secrets :

   ```bash
   cp .env.example .env
   ./scripts/setup.sh
   ```

   👉 Le script :

   * crée `.env` si absent
   * génère un `DJANGO_SECRET_KEY` unique si manquant
   * construit les images Docker
   * applique les migrations
   * propose de créer un superutilisateur

2. Démarrer l’application :

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
   ```

3. Accéder à l’application :

   ```
   http://localhost:8000
   ```

---

## 3. Installation locale (développement)

### Étapes

1. Créer un environnement virtuel :

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Installer les dépendances avec **uv** :

   ```bash
   uv pip install -r pyproject.toml
   ```

3. Configurer `.env` :

   ```bash
   cp .env.example .env
   python -c "from django.core.management.utils import get_random_secret_key; print('DJANGO_SECRET_KEY='+get_random_secret_key())" >> .env
   ```

4. Lancer les migrations :

   ```bash
   python manage.py migrate
   ```

5. Démarrer le serveur :

   ```bash
   python manage.py runserver
   ```

---

## 4. Services externes

* **Base de données** : PostgreSQL (local ou conteneur `db`)
* **Cache & tâches asynchrones** : Redis (local ou conteneur `redis`)
* **E-mails** : Postmark (via `POSTMARK_SERVER_TOKEN`)
* **Authentification** : Microsoft (via `MS_CLIENT_ID`, `MS_SECRET`, `MS_TENANT_ID`)

---

## 5. Commandes utiles

### Avec Docker

* Rebuild complet :

  ```bash
  docker compose build --no-cache
  ```

* Migrations :

  ```bash
  docker compose run --rm web python manage.py migrate
  ```

* Créer un superutilisateur :

  ```bash
  docker compose run --rm web python manage.py createsuperuser
  ```

* Voir les logs :

  ```bash
  docker compose logs -f
  ```

### En local

* Appliquer migrations :

  ```bash
  python manage.py migrate
  ```

* Créer un superutilisateur :

  ```bash
  python manage.py createsuperuser
  ```

---

## 6. Notes importantes

* La variable `DJANGO_SECRET_KEY` est générée **une seule fois** lors de l’installation initiale et ajoutée dans `.env`.
* **Ne jamais** commiter `.env` dans le dépôt.
* Pour un déploiement en production, placer un **reverse proxy** (Nginx ou Traefik) devant le service `web`.
* Le fichier `.env.example` fournit la configuration **minimale** nécessaire. Ajoutez d’autres variables si vous activez Sentry, Anymail avancé, ou des options de sécurité supplémentaires.
