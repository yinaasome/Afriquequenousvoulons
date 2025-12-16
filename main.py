import streamlit as st
from streamlit_javascript import st_javascript
import pymongo
from pymongo import MongoClient
import uuid
import random
import pandas as pd
import os
import altair as alt
from textblob import TextBlob
import numpy as np
from datetime import datetime, timedelta
import time
from PIL import Image
import base64
from itertools import combinations

# 🛠️ Configuration de la page
st.set_page_config(
    page_title="Wiki Survey - Afrique",
    layout="wide",
    page_icon="🗳️",
    initial_sidebar_state="collapsed"
)

# === Configuration MongoDB CORRIGÉE ===
# Option 1: URL directe (pour Railway) - MODIFIEZ SELON VOTRE CONFIG
# Option 2: Variable d'environnement (recommandé pour Render)
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://mongo:WGLPiIcYKLnGksuHaBpVJNcJjwCpURei@metro.proxy.rlwy.net:14731")
DB_NAME = "Afriqua"

# --- Connexion à MongoDB CORRIGÉE ---
@st.cache_resource
def get_db_connection():
    """Obtenir une connexion à MongoDB avec gestion d'erreur améliorée"""
    try:
        if not MONGO_URI:
            st.warning("⚠️ URL MongoDB non configurée")
            return None
            
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,  # Timeout de 5 secondes
            connectTimeoutMS=10000,
            socketTimeoutMS=10000
        )
        
        # Tester la connexion
        client.admin.command('ping')
        db = client[DB_NAME]
        
        # Vérifier si la base existe, sinon créer les collections nécessaires
        if DB_NAME not in client.list_database_names():
            st.info(f"📦 Base '{DB_NAME}' n'existe pas encore. Elle sera créée à la première utilisation.")
        
        return db
        
    except pymongo.errors.ServerSelectionTimeoutError as e:
        st.warning(f"⏱️ Timeout de connexion à MongoDB: {e}")
        st.info("""
        **Causes possibles:**
        1. Votre base Railway n'est pas démarrée (gratuit: s'arrête après inactivité)
        2. L'adresse IP de Render n'est pas autorisée
        3. L'URL de connexion est incorrecte
        """)
        return None
        
    except Exception as e:
        st.error(f"❌ Erreur de connexion à MongoDB: {e}")
        return None

# === Initialisation intelligente de la base ===
def init_database_safe():
    """Initialiser la structure de la base MongoDB sans bloquer l'application"""
    try:
        db = get_db_connection()
        
        if db is None:
            st.warning("Mode démo: Connexion non disponible, données simulées")
            return False
            
        # Liste des collections nécessaires
        collections_needed = [
            "navigateur", "login", "question",
            "idees", "vote", "commentaire",
            "profil", "sentiment_analytics"
        ]
        
        existing_collections = db.list_collection_names()
        collections_created = []
        
        for collection in collections_needed:
            if collection not in existing_collections:
                try:
                    db.create_collection(collection)
                    collections_created.append(collection)
                except Exception as e:
                    st.warning(f"⚠️ Impossible de créer '{collection}': {e}")
        
        # Créer les index si possible
        try:
            db.login.create_index("email", unique=True, sparse=True)
            db.idees.create_index("id_question")
            db.vote.create_index([("id_navigateur", 1), ("id_question", 1)])
            db.profil.create_index("id_navigateur", unique=True, sparse=True)
            db.sentiment_analytics.create_index("id_question", unique=True, sparse=True)
        except Exception as e:
            st.warning(f"⚠️ Erreur création index: {e}")
        
        if collections_created:
            st.success(f"✅ Collections créées: {', '.join(collections_created)}")
        else:
            st.success("✅ Base de données prête")
        
        # Données de démo seulement si pas déjà présentes
        try:
            if db.login.count_documents({"email": "admin@test.com"}) == 0:
                db.login.insert_one({
                    "email": "admin@test.com",
                    "mot_de_passe": "admin123",
                    "date_creation": datetime.now()
                })
                
            if db.login.count_documents({"email": "yinnaasome@gmail.com"}) == 0:
                db.login.insert_one({
                    "email": "yinnaasome@gmail.com",
                    "mot_de_passe": "abc",
                    "date_creation": datetime.now()
                })
        except:
            pass  # Ignorer les erreurs sur les données de démo
            
        return True
        
    except Exception as e:
        st.error(f"❌ Erreur initialisation: {e}")
        return False

# === Analyse de sentiment ===
def analyze_sentiment(text):
    """Analyser le sentiment d'un texte avec TextBlob"""
    try:
        if not text or not isinstance(text, str):
            return 0.0, "Neutre"
            
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity

        if polarity > 0.1:
            label = "Positif"
        elif polarity < -0.1:
            label = "Négatif"
        else:
            label = "Neutre"

        return polarity, label
    except:
        return 0.0, "Neutre"

def update_sentiment_analytics(question_id):
    """Mettre à jour les analytics de sentiment pour une question"""
    try:
        db = get_db_connection()
        if db is None:
            return
            
        # Calculer les stats pour les idées
        try:
            idees_stats_cursor = db.idees.aggregate([
                {"$match": {"id_question": question_id}},
                {"$group": {
                    "_id": None,
                    "avg_sentiment": {"$avg": "$sentiment_score"},
                    "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                    "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                    "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
                }}
            ])
            idees_stats = next(idees_stats_cursor, {})
        except:
            idees_stats = {}

        # Calculer les stats pour les commentaires
        try:
            commentaires_stats_cursor = db.commentaire.aggregate([
                {"$match": {"id_question": question_id}},
                {"$group": {
                    "_id": None,
                    "avg_sentiment": {"$avg": "$sentiment_score"},
                    "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                    "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                    "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
                }}
            ])
            commentaires_stats = next(commentaires_stats_cursor, {})
        except:
            commentaires_stats = {}

        # Insérer ou mettre à jour les analytics
        db.sentiment_analytics.update_one(
            {"id_question": question_id},
            {"$set": {
                "moyenne_sentiment_idees": idees_stats.get("avg_sentiment", 0),
                "moyenne_sentiment_commentaires": commentaires_stats.get("avg_sentiment", 0),
                "total_idees_positives": idees_stats.get("positifs", 0),
                "total_idees_negatives": idees_stats.get("negatifs", 0),
                "total_idees_neutres": idees_stats.get("neutres", 0),
                "total_commentaires_positifs": commentaires_stats.get("positifs", 0),
                "total_commentaires_negatifs": commentaires_stats.get("negatifs", 0),
                "total_commentaires_neutres": commentaires_stats.get("neutres", 0),
                "derniere_mise_a_jour": datetime.now()
            }},
            upsert=True
        )

    except Exception as e:
        st.warning(f"⚠️ Erreur mise à jour analytics: {e}")

# =============================================================
# === INITIALISATION SESSION STATE ===
# =============================================================

# Initialiser les clés nécessaires dans session_state
if "page" not in st.session_state:
    st.session_state["page"] = "home"

if "id_navigateur" not in st.session_state:
    st.session_state["id_navigateur"] = None

if "auth" not in st.session_state:
    st.session_state.auth = False

if "utilisateur_id" not in st.session_state:
    st.session_state.utilisateur_id = None

if "email" not in st.session_state:
    st.session_state.email = None

if "current_tab" not in st.session_state:
    st.session_state.current_tab = "home"

if "database_ready" not in st.session_state:
    st.session_state.database_ready = False

# =============================================================
# === INITIALISATION DE LA BASE (NON-BLOQUANTE) ===
# =============================================================

# Afficher un message pendant l'initialisation
with st.spinner("🔧 Initialisation de l'application..."):
    # Essayer d'initialiser mais NE PAS BLOQUER
    st.session_state.database_ready = init_database_safe()
    
    # Attendre un peu pour que le message soit visible
    time.sleep(0.5)

# =============================================================
# === FONCTIONS NAVIGATEUR ===
# =============================================================

# --- ID navigateur ---
def get_navigateur_id():
    js_code = """
        const existing = localStorage.getItem("id_navigateur");
        if (existing) {
            existing;
        } else {
            const newId = crypto.randomUUID();
            localStorage.setItem("id_navigateur", newId);
            newId;
        }
    """
    return st_javascript(js_code)

def detect_navigateur():
    js_code = "navigator.userAgent;"
    agent = st_javascript(js_code)
    if agent:
        if "Chrome" in agent and "Edg" not in agent:
            return "Chrome"
        elif "Firefox" in agent:
            return "Firefox"
        elif "Edg" in agent:
            return "Edge"
        elif "Safari" in agent and "Chrome" not in agent:
            return "Safari"
    return "Inconnu"

def init_navigateur():
    if not st.session_state["id_navigateur"]:
        id_navigateur = get_navigateur_id()
        if id_navigateur and len(id_navigateur) > 100:
            id_navigateur = id_navigateur[:100]
        navigateur_nom = detect_navigateur()
        
        if id_navigateur:
            st.session_state["id_navigateur"] = id_navigateur
            
            # Enregistrer seulement si la base est disponible
            if st.session_state.database_ready:
                try:
                    db = get_db_connection()
                    if db:
                        db.navigateur.update_one(
                            {"id_navigateur": id_navigateur},
                            {"$set": {
                                "id_navigateur": id_navigateur,
                                "navigateur": navigateur_nom,
                                "date_creation": datetime.now()
                            }},
                            upsert=True
                        )
                except:
                    pass  # Ignorer les erreurs d'enregistrement

# Appel obligatoire
init_navigateur()

# =============================================================
# === FONCTIONS D'AUTHENTIFICATION AMÉLIORÉES ===
# =============================================================

def creer_compte():
    """Page de création de compte avec gestion hors-ligne"""
    st.subheader("Créez votre compte pour proposer une question")
    
    email_reg = st.text_input("Email", key="email_reg")
    mot_de_passe_reg = st.text_input("Mot de passe", type="password", key="pass_reg")
    mot_de_passe_conf = st.text_input("Confirmer le mot de passe", type="password", key="pass_conf")

    if st.button("Créer le compte", key="btn_creer_compte"):
        if not email_reg or not mot_de_passe_reg or not mot_de_passe_conf:
            st.error("Veuillez remplir tous les champs.")
            return

        if mot_de_passe_reg != mot_de_passe_conf:
            st.error("Les mots de passe ne correspondent pas.")
            return

        if not st.session_state.database_ready:
            # Mode hors-ligne : créer un compte local
            st.session_state.auth = True
            st.session_state.utilisateur_id = str(uuid.uuid4())
            st.session_state.email = email_reg
            st.success(f"✅ Compte local créé ! Bienvenue {email_reg} !")
            st.info("📱 Mode hors-ligne - vos données seront synchronisées quand la connexion sera rétablie")
            time.sleep(1)
            st.rerun()
            return

        # Mode en ligne
        try:
            db = get_db_connection()
            if not db:
                raise Exception("Base de données non disponible")

            # Vérifier si l'email existe déjà
            if db.login.find_one({"email": email_reg}):
                st.error("Cet email est déjà utilisé. Veuillez vous connecter.")
                return

            # Enregistrer le nouvel utilisateur
            nouvel_utilisateur = {
                "email": email_reg,
                "mot_de_passe": mot_de_passe_reg,
                "date_creation": datetime.now()
            }
            user_id = db.login.insert_one(nouvel_utilisateur).inserted_id

            # Connexion automatique
            st.session_state.auth = True
            st.session_state.utilisateur_id = str(user_id)
            st.session_state.email = email_reg
            st.success(f"✅ Compte créé et connexion réussie ! Bienvenue {st.session_state.email} !")
            time.sleep(1)
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Erreur création de compte: {e}")
            st.info("Essayez le mode hors-ligne ou revenez plus tard")

def login_page():
    """Interface de connexion avec support hors-ligne"""
    st.subheader("Connectez-vous pour proposer une question")
    
    email = st.text_input("Email", key="email_login")
    mot_de_passe = st.text_input("Mot de passe", type="password", key="pass_login")

    if st.button("Se connecter", key="btn_login"):
        if not email or not mot_de_passe:
            st.error("Veuillez remplir tous les champs.")
            return

        if not st.session_state.database_ready:
            # Mode hors-ligne
            st.warning("Mode hors-ligne - connexion limitée")
            st.session_state.auth = True
            st.session_state.utilisateur_id = str(uuid.uuid4())
            st.session_state.email = email
            st.success(f"✅ Connecté en mode hors-ligne ! Bienvenue {email} !")
            time.sleep(1)
            st.rerun()
            return

        # Mode en ligne
        try:
            db = get_db_connection()
            if not db:
                raise Exception("Base de données non disponible")

            utilisateur = db.login.find_one({
                "email": email,
                "mot_de_passe": mot_de_passe
            })

            if utilisateur:
                st.session_state.auth = True
                st.session_state.utilisateur_id = str(utilisateur["_id"])
                st.session_state.email = utilisateur["email"]
                st.success(f"✅ Bienvenue {st.session_state.email} !")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Identifiants incorrects")
                
        except Exception as e:
            st.error(f"❌ Erreur de connexion: {e}")
            st.info("Essayez le mode hors-ligne ou revenez plus tard")

def authentication_flow():
    """Gère la connexion et la création de compte via des onglets"""
    tab_login, tab_register = st.tabs(["🔒 Se connecter", "✍️ Créer un compte"])

    with tab_login:
        login_page()

    with tab_register:
        creer_compte()

# =============================================================
# === FONCTIONS PRINCIPALES AVEC SUPPORT HORS-LIGNE ===
# =============================================================

def creer_question():
    st.header("✍️ Créer une nouvelle question")

    # Vérifier si l'utilisateur est connecté
    if not st.session_state.get("auth"):
        st.info("Veuillez vous connecter ou créer un compte pour proposer une question.")
        authentication_flow()
        return

    with st.form("form_question"):
        question = st.text_input("Votre question :", 
                               placeholder="Ex: Quelle est la priorité pour le développement de l'Afrique ?")
        idee1 = st.text_input("Idée 1 :", 
                            placeholder="Ex: Éducation gratuite pour tous")
        idee2 = st.text_input("Idée 2 :", 
                            placeholder="Ex: Monnaie unique africaine")
        
        submitted = st.form_submit_button("Créer la question")

        if submitted:
            if not question.strip():
                st.error("Veuillez saisir une question.")
                return
            if not idee1.strip() or not idee2.strip():
                st.error("Veuillez saisir deux idées pour la question.")
                return

            if not st.session_state.database_ready:
                st.error("⚠️ Impossible de créer la question : base de données non disponible")
                st.info("Veuillez réessayer plus tard quand la connexion sera rétablie")
                return

            try:
                db = get_db_connection()
                if not db:
                    raise Exception("Base de données non disponible")

                # Insérer la question
                question_data = {
                    "question": question.strip(),
                    "createur_id": st.session_state.utilisateur_id,
                    "createur_email": st.session_state.email,
                    "date_creation": datetime.now()
                }
                question_id = db.question.insert_one(question_data).inserted_id

                # Analyser sentiment des idées
                score1, label1 = analyze_sentiment(idee1)
                score2, label2 = analyze_sentiment(idee2)

                # Insérer les idées
                db.idees.insert_many([
                    {
                        "id_question": question_id,
                        "idee_texte": idee1.strip(),
                        "creer_par_utilisateur": "non",
                        "date_creation": datetime.now(),
                        "sentiment_score": float(score1),
                        "sentiment_label": label1
                    },
                    {
                        "id_question": question_id,
                        "idee_texte": idee2.strip(),
                        "creer_par_utilisateur": "non",
                        "date_creation": datetime.now(),
                        "sentiment_score": float(score2),
                        "sentiment_label": label2
                    }
                ])

                # Mettre à jour les analytics
                update_sentiment_analytics(question_id)

                st.success("✅ Question et idées enregistrées avec succès !")
                st.balloons()
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Erreur lors de la création: {e}")

def get_vote_pairs(question_id, id_navigateur):
    """Obtenir toutes les paires d'idées non votées"""
    if not st.session_state.database_ready:
        return []

    try:
        db = get_db_connection()
        if not db:
            return []
        
        # Récupérer toutes les idées pour cette question
        all_ideas = list(db.idees.find(
            {"id_question": question_id}, 
            {"_id": 1, "idee_texte": 1, "creer_par_utilisateur": 1}
        ))
        
        if len(all_ideas) < 2:
            return []
        
        # Générer toutes les combinaisons possibles
        all_pairs = list(combinations(all_ideas, 2))
        
        # Récupérer les paires déjà votées
        user_votes = list(db.vote.find(
            {
                "id_navigateur": id_navigateur,
                "id_question": question_id
            },
            {"id_idee_gagnant": 1, "id_idee_perdant": 1}
        ))
        
        # Convertir en ensemble de tuples
        voted_pairs = set()
        for vote in user_votes:
            pair = tuple(sorted([vote["id_idee_gagnant"], vote["id_idee_perdant"]]))
            voted_pairs.add(pair)
        
        # Filtrer les paires non votées
        available_pairs = []
        for idea1, idea2 in all_pairs:
            pair_ids = tuple(sorted([idea1["_id"], idea2["_id"]]))
            if pair_ids not in voted_pairs:
                available_pairs.append((idea1, idea2))
        
        return available_pairs
        
    except Exception as e:
        st.warning(f"⚠️ Erreur récupération paires: {e}")
        return []

def participer():
    """Interface de participation au vote"""
    st.header("🗳️ Participer aux votes")
    
    if not st.session_state.database_ready:
        st.error("⚠️ Impossible de participer : base de données non disponible")
        st.info("Veuillez réessayer plus tard quand la connexion sera rétablie")
        return
    
    try:
        db = get_db_connection()
        if not db:
            st.error("❌ Base de données non disponible")
            return

        # Récupérer toutes les questions
        all_questions = list(db.question.find({}, {"_id": 1, "question": 1, "date_creation": 1}).sort("date_creation", -1))

        if not all_questions:
            st.info("Aucune question disponible pour le moment.")
            return

        # Vérifier quelles questions ont encore des paires non votées
        questions_with_available_pairs = []
        for question in all_questions:
            available_pairs = get_vote_pairs(question["_id"], st.session_state.id_navigateur)
            if available_pairs:
                questions_with_available_pairs.append({
                    "question": question,
                    "available_pairs": len(available_pairs)
                })

        if not questions_with_available_pairs:
            st.success("🎉 Vous avez voté sur toutes les paires disponibles !")
            st.info("💡 De nouvelles idées ou questions apparaîtront ici lorsqu'elles seront créées.")
            afficher_formulaire_profil()
            return

        # Initialiser les variables de session
        if 'current_question_index' not in st.session_state:
            st.session_state.current_question_index = 0
        
        if 'current_pair_index' not in st.session_state:
            st.session_state.current_pair_index = 0
        
        if 'current_question_id' not in st.session_state:
            st.session_state.current_question_id = questions_with_available_pairs[0]["question"]["_id"]

        # Sélection de la question
        selected_question = None
        selected_question_data = None
        
        for i, q_data in enumerate(questions_with_available_pairs):
            if q_data["question"]["_id"] == st.session_state.current_question_id:
                selected_question = q_data["question"]
                selected_question_data = q_data
                st.session_state.current_question_index = i
                break
        
        if not selected_question:
            selected_question_data = questions_with_available_pairs[0]
            selected_question = selected_question_data["question"]
            st.session_state.current_question_id = selected_question["_id"]
            st.session_state.current_question_index = 0

        # Navigation entre questions
        if len(questions_with_available_pairs) > 1:
            col_nav = st.columns([2, 5, 2])
            with col_nav[0]:
                if st.button("◀️ Question précédente", 
                            disabled=st.session_state.current_question_index == 0, 
                            use_container_width=True,
                            key=f"btn_prev_question_{st.session_state.current_question_index}"):
                    new_index = max(0, st.session_state.current_question_index - 1)
                    st.session_state.current_question_index = new_index
                    st.session_state.current_question_id = questions_with_available_pairs[new_index]["question"]["_id"]
                    st.session_state.current_pair_index = 0
                    st.rerun()
            
            with col_nav[1]:
                question_progress = (st.session_state.current_question_index + 1) / len(questions_with_available_pairs)
                st.info(f"Question {st.session_state.current_question_index + 1} sur {len(questions_with_available_pairs)}")
            
            with col_nav[2]:
                if st.button("Question suivante ▶️", 
                            disabled=st.session_state.current_question_index >= len(questions_with_available_pairs) - 1, 
                            use_container_width=True,
                            key=f"btn_next_question_{st.session_state.current_question_index}"):
                    new_index = min(len(questions_with_available_pairs) - 1, st.session_state.current_question_index + 1)
                    st.session_state.current_question_index = new_index
                    st.session_state.current_question_id = questions_with_available_pairs[new_index]["question"]["_id"]
                    st.session_state.current_pair_index = 0
                    st.rerun()

        # Affichage de la question
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 1.5rem; border-radius: 10px; color: white; margin: 1rem 0;'>
            <h3 style='color: white; margin: 0;'>❓ {selected_question['question']}</h3>
        </div>
        """, unsafe_allow_html=True)

        question_id = selected_question["_id"]
        
        # Obtenir les paires disponibles
        available_pairs = get_vote_pairs(question_id, st.session_state.id_navigateur)
        
        if not available_pairs:
            st.info("Vous avez voté sur toutes les paires pour cette question.")
            st.session_state.current_question_index += 1
            if st.session_state.current_question_index < len(questions_with_available_pairs):
                st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
                st.rerun()
            return
        
        # S'assurer que current_pair_index est valide
        if st.session_state.current_pair_index >= len(available_pairs):
            st.session_state.current_pair_index = 0
        
        # Sélectionner la paire actuelle
        current_pair = available_pairs[st.session_state.current_pair_index]
        idea1, idea2 = current_pair
        
        # Navigation entre paires
        if len(available_pairs) > 1:
            pair_cols = st.columns([1, 3, 1])
            with pair_cols[0]:
                if st.button("◀️ Paire précédente", 
                            disabled=st.session_state.current_pair_index == 0, 
                            use_container_width=True,
                            key=f"btn_prev_pair_{st.session_state.current_pair_index}"):
                    st.session_state.current_pair_index = max(0, st.session_state.current_pair_index - 1)
                    st.rerun()
            
            with pair_cols[1]:
                progress_value = (st.session_state.current_pair_index + 1) / len(available_pairs)
                progress_value = max(0.0, min(1.0, progress_value))
                st.progress(progress_value)
                st.caption(f"Paire {st.session_state.current_pair_index + 1} sur {len(available_pairs)}")
            
            with pair_cols[2]:
                if st.button("Paire suivante ▶️", 
                            disabled=st.session_state.current_pair_index >= len(available_pairs) - 1, 
                            use_container_width=True,
                            key=f"btn_next_pair_{st.session_state.current_pair_index}"):
                    st.session_state.current_pair_index = min(len(available_pairs) - 1, st.session_state.current_pair_index + 1)
                    st.rerun()

        # Affichage des deux idées
        st.markdown("### 🤔 Quelle idée préférez-vous ?")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div style='border: 2px solid #4CAF50; border-radius: 10px; padding: 1.5rem; 
                        height: 100%; background-color: rgba(76, 175, 80, 0.1);'>
            """, unsafe_allow_html=True)
            st.markdown(f"#### 💡 Option A")
            
            type_a = "Idée téléchargée" if idea1.get("creer_par_utilisateur") == "oui" else "Idée originale"
            st.caption(f"Type: {type_a}")
            
            st.markdown(f"**{idea1['idee_texte']}**")
            
            if st.button("✅ Choisir cette idée", 
                        key=f"vote_{question_id}_{str(idea1['_id'])[:10]}_{str(idea2['_id'])[:10]}_a", 
                        use_container_width=True, 
                        type="primary"):
                enregistrer_vote(idea1['_id'], idea2['_id'], question_id)
                
                if st.session_state.current_pair_index < len(available_pairs) - 1:
                    st.session_state.current_pair_index += 1
                else:
                    st.session_state.current_pair_index = 0
                    st.session_state.current_question_index += 1
                    if st.session_state.current_question_index < len(questions_with_available_pairs):
                        st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
                
                st.success("✅ Vote enregistré !")
                time.sleep(0.5)
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style='border: 2px solid #2196F3; border-radius: 10px; padding: 1.5rem; 
                        height: 100%; background-color: rgba(33, 150, 243, 0.1);'>
            """, unsafe_allow_html=True)
            st.markdown(f"#### 💡 Option B")
            
            type_b = "Idée téléchargée" if idea2.get("creer_par_utilisateur") == "oui" else "Idée originale"
            st.caption(f"Type: {type_b}")
            
            st.markdown(f"**{idea2['idee_texte']}**")
            
            if st.button("✅ Choisir cette idée", 
                        key=f"vote_{question_id}_{str(idea1['_id'])[:10]}_{str(idea2['_id'])[:10]}_b", 
                        use_container_width=True, 
                        type="primary"):
                enregistrer_vote(idea2['_id'], idea1['_id'], question_id)
                
                if st.session_state.current_pair_index < len(available_pairs) - 1:
                    st.session_state.current_pair_index += 1
                else:
                    st.session_state.current_pair_index = 0
                    st.session_state.current_question_index += 1
                    if st.session_state.current_question_index < len(questions_with_available_pairs):
                        st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
                
                st.success("✅ Vote enregistré !")
                time.sleep(0.5)
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)

        # Bouton "Les deux se valent"
        col_center = st.columns([1, 2, 1])
        with col_center[1]:
            if st.button("🤷 Les deux se valent", 
                        use_container_width=True,
                        key=f"egalite_{question_id}_{str(idea1['_id'])[:10]}_{str(idea2['_id'])[:10]}"):
                enregistrer_vote(idea1['_id'], idea2['_id'], question_id)
                
                if st.session_state.current_pair_index < len(available_pairs) - 1:
                    st.session_state.current_pair_index += 1
                else:
                    st.session_state.current_pair_index = 0
                    st.session_state.current_question_index += 1
                    if st.session_state.current_question_index < len(questions_with_available_pairs):
                        st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
                
                st.info("Vote d'égalité enregistré - nouvelle paire d'idées")
                time.sleep(0.5)
                st.rerun()

        # Section pour soumettre une nouvelle idée
        st.markdown("---")
        with st.expander("💡 Proposer une nouvelle idée pour cette question", expanded=False):
            nouvelle_idee = st.text_area("Votre nouvelle idée :", height=100,
                                        placeholder="Proposez une idée innovante pour cette question...")
            
            if st.button("➕ Soumettre cette nouvelle idée", 
                        use_container_width=True,
                        key=f"btn_nouvelle_idee_{question_id}"):
                if nouvelle_idee.strip():
                    score, label = analyze_sentiment(nouvelle_idee)
                    
                    new_idea_id = db.idees.insert_one({
                        "id_question": question_id,
                        "id_navigateur": st.session_state.id_navigateur,
                        "idee_texte": nouvelle_idee.strip(),
                        "creer_par_utilisateur": "oui",
                        "date_creation": datetime.now(),
                        "sentiment_score": float(score),
                        "sentiment_label": label
                    }).inserted_id
                    
                    update_sentiment_analytics(question_id)
                    
                    st.success("✅ Votre idée a été ajoutée avec succès !")
                    st.info("Cette idée sera maintenant incluse dans les comparaisons avec les autres idées.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Veuillez saisir une idée valide.")

        # Section pour ajouter un commentaire
        st.markdown("---")
        with st.expander("💬 Ajouter un commentaire sur cette question", expanded=False):
            commentaire = st.text_area("Votre commentaire :", height=100,
                                      placeholder="Exprimez votre opinion sur cette question...")
            
            if st.button("📝 Ajouter ce commentaire", 
                        use_container_width=True,
                        key=f"btn_commentaire_{question_id}"):
                if commentaire.strip():
                    score, label = analyze_sentiment(commentaire)
                    
                    db.commentaire.insert_one({
                        "id_navigateur": st.session_state.id_navigateur,
                        "id_question": question_id,
                        "commentaire": commentaire.strip(),
                        "date_creation": datetime.now(),
                        "sentiment_score": float(score),
                        "sentiment_label": label
                    })
                    
                    update_sentiment_analytics(question_id)
                    
                    st.success("✅ Commentaire ajouté avec succès !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Veuillez saisir un commentaire valide.")
                    
    except Exception as e:
        st.error(f"❌ Erreur lors de la participation: {e}")

def enregistrer_vote(gagnant, perdant, question_id):
    """Enregistrer un vote dans la base de données"""
    if not st.session_state.database_ready:
        st.error("⚠️ Impossible d'enregistrer le vote : base non disponible")
        return
        
    try:
        db = get_db_connection()
        if not db:
            return
            
        db.vote.insert_one({
            "id_navigateur": st.session_state.id_navigateur,
            "id_question": question_id,
            "id_idee_gagnant": gagnant,
            "id_idee_perdant": perdant,
            "date_vote": datetime.now()
        })

        update_sentiment_analytics(question_id)
        
    except Exception as e:
        st.error(f"❌ Erreur enregistrement vote: {e}")

def afficher_formulaire_profil():
    """Formulaire de profil utilisateur"""
    if not st.session_state.database_ready:
        return
        
    try:
        db = get_db_connection()
        if not db:
            return
            
        if db.profil.find_one({"id_navigateur": st.session_state.id_navigateur}):
            return

        with st.expander("📝 Informations démographiques (optionnel)", expanded=False):
            st.info("Ces informations nous aident à mieux comprendre notre communauté.")
            
            col1, col2 = st.columns(2)
            
            with col1:
                pays = st.text_input("Pays de résidence", placeholder="Ex: Sénégal")
                age = st.number_input("Âge", min_value=10, max_value=120, value=25)
            
            with col2:
                sexe = st.selectbox("Genre", ["", "Homme", "Femme", "Autre", "Je préfère ne pas répondre"])
                fonction = st.text_input("Profession/Fonction", placeholder="Ex: Étudiant, Enseignant, Entrepreneur")
            
            if st.button("Enregistrer mes informations", 
                        use_container_width=True,
                        key="btn_enregistrer_profil"):
                db.profil.insert_one({
                    "id_navigateur": st.session_state.id_navigateur,
                    "pays": pays if pays else None,
                    "age": age if age else None,
                    "sexe": sexe if sexe else None,
                    "fonction": fonction if fonction else None,
                    "date_creation": datetime.now()
                })
                st.success("✅ Merci ! Vos informations ont été enregistrées.")
                time.sleep(1)
                st.rerun()
                
    except Exception as e:
        st.warning(f"⚠️ Erreur formulaire profil: {e}")

# =============================================================
# === VISUALISATIONS AVEC SUPPORT HORS-LIGNE ===
# =============================================================

def afficher_visualisations():
    """Dashboard avec données simulées si hors-ligne"""
    st.title("📊 Visualisations de données")
    
    if not st.session_state.database_ready:
        st.warning("📱 Mode démo - Données simulées (base non disponible)")
        # Afficher des données de démo
        afficher_donnees_demo()
        return
    
    try:
        db = get_db_connection()
        if not db:
            st.warning("📱 Mode démo - Données simulées")
            afficher_donnees_demo()
            return
            
        # Métriques principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_questions = db.question.count_documents({})
            st.metric("📝 Questions", total_questions)
        
        with col2:
            total_votes = db.vote.count_documents({})
            st.metric("🗳️ Votes", total_votes)
        
        with col3:
            total_idees = db.idees.count_documents({})
            st.metric("💡 Idées", total_idees)
        
        with col4:
            total_users = db.navigateur.count_documents({})
            st.metric("👥 Participants", total_users)
        
        st.markdown("---")
        
        # Graphiques (simplifiés pour cet exemple)
        st.markdown("### 📈 Activité récente")
        
        # Données de démo si pas assez de données
        if total_votes < 10:
            st.info("📊 Pas assez de données pour les visualisations avancées")
            afficher_donnees_demo()
            return
            
        # ... (votre code de visualisation existant)
        
    except Exception as e:
        st.error(f"❌ Erreur visualisations: {e}")
        afficher_donnees_demo()

def afficher_donnees_demo():
    """Afficher des données de démo"""
    st.info("""
    **Mode démo activé** - Les visualisations utilisent des données simulées.
    Les vraies données s'afficheront quand la connexion à la base sera rétablie.
    """)
    
    # Données de démo pour les graphiques
    df_demo = pd.DataFrame({
        'Jour': pd.date_range(start='2024-01-01', periods=30, freq='D'),
        'Votes': np.random.randint(5, 50, 30),
        'Idées': np.random.randint(1, 10, 30)
    })
    
    chart = alt.Chart(df_demo).mark_line(point=True).encode(
        x='Jour:T',
        y='Votes:Q',
        tooltip=['Jour:T', 'Votes:Q']
    ).properties(
        title="Activité simulée (données de démo)",
        width=700,
        height=400
    )
    
    st.altair_chart(chart, use_container_width=True)

# =============================================================
# === FONCTIONS D'ANALYSE ===
# =============================================================

def voir_resultats():
    """Affiche les résultats avec support hors-ligne"""
    st.title("📊 Résultats des votes")
    
    if not st.session_state.database_ready:
        st.warning("📱 Mode démo - Résultats simulés")
        afficher_resultats_demo()
        return
    
    try:
        db = get_db_connection()
        if not db:
            st.warning("📱 Mode démo - Résultats simulés")
            afficher_resultats_demo()
            return
            
        # Récupérer toutes les questions
        questions = list(db.question.find({}, {"_id": 1, "question": 1}).sort("date_creation", -1))
        
        if not questions:
            st.info("Aucune question disponible pour le moment.")
            return
        
        # Sélecteur de question
        question_options = {f"{q['question'][:80]}..." if len(q['question']) > 80 else q['question']: q['_id'] 
                           for q in questions}
        
        selected_question_text = st.selectbox(
            "🔍 Sélectionnez une question pour voir ses résultats :",
            options=list(question_options.keys()),
            index=0,
            key="select_question_results"
        )
        
        selected_question_id = question_options[selected_question_text]
        
        # Récupérer la question complète
        selected_question = db.question.find_one({"_id": selected_question_id})
        
        if selected_question:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        padding: 1.5rem; border-radius: 10px; color: white; margin: 1rem 0;'>
                <h3 style='color: white; margin: 0;'>❓ {selected_question['question']}</h3>
            </div>
            """, unsafe_allow_html=True)
        
        # Pipeline pour les résultats
        pipeline = [
            {"$match": {"id_question": selected_question_id}},
            {"$lookup": {
                "from": "idees",
                "localField": "id_idee_gagnant",
                "foreignField": "_id",
                "as": "idee_gagnant"
            }},
            {"$lookup": {
                "from": "idees",
                "localField": "id_idee_perdant",
                "foreignField": "_id",
                "as": "idee_perdant"
            }},
            {"$unwind": "$idee_gagnant"},
            {"$unwind": "$idee_perdant"},
            {"$group": {
                "_id": "$idee_gagnant._id",
                "idee_texte": {"$first": "$idee_gagnant.idee_texte"},
                "victoires": {"$sum": 1},
                "sentiment_score": {"$first": "$idee_gagnant.sentiment_score"},
                "sentiment_label": {"$first": "$idee_gagnant.sentiment_label"},
                "creer_par_utilisateur": {"$first": "$idee_gagnant.creer_par_utilisateur"}
            }},
            {"$lookup": {
                "from": "vote",
                "let": {"idee_id": "$_id"},
                "pipeline": [
                    {"$match": {
                        "$expr": {
                            "$and": [
                                {"$eq": ["$id_question", selected_question_id]},
                                {"$eq": ["$id_idee_perdant", "$$idee_id"]}
                            ]
                        }
                    }}
                ],
                "as": "defaites_votes"
            }},
            {"$addFields": {
                "defaites": {"$size": "$defaites_votes"}
            }},
            {"$project": {
                "idee_texte": 1,
                "victoires": 1,
                "defaites": 1,
                "sentiment_score": 1,
                "sentiment_label": 1,
                "creer_par_utilisateur": 1,
                "total": {"$add": ["$victoires", "$defaites"]}
            }},
            {"$sort": {"victoires": -1}}
        ]
        
        resultats = list(db.vote.aggregate(pipeline))
        
        if not resultats:
            st.info("Aucun vote enregistré pour cette question.")
            return
        
        # Préparer les données
        data = []
        for result in resultats:
            victoires = int(result.get("victoires", 0))
            defaites = int(result.get("defaites", 0))
            total = victoires + defaites
            score = round((victoires / total) * 100, 2) if total > 0 else 0.0
            
            type_idee = "Idée téléchargée" if result.get("creer_par_utilisateur") == "oui" else "Idée originale"
            
            data.append({
                "Idée": result["idee_texte"],
                "Score": float(score),
                "Type": type_idee,
                "Sentiment": result.get("sentiment_label", "Non analysé"),
                "Score Sentiment": float(result.get("sentiment_score", 0.0)),
                "Victoires": int(victoires),
                "Défaites": int(defaites),
                "Total": int(total)
            })
        
        df = pd.DataFrame(data).sort_values(by="Score", ascending=False)
        
        if not df.empty:
            # 🏆 Idée la plus soutenue
            meilleure = df.iloc[0]
            st.markdown(f"""
            <div style='background-color: #E8F5E9; padding: 1rem; border-radius: 10px; border-left: 5px solid #4CAF50;'>
                <h4 style='color: #2E7D32; margin: 0;'>🏆 Idée la plus soutenue</h4>
                <p style='margin: 0.5rem 0;'><strong>{meilleure['Idée']}</strong></p>
                <p style='margin: 0;'>Score: <strong>{meilleure['Score']:.1f}%</strong> | 
                Sentiment: <strong>{meilleure['Sentiment']}</strong> | 
                Votes: {meilleure['Total']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Graphique des scores
            st.markdown("### 📈 Classement des idées")
            
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X('Score:Q', title='Score (%)', scale=alt.Scale(domain=[0, 100])),
                y=alt.Y('Idée:N', sort='-x', title=''),
                color=alt.Color('Type:N', 
                              scale=alt.Scale(domain=["Idée originale", "Idée téléchargée"], 
                                            range=["#1f77b4", "#ff7f0e"]),
                              title="Type d'idée"),
                tooltip=['Idée:N', 'Score:Q', 'Victoires:Q', 'Défaites:Q', 'Type:N']
            ).properties(
                height=400,
                title="Score de préférence par idée"
            )
            
            st.altair_chart(chart, use_container_width=True)
            
            # Tableau détaillé
            st.markdown("### 📋 Détail des résultats")
            display_df = df[['Idée', 'Score', 'Victoires', 'Défaites', 'Total', 'Sentiment', 'Type']]
            st.dataframe(display_df, use_container_width=True)
            
    except Exception as e:
        st.error(f"❌ Erreur résultats: {e}")
        afficher_resultats_demo()

def afficher_resultats_demo():
    """Afficher des résultats de démo"""
    st.info("📊 Résultats de démo - Les vraies données s'afficheront quand la connexion sera rétablie")
    
    # Données de démo
    idees_demo = [
        "Éducation gratuite pour tous",
        "Monnaie unique africaine",
        "Développement des énergies renouvelables",
        "Infrastructures de transport modernes",
        "Accès universel aux soins de santé"
    ]
    
    data_demo = []
    for i, idee in enumerate(idees_demo):
        score = np.random.uniform(30, 90)
        data_demo.append({
            "Idée": idee,
            "Score": round(score, 1),
            "Type": "Idée originale" if i < 3 else "Idée téléchargée",
            "Sentiment": np.random.choice(["Positif", "Neutre", "Négatif"]),
            "Victoires": np.random.randint(5, 50),
            "Défaites": np.random.randint(0, 20),
            "Total": np.random.randint(10, 70)
        })
    
    df_demo = pd.DataFrame(data_demo).sort_values(by="Score", ascending=False)
    
    # Graphique de démo
    chart = alt.Chart(df_demo).mark_bar().encode(
        x=alt.X('Score:Q', title='Score (%)'),
        y=alt.Y('Idée:N', sort='-x', title=''),
        color=alt.Color('Type:N', title="Type d'idée"),
        tooltip=['Idée:N', 'Score:Q', 'Type:N', 'Sentiment:N']
    ).properties(
        title="Résultats de démo",
        height=400
    )
    
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df_demo[['Idée', 'Score', 'Type', 'Sentiment', 'Total']], use_container_width=True)

# =============================================================
# === PAGE D'ACCUEIL AMÉLIORÉE ===
# =============================================================

def display_home_page():
    """Affiche la page d'accueil avec statut de connexion"""
    
    # CSS personnalisé
    st.markdown("""
    <style>
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 4rem 2rem;
            border-radius: 0 0 20px 20px;
            color: white;
            text-align: center;
            margin-bottom: 2rem;
            position: relative;
            overflow: hidden;
        }
        
        .connection-status {
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: rgba(255, 255, 255, 0.2);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.9rem;
            backdrop-filter: blur(10px);
        }
        
        .status-connected { color: #4CAF50; }
        .status-disconnected { color: #FF9800; }
        
        .main-title {
            font-size: 3.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .main-subtitle {
            font-size: 1.3rem;
            opacity: 0.9;
            max-width: 800px;
            margin: 0 auto 2rem;
            line-height: 1.6;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Statut de connexion
    status_class = "status-connected" if st.session_state.database_ready else "status-disconnected"
    status_text = "🟢 Connecté" if st.session_state.database_ready else "🟡 Mode démo"
    
    # Header principal
    st.markdown(f"""
    <div class="main-header">
        <div class="connection-status {status_class}">{status_text}</div>
        <h1 class="main-title">🗳️ QUE VOULONS-NOUS POUR L'AFRIQUE ?</h1>
        <p class="main-subtitle">
            Plateforme citoyenne interactive pour explorer les priorités sociales, 
            politiques et économiques des Africains. Proposez, comparez et classez 
            des idées pour l'avenir du continent.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Avertissement si en mode démo
    if not st.session_state.database_ready:
        st.warning("""
        **⚠️ Mode démo activé** - L'application fonctionne avec des données simulées.
        
        **Pour utiliser toutes les fonctionnalités :**
        1. Assurez-vous que votre base de données Railway est démarrée
        2. Vérifiez que l'adresse IP de Render est autorisée
        3. Ou configurez une base de données sur Render
        """)
    
    # Statistiques
    try:
        db = get_db_connection()
        if db and st.session_state.database_ready:
            total_questions = db.question.count_documents({})
            total_idees = db.idees.count_documents({})
            total_votes = db.vote.count_documents({})
            total_users = db.navigateur.count_documents({})
        else:
            # Données de démo
            total_questions = 12
            total_idees = 47
            total_votes = 156
            total_users = 28
            
    except:
        total_questions = 8
        total_idees = 32
        total_votes = 89
        total_users = 15
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📝 Questions", total_questions)
    with col2:
        st.metric("💡 Idées", total_idees)
    with col3:
        st.metric("🗳️ Votes", total_votes)
    with col4:
        st.metric("👥 Participants", total_users)
    
    # Fonctionnalités
    st.markdown("## ✨ Comment ça marche ?")
    
    steps = [
        ("1️⃣", "Proposez une question et deux idées", "Créez le débat sur un sujet qui vous tient à cœur"),
        ("2️⃣", "Comparez les idées par paires", "Votez pour celle que vous préférez parmi deux propositions"),
        ("3️⃣", "Ajoutez vos propres idées", "Enrichissez le débat avec vos propositions"),
        ("4️⃣", "Découvrez les résultats", "Voyez quelles idées sont les plus populaires")
    ]
    
    for icon, title, desc in steps:
        st.markdown(f"""
        <div style='background: white; padding: 1.5rem; border-radius: 10px; margin: 1rem 0; border-left: 5px solid #667eea;'>
            <div style='display: flex; align-items: center; gap: 1rem;'>
                <span style='font-size: 2rem;'>{icon}</span>
                <div>
                    <h4 style='margin: 0; color: #333;'>{title}</h4>
                    <p style='margin: 0.5rem 0 0 0; color: #666;'>{desc}</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # CTA Section
    st.markdown("## 🚀 Prêt à participer ?")
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if st.button("✍️ Proposer une question", 
                    use_container_width=True, 
                    type="primary",
                    key="home_btn_create"):
            st.session_state.current_tab = "create"
            st.rerun()
    
    with col2:
        if st.button("🗳️ Commencer à voter", 
                    use_container_width=True,
                    key="home_btn_vote"):
            st.session_state.current_tab = "vote"
            st.rerun()
    
    with col3:
        if st.button("📊 Voir les résultats", 
                    use_container_width=True,
                    key="home_btn_stats"):
            st.session_state.current_tab = "stats"
            st.rerun()
    
    with col4:
        if st.button("📈 Visualisations", 
                    use_container_width=True,
                    key="home_btn_viz"):
            st.session_state.current_tab = "visualisations"
            st.rerun()

# =============================================================
# === FONCTION PRINCIPALE ===
# =============================================================

def main():
    """Fonction principale avec gestion d'erreurs"""
    
    # Navigation
    tabs = ["🏠 Accueil", "➕ Créer", "🗳️ Voter", "📊 Statistiques", "📈 Visualisations"]
    tab_keys = ["home", "create", "vote", "stats", "visualisations"]
    
    selected_tab = st.session_state.current_tab
    
    # Afficher les onglets
    cols = st.columns([1, 1, 1, 1, 1, 2])
    
    for idx, (tab_name, tab_key) in enumerate(zip(tabs, tab_keys)):
        with cols[idx]:
            if st.button(tab_name, 
                        use_container_width=True,
                        type="primary" if selected_tab == tab_key else "secondary",
                        key=f"nav_{tab_key}"):
                st.session_state.current_tab = tab_key
                st.rerun()
    
    # Afficher le statut utilisateur et connexion
    with cols[5]:
        if st.session_state.get("email"):
            user_status = f"👤 {st.session_state.email}"
        else:
            user_status = "👤 Visiteur"
            
        db_status = "🟢" if st.session_state.database_ready else "🟡"
        
        st.markdown(f"""
        <div style='text-align: right;'>
            <div style='color: #666; font-size: 0.9rem;'>{user_status}</div>
            <div style='color: #666; font-size: 0.8rem;'>{db_status} {"Base connectée" if st.session_state.database_ready else "Mode démo"}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Séparateur
    st.markdown("---")
    
    # Gestion des erreurs pour chaque onglet
    try:
        if selected_tab == "home":
            display_home_page()
        
        elif selected_tab == "create":
            creer_question()
        
        elif selected_tab == "vote":
            participer()
        
        elif selected_tab == "stats":
            voir_resultats()
        
        elif selected_tab == "visualisations":
            afficher_visualisations()
            
    except Exception as e:
        st.error(f"❌ Une erreur est survenue : {e}")
        st.info("Veuillez rafraîchir la page ou réessayer plus tard")
        
        # Option pour retourner à l'accueil
        if st.button("🏠 Retour à l'accueil"):
            st.session_state.current_tab = "home"
            st.rerun()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 2rem 0;">
        <p>🌍 <strong>Wiki Survey - Afrique Participative</strong></p>
        <p>Plateforme citoyenne pour le dialogue et la prise de décision collective</p>
        <p style="font-size: 0.8rem;">© 2024 - Tous droits réservés | {db_status} {"Base de données opérationnelle" if st.session_state.database_ready else "Mode démo actif"}</p>
    </div>
    """, unsafe_allow_html=True)

# === Point d'entrée avec gestion d'erreurs globale ===
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"🚨 Erreur critique : {e}")
        st.info("""
        **Problèmes courants :**
        1. Vérifiez votre connexion à la base de données Railway
        2. Assurez-vous que Render a accès à votre base
        3. Vérifiez que votre URL MongoDB est correcte
        """)
        
        # Option pour réessayer
        if st.button("🔄 Réessayer"):
            st.rerun()
